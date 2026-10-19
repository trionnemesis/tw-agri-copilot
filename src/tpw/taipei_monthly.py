"""Taipei monthly retail prices and food supply statistics (Issue #51 PR 2).

Two monthly sources stay apart at every step: item-level public retail market average prices
(元/台斤) and category-level food supply volumes and prices. Snapshots enter only through
`ingest_snapshot`, which pins the raw header contract and fails closed on drift, keeps every
revision, and is idempotent for identical content. The analysis publishes descriptive history per
exact raw item or category only: no Buy Score, no current-price claim, no confidence interval, and
no mixing with the daily wholesale rows. A failure is published as a failed document so it never
blocks the nationwide build.
"""

import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import pathlib
import re
import statistics
import tempfile
import unicodedata


SCHEMA_VERSION = "1.0"
SCOPE_ID = "taipei-city"
SNAPSHOT_DIR = pathlib.PurePosixPath("data/taipei-monthly")
MAPPING_PATH = pathlib.PurePosixPath("config/taipei-retail-items.json")
JIN_IN_KG = 0.6
TAIPEI_NAMES = frozenset({"臺北市", "台北市"})
BLANK_TOKENS = frozenset({"", "-", "—", "－", "–"})
SOURCE_STATUSES = frozenset({"live", "manual", "fixture"})
VERIFIED_AUTHORITATIVE_CONTRACT_STATUS = "verified_authoritative"
COMMODITY_FAMILIES = frozenset({"fruit", "vegetable", "livestock", "aquaculture"})
SUPPLY_CATEGORIES = ("雞", "鴨", "魚", "蔬菜", "水果")
MIN_MONTHS_MEDIAN = 3
MIN_MONTHS_QUARTILES = 4
SOURCES = {
    "retail": {
        "source_id": "taipei_public_retail_market_prices",
        "title": "臺北市公有零售市場行情",
        "dataset_url": "https://data.taipei/dataset/detail?id=54d9d492-1e2e-40d1-ae7b-fbce6f271bf1",
        "granularity": "item",
        "market_level": "retail",
        # Headers come from search-engine summaries of the data.taipei and data.gov.tw listings, not
        # from an inspected CSV; they stay provisional until a real resource is checked.
        "contract_status": "provisional_unverified",
        "headers": {
            "retail-3col": ("序號", "項目", "平均(元/台斤)"),
            "retail-5col": ("序號", "縣市名", "縣市別代碼", "項目", "平均(元/台斤)"),
        },
    },
    "supply": {
        "source_id": "taipei_food_supply_monthly",
        "title": "臺北市食物供銷按月別",
        "dataset_url": "https://data.taipei/dataset/detail?id=925ba4ba-9e3c-4ae9-98fc-95ddfe14ea90",
        "granularity": "category",
        "market_level": "unknown",
        # No upstream header has been observed: this intake header is the project's own and must be
        # replaced by the verified upstream one before any live ingestion.
        "contract_status": "provisional_project_defined",
        "headers": {
            "supply-v0": ("類別", "交易量(公斤)", "平均價格(元/公斤)"),
        },
    },
}
ANALYSIS_STATUSES = frozenset({"published", "failed"})
SOURCE_SUMMARY_STATUSES = frozenset({"not_ingested", "mixed"}) | SOURCE_STATUSES
VALUE_STATUSES = frozenset({"valid", "missing", "zero_reported"})
ADVICE_STATUSES = frozenset({"historical_reference", "insufficient"})
POSITIONS = frozenset({"below_q1", "within_iqr", "above_q3"})
DIRECTIONS = frozenset({"up", "down", "flat"})
FIELDS = frozenset({
    "schema_version", "scope_id", "analysis_status", "failure_reason", "as_of_date", "requested_date",
    "national_fallback", "buy_score", "method", "snapshot_hash", "sources", "retail_items", "supply_categories",
})
RETAIL_CSV_FIELDS = (
    "observation_period", "frequency", "scope_id", "market_level", "source_id", "item_raw", "commodity_family",
    "mapping_status", "price_raw", "price_unit_raw", "price_twd_per_kg", "value_status", "revision", "raw_hash",
    "source_status",
)
SUPPLY_CSV_FIELDS = (
    "observation_period", "frequency", "scope_id", "source_id", "category", "volume_kg", "volume_status",
    "price_twd_per_kg", "price_status", "revision", "raw_hash", "source_status",
)


class TaipeiMonthlyError(ValueError):
    """A Taipei monthly snapshot, mapping or published document violated its contract."""


def _require(condition, message):
    if not condition:
        raise TaipeiMonthlyError(message)


def _require_live_contract(source, source_status, stored_contract_status):
    if source_status != "live":
        return
    _require(
        SOURCES[source]["contract_status"] == VERIFIED_AUTHORITATIVE_CONTRACT_STATUS,
        source + " registry contract is not verified authoritative for live snapshots",
    )
    _require(
        stored_contract_status == VERIFIED_AUTHORITATIVE_CONTRACT_STATUS,
        source + " stored contract is not verified authoritative for live snapshots",
    )


def _period(value):
    _require(isinstance(value, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value) is not None, "period must use YYYY-MM")
    return value


def _shift(period, months):
    year, month = map(int, period.split("-"))
    index = year * 12 + month - 1 + months
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def _hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _number(token, label):
    text = unicodedata.normalize("NFKC", token).replace(",", "").strip()
    if text in BLANK_TOKENS:
        return None, "missing"
    try:
        value = float(text)
    except ValueError as exc:
        # An unknown token is drift, not a missing value: fail closed instead of guessing.
        raise TaipeiMonthlyError(label + " is not a number or a known blank token: " + repr(token)) from exc
    _require(math.isfinite(value) and value >= 0, label + " must be finite and nonnegative")
    return value, "valid" if value > 0 else "zero_reported"


def parse_snapshot(source, raw_bytes):
    _require(source in SOURCES, "unknown Taipei monthly source: " + repr(source))
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TaipeiMonthlyError(source + " snapshot is not UTF-8") from exc
    rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    _require(rows, source + " snapshot is empty")
    header = tuple(unicodedata.normalize("NFKC", cell).strip() for cell in rows[0])
    contract = next((name for name, expected in SOURCES[source]["headers"].items() if expected == header), None)
    _require(contract is not None, source + " header does not match a pinned contract: " + "|".join(header))
    records = []
    for row in rows[1:]:
        _require(len(row) == len(header), source + " row width does not match its header")
        records.append(dict(zip(header, (cell.strip() for cell in row))))
    _require(records, source + " snapshot has no data rows")
    return contract, _normalize(source, contract, records)


def _normalize(source, contract, records):
    rows = []
    if source == "retail":
        codes = set()
        for record in records:
            if contract == "retail-5col":
                _require(record["縣市名"] in TAIPEI_NAMES, "retail snapshot row is not for Taipei City: " + record["縣市名"])
                codes.add(record["縣市別代碼"])
            item = record["項目"]
            _require(bool(item), "retail item name is empty")
            price, status = _number(record["平均(元/台斤)"], "retail price for " + item)
            rows.append({"item_raw": item, "price_raw": price, "value_status": status})
        _require(len(codes) <= 1, "retail snapshot mixes county codes")
        keys = [row["item_raw"] for row in rows]
    else:
        for record in records:
            category = record["類別"]
            _require(category in SUPPLY_CATEGORIES, "supply category is not one of 雞／鴨／魚／蔬菜／水果: " + repr(category))
            volume, volume_status = _number(record["交易量(公斤)"], "supply volume for " + category)
            price, price_status = _number(record["平均價格(元/公斤)"], "supply price for " + category)
            rows.append({"category": category, "volume_kg": volume, "volume_status": volume_status, "price_twd_per_kg": price, "price_status": price_status})
        keys = [row["category"] for row in rows]
    _require(len(keys) == len(set(keys)), source + " snapshot repeats an item or category")
    return rows


def _iso_datetime(value, label):
    try:
        _require(isinstance(value, str) and dt.datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None, label + " must be an ISO-8601 timestamp with a timezone")
    except ValueError as exc:
        raise TaipeiMonthlyError(label + " must be an ISO-8601 timestamp with a timezone") from exc
    return value


def _period_evidence(period, resource_name):
    # data.taipei names monthly resources like 「114年12月份行情」; when the name carries a month it
    # must agree with the operator-supplied period, otherwise the period rests on the operator alone.
    match = re.search(r"(\d{2,3})年(\d{1,2})月", resource_name)
    if not match:
        return "operator"
    named = "%04d-%02d" % (int(match.group(1)) + 1911, int(match.group(2)))
    _require(named == period, "resource name month " + named + " does not match the period " + period)
    return "resource_name"


def snapshot_path(data_root, source, period):
    return pathlib.Path(data_root) / "taipei-monthly" / source / (period + ".json")


def ingest_snapshot(data_root, source, raw_bytes, *, period, resource_id, resource_name, resource_url, retrieved_at, license, source_status):
    period = _period(period)
    _require(source_status in SOURCE_STATUSES, "source_status must be live, manual or fixture")
    _require(isinstance(resource_url, str) and resource_url.startswith("https://"), "resource_url must use https")
    for label, value in (("resource_id", resource_id), ("resource_name", resource_name), ("license", license)):
        _require(isinstance(value, str) and value.strip() == value and value, label + " must be a non-empty trimmed string")
    _iso_datetime(retrieved_at, "retrieved_at")
    evidence = _period_evidence(period, resource_name)
    contract, rows = parse_snapshot(source, raw_bytes)
    contract_status = SOURCES[source]["contract_status"]
    _require_live_contract(source, source_status, contract_status)
    raw_hash = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    path = snapshot_path(data_root, source, period)
    document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "schema_version": SCHEMA_VERSION, "source": source, "source_id": SOURCES[source]["source_id"],
        "observation_period": period, "revisions": [],
    }
    if document["revisions"]:
        validate_snapshot_document(document, source, period)
    if document["revisions"] and document["revisions"][-1]["raw_hash"] == raw_hash:
        return {"source": source, "period": period, "revision": document["revisions"][-1]["revision"], "status": "unchanged"}
    revision = len(document["revisions"]) + 1
    document["revisions"].append({
        "revision": revision, "resource_id": resource_id, "resource_name": resource_name, "resource_url": resource_url,
        "retrieved_at": retrieved_at, "known_at": retrieved_at, "license": license, "source_status": source_status,
        "period_evidence": evidence, "contract": contract, "contract_status": contract_status,
        "raw_hash": raw_hash, "row_count": len(rows), "raw_text": raw_bytes.decode("utf-8-sig"),
    })
    validate_snapshot_document(document, source, period)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)
    return {"source": source, "period": period, "revision": revision, "status": "revised" if revision > 1 else "added"}


REVISION_FIELDS = frozenset({
    "revision", "resource_id", "resource_name", "resource_url", "retrieved_at", "known_at", "license", "source_status",
    "period_evidence", "contract", "contract_status", "raw_hash", "row_count", "raw_text",
})


def validate_snapshot_document(document, source, period):
    _require(isinstance(document, dict) and set(document) == {"schema_version", "source", "source_id", "observation_period", "revisions"}, "Taipei monthly snapshot fields do not match the contract")
    _require((document["schema_version"], document["source"], document["source_id"], document["observation_period"]) == (SCHEMA_VERSION, source, SOURCES[source]["source_id"], period), "Taipei monthly snapshot identity does not match its path")
    _require(isinstance(document["revisions"], list) and document["revisions"], "Taipei monthly snapshot has no revisions")
    for index, revision in enumerate(document["revisions"], start=1):
        _require(isinstance(revision, dict) and set(revision) == REVISION_FIELDS and revision["revision"] == index, "Taipei monthly revision fields or numbering are invalid")
        _require(revision["source_status"] in SOURCE_STATUSES and revision["contract"] in SOURCES[source]["headers"], "Taipei monthly revision status or contract is invalid")
        _require_live_contract(source, revision["source_status"], revision["contract_status"])
        raw_bytes = revision["raw_text"].encode("utf-8")
        contract, rows = parse_snapshot(source, raw_bytes)
        _require(contract == revision["contract"] and len(rows) == revision["row_count"], "Taipei monthly revision does not re-parse to its recorded contract")
        _require(revision["period_evidence"] == _period_evidence(period, revision["resource_name"]), "Taipei monthly revision period evidence is inconsistent")
    return document


def load_retail_mapping(root):
    path = pathlib.Path(root) / MAPPING_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict) and set(payload) == {"schema_version", "review_policy", "items"} and payload["schema_version"] == "1.0", "retail item mapping fields do not match the contract")
    mapping = {}
    fields = {"item_raw", "commodity_family", "canonical_id", "variant", "cut", "grade", "mass_basis", "evidence"}
    for entry in payload["items"]:
        _require(isinstance(entry, dict) and set(entry) == fields, "retail item mapping entry fields do not match the contract")
        _require(entry["commodity_family"] in COMMODITY_FAMILIES and isinstance(entry["mass_basis"], bool), "retail item mapping family or mass basis is invalid")
        _require(isinstance(entry["evidence"], str) and entry["evidence"].strip(), "retail item mapping needs reviewed evidence")
        _require(all(entry[key] is None or (isinstance(entry[key], str) and entry[key].strip()) for key in ("canonical_id", "variant", "cut", "grade")), "retail item mapping identifiers must be null or non-empty strings")
        _require(entry["item_raw"] not in mapping, "retail item mapping repeats an exact item")
        mapping[entry["item_raw"]] = entry
    return mapping


def _latest_revisions(data_root, source, cutoff_date):
    base = pathlib.Path(data_root) / "taipei-monthly" / source
    selected = []
    for path in sorted(base.glob("*.json")) if base.exists() else []:
        period = _period(path.stem)
        document = validate_snapshot_document(json.loads(path.read_text(encoding="utf-8")), source, period)
        # A historical rebuild only sees revisions already known on its requested date.
        known = [revision for revision in document["revisions"] if revision["known_at"][:10] <= cutoff_date]
        if known:
            selected.append((period, known[-1], len(known)))
    return selected


def _pct(current, reference):
    if current is None or reference in (None, 0):
        return None
    return round((current - reference) / reference * 100, 6)


def _round(value):
    return None if value is None else round(value, 6)


def _per_kg(price_raw):
    return None if price_raw is None else round(price_raw / JIN_IN_KG, 6)


def _describe(months, key):
    valid = [row for row in months if row[key + "_status"] == "valid"]
    values = [row[key] for row in valid]
    latest = valid[-1] if valid else None
    by_period = {row["period"]: row[key] for row in valid}
    quartiles = statistics.quantiles(values, n=4, method="inclusive") if len(values) >= MIN_MONTHS_QUARTILES else None
    reference = values[:-1]
    reference_quartiles = statistics.quantiles(reference, n=4, method="inclusive") if len(reference) >= MIN_MONTHS_QUARTILES else None
    position = None
    if latest and reference_quartiles:
        position = "below_q1" if latest[key] < reference_quartiles[0] else "above_q3" if latest[key] > reference_quartiles[2] else "within_iqr"
    return {
        "valid_month_count": len(values),
        "latest_valid_period": latest["period"] if latest else None,
        "latest": _round(latest[key]) if latest else None,
        "median": _round(statistics.median(values)) if len(values) >= MIN_MONTHS_MEDIAN else None,
        "q1": _round(quartiles[0]) if quartiles else None,
        "q3": _round(quartiles[2]) if quartiles else None,
        "mom_pct": _pct(latest[key], by_period.get(_shift(latest["period"], -1))) if latest else None,
        "yoy_pct": _pct(latest[key], by_period.get(_shift(latest["period"], -12))) if latest else None,
        "latest_vs_history": position,
        "stats_status": "valid" if len(values) >= MIN_MONTHS_MEDIAN else "insufficient",
    }


def _direction(change):
    if change is None:
        return None
    return "up" if change > 0 else "down" if change < 0 else "flat"


def _source_summary(source, revisions):
    spec = SOURCES[source]
    statuses = {revision["source_status"] for _, revision, _ in revisions}
    return {
        "source": source,
        "source_id": spec["source_id"],
        "title": spec["title"],
        "dataset_url": spec["dataset_url"],
        "granularity": spec["granularity"],
        "frequency": "monthly",
        "market_level": spec["market_level"],
        "contract_status": spec["contract_status"],
        "status": "not_ingested" if not revisions else statuses.pop() if len(statuses) == 1 else "mixed",
        "latest_period": revisions[-1][0] if revisions else None,
        "periods": [
            {
                "period": period, "revision": revision["revision"], "revision_count": count,
                "resource_id": revision["resource_id"], "resource_name": revision["resource_name"],
                "resource_url": revision["resource_url"], "retrieved_at": revision["retrieved_at"],
                "known_at": revision["known_at"], "license": revision["license"],
                "source_status": revision["source_status"], "period_evidence": revision["period_evidence"],
                "contract": revision["contract"], "raw_hash": revision["raw_hash"], "row_count": revision["row_count"],
            }
            for period, revision, count in revisions
        ],
    }


def _retail_items(revisions, mapping):
    series = {}
    for period, revision, _ in revisions:
        _, rows = parse_snapshot("retail", revision["raw_text"].encode("utf-8"))
        for row in rows:
            series.setdefault(row["item_raw"], []).append({
                "period": period, "price_raw": row["price_raw"], "price_raw_status": row["value_status"],
                "revision": revision["revision"], "raw_hash": revision["raw_hash"], "source_status": revision["source_status"],
            })
    latest_period = revisions[-1][0] if revisions else None
    items = []
    for item_raw, months in sorted(series.items()):
        entry = mapping.get(item_raw)
        mass_basis = entry["mass_basis"] if entry else True
        stats = _describe(months, "price_raw")
        items.append({
            "item_raw": item_raw,
            "comparison_key": "exact_raw_item",
            "mapping_status": "reviewed" if entry else "unmapped",
            "commodity_family": entry["commodity_family"] if entry else "unknown",
            "canonical_id": entry["canonical_id"] if entry else None,
            "variant": entry["variant"] if entry else None,
            "cut": entry["cut"] if entry else None,
            "grade": entry["grade"] if entry else None,
            "mass_basis": mass_basis,
            "price_unit_raw": "元/台斤",
            "in_latest_period": months[-1]["period"] == latest_period,
            **{key: value for key, value in stats.items() if key not in ("latest", "median", "q1", "q3")},
            "latest_price_raw": stats["latest"],
            "latest_price_twd_per_kg": _per_kg(stats["latest"]) if mass_basis else None,
            "median_price_raw": stats["median"],
            "q1_price_raw": stats["q1"],
            "q3_price_raw": stats["q3"],
            "advice": {"status": "historical_reference" if stats["latest_vs_history"] else "insufficient", "basis": "latest_published_month"},
            "months": [
                {**month, "price_twd_per_kg": _per_kg(month["price_raw"]) if mass_basis else None}
                for month in months
            ],
        })
    return items


def _supply_categories(revisions):
    series = {category: [] for category in SUPPLY_CATEGORIES}
    for period, revision, _ in revisions:
        _, rows = parse_snapshot("supply", revision["raw_text"].encode("utf-8"))
        for row in rows:
            series[row["category"]].append({
                "period": period, "volume_kg": row["volume_kg"], "volume_kg_status": row["volume_status"],
                "price_twd_per_kg": row["price_twd_per_kg"], "price_twd_per_kg_status": row["price_status"],
                "revision": revision["revision"], "raw_hash": revision["raw_hash"], "source_status": revision["source_status"],
            })
    categories = []
    for category in SUPPLY_CATEGORIES:
        months = series[category]
        volume = _describe(months, "volume_kg")
        price = _describe(months, "price_twd_per_kg")
        same_month = volume["latest_valid_period"] is not None and volume["latest_valid_period"] == price["latest_valid_period"]
        categories.append({
            "category": category,
            "volume": volume,
            "price": price,
            # A volume-price trend needs both measures on the same latest month and its previous month.
            "trend": {"volume": _direction(volume["mom_pct"]), "price": _direction(price["mom_pct"])} if same_month and volume["mom_pct"] is not None and price["mom_pct"] is not None else None,
            "months": months,
        })
    return categories


def _method():
    return {
        "comparison_key": "exact_raw_item_or_category",
        "jin_in_kg": JIN_IN_KG,
        "price_conversion": "price_twd_per_kg = price_raw_per_jin / 0.6",
        "quartile_method": "statistics.quantiles(n=4, method='inclusive')",
        "minimum_months": {"median": MIN_MONTHS_MEDIAN, "quartiles": MIN_MONTHS_QUARTILES},
        "position_reference": "valid months before the latest valid month",
        "knowledge_cutoff": "revision known_at UTC date <= requested_date",
        "confidence_interval": "not_published_without_sample_counts",
    }


def _header(as_of_date, publication_status):
    return {
        "schema_version": SCHEMA_VERSION,
        "scope_id": SCOPE_ID,
        "as_of_date": dt.date.fromisoformat(as_of_date).isoformat(),
        "requested_date": publication_status["requested_date"],
        "national_fallback": False,
        "buy_score": "not_evaluated",
        "method": _method(),
    }


def build_monthly_analysis(data_root, as_of_date, publication_status, mapping):
    cutoff = publication_status["requested_date"]
    retail = _latest_revisions(data_root, "retail", cutoff)
    supply = _latest_revisions(data_root, "supply", cutoff)
    document = {
        **_header(as_of_date, publication_status),
        "analysis_status": "published",
        "failure_reason": None,
        "snapshot_hash": _hash([[source, period, revision["raw_hash"]] for source, revisions in (("retail", retail), ("supply", supply)) for period, revision, _ in revisions]),
        "sources": [_source_summary("retail", retail), _source_summary("supply", supply)],
        "retail_items": _retail_items(retail, mapping),
        "supply_categories": _supply_categories(supply) if supply else [],
    }
    return validate_monthly_analysis(document)


def failed_monthly_analysis(as_of_date, publication_status, reason):
    # Publishes the failure instead of statistics: no last-known-good numbers, no substitute source.
    document = {
        **_header(as_of_date, publication_status),
        "analysis_status": "failed",
        "failure_reason": reason,
        "snapshot_hash": None,
        "sources": [],
        "retail_items": [],
        "supply_categories": [],
    }
    return validate_monthly_analysis(document)


def _validate_stats(stats, label):
    _require(stats["stats_status"] in ("valid", "insufficient") and (stats["stats_status"] == "valid") == (stats["valid_month_count"] >= MIN_MONTHS_MEDIAN), label + " stats status is inconsistent")
    _require(stats["latest_vs_history"] is None or stats["latest_vs_history"] in POSITIONS, label + " history position is invalid")


def validate_monthly_analysis(document):
    _require(isinstance(document, dict) and set(document) == FIELDS, "Taipei monthly analysis fields do not match the contract")
    _require((document["schema_version"], document["scope_id"], document["national_fallback"], document["buy_score"]) == (SCHEMA_VERSION, SCOPE_ID, False, "not_evaluated"), "Taipei monthly analysis header is invalid")
    _require(document["method"] == _method(), "Taipei monthly method does not match the published contract")
    _require(document["as_of_date"] <= document["requested_date"], "Taipei monthly as_of_date cannot be after requested_date")
    _require(document["analysis_status"] in ANALYSIS_STATUSES, "Taipei monthly analysis_status is invalid")
    if document["analysis_status"] == "failed":
        _require(isinstance(document["failure_reason"], str) and document["failure_reason"].strip(), "a failed Taipei monthly analysis must state its reason")
        _require(document["snapshot_hash"] is None and all(document[key] == [] for key in ("sources", "retail_items", "supply_categories")), "a failed Taipei monthly analysis must not publish statistics")
        return document
    _require(document["failure_reason"] is None and isinstance(document["snapshot_hash"], str), "a published Taipei monthly analysis needs a snapshot hash and no failure reason")
    _require([source.get("source") for source in document["sources"]] == ["retail", "supply"], "Taipei monthly analysis must describe the retail and supply sources")
    for source in document["sources"]:
        _require(source["status"] in SOURCE_SUMMARY_STATUSES and source["contract_status"] == SOURCES[source["source"]]["contract_status"], "Taipei monthly source summary is invalid")
        periods = [row["period"] for row in source["periods"]]
        _require(periods == sorted(set(periods)) and (source["latest_period"] == (periods[-1] if periods else None)), "Taipei monthly source periods are inconsistent")
    retail_periods = {row["period"] for row in document["sources"][0]["periods"]}
    for item in document["retail_items"]:
        label = "retail item " + item["item_raw"]
        _validate_stats(item, label)
        _require(item["commodity_family"] in COMMODITY_FAMILIES | {"unknown"} and (item["mapping_status"] == "reviewed") == (item["commodity_family"] != "unknown"), label + " mapping is inconsistent")
        _require(item["advice"]["status"] in ADVICE_STATUSES and (item["advice"]["status"] == "historical_reference") == (item["latest_vs_history"] is not None), label + " advice is inconsistent")
        for month in item["months"]:
            _require(month["period"] in retail_periods and month["price_raw_status"] in VALUE_STATUSES, label + " month is outside the ingested periods")
            expected = _per_kg(month["price_raw"]) if item["mass_basis"] else None
            _require(month["price_twd_per_kg"] == expected, label + " per-kg price does not follow price_raw / 0.6")
    supply_periods = {row["period"] for row in document["sources"][1]["periods"]}
    _require([row["category"] for row in document["supply_categories"]] == (list(SUPPLY_CATEGORIES) if supply_periods else []), "Taipei supply categories must be the five fixed categories")
    for category in document["supply_categories"]:
        _validate_stats(category["volume"], "supply volume " + category["category"])
        _validate_stats(category["price"], "supply price " + category["category"])
        _require(all(month["period"] in supply_periods for month in category["months"]), "supply month is outside the ingested periods")
        _require(category["trend"] is None or set(category["trend"].values()) <= DIRECTIONS, "supply trend is invalid")
    return document


def _csv_text(fieldnames, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row[key] is None else row[key] for key in fieldnames})
    return buffer.getvalue()


def monthly_csv_documents(document):
    source_ids = {source["source"]: source["source_id"] for source in document["sources"]}
    retail_rows = [
        {
            "observation_period": month["period"], "frequency": "monthly", "scope_id": document["scope_id"], "market_level": "retail",
            "source_id": source_ids.get("retail"), "item_raw": item["item_raw"], "commodity_family": item["commodity_family"],
            "mapping_status": item["mapping_status"], "price_raw": month["price_raw"], "price_unit_raw": item["price_unit_raw"],
            "price_twd_per_kg": month["price_twd_per_kg"], "value_status": month["price_raw_status"], "revision": month["revision"],
            "raw_hash": month["raw_hash"], "source_status": month["source_status"],
        }
        for item in document["retail_items"] for month in item["months"]
    ]
    supply_rows = [
        {
            "observation_period": month["period"], "frequency": "monthly", "scope_id": document["scope_id"], "source_id": source_ids.get("supply"),
            "category": category["category"], "volume_kg": month["volume_kg"], "volume_status": month["volume_kg_status"],
            "price_twd_per_kg": month["price_twd_per_kg"], "price_status": month["price_twd_per_kg_status"], "revision": month["revision"],
            "raw_hash": month["raw_hash"], "source_status": month["source_status"],
        }
        for category in document["supply_categories"] for month in category["months"]
    ]
    return {
        "monthly-retail.csv": _csv_text(RETAIL_CSV_FIELDS, retail_rows),
        "monthly-supply.csv": _csv_text(SUPPLY_CSV_FIELDS, supply_rows),
    }


def fixture_snapshots(fixture):
    """Deterministic monthly CSV snapshots for the prototype; never real published values."""
    output = []
    retail = fixture["retail"]
    for offset in range(retail["months"]):
        period = _shift(retail["start"], offset)
        roc = "%d年%d月份行情" % (int(period[:4]) - 1911, int(period[5:]))
        lines = ["序號,縣市名,縣市別代碼,項目,平均(元/台斤)"]
        for index, item in enumerate(retail["items"], start=1):
            if offset < item.get("start_offset", 0) or period in item.get("absent", []):
                continue
            value = "-" if period in item.get("blank", []) else "%.1f" % (item["base"] + item["slope"] * offset + item.get("season", [0] * 12)[int(period[5:]) - 1])
            lines.append("%d,臺北市,63000,%s,%s" % (index, item["item"], value))
        output.append(("retail", period, roc, "\n".join(lines) + "\n"))
    supply = fixture["supply"]
    for offset in range(supply["months"]):
        period = _shift(supply["start"], offset)
        lines = ["類別,交易量(公斤),平均價格(元/公斤)"]
        for category in supply["categories"]:
            volume = category["volume"] + category["volume_slope"] * offset
            price = category["price"] + category["price_slope"] * offset
            lines.append("%s,%.0f,%.1f" % (category["category"], volume, price))
        output.append(("supply", period, "%d年%d月" % (int(period[:4]) - 1911, int(period[5:])), "\n".join(lines) + "\n"))
    return output
