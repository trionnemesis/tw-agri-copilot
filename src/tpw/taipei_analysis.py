"""Taipei-city scope over the stored MOA 8066 wholesale rows (Issue #51 PR 1).

Rows are filtered to the verified Taipei markets *before* aggregation, with one policy for the
as-of day and for every historical day, so a nationwide statistic is never relabelled as
Taipei's. The scope publishes descriptive statistics only: it computes no Buy Score, never
falls back to nationwide prices when Taipei has no rows, and never treats a market location
as a production origin.
"""

import csv
import datetime as dt
import hashlib
import io
import json

from .analytics import WINDOWS, aggregate, build_series
from .publication import MARKET_STATES


SCHEMA_VERSION = "1.0"
SCOPE_ID = "taipei-city"
SCOPE_LABEL = "臺北市"
SOURCE_ID = "moa_market_8066"
DATASET_ID = "8066"
DATASET_URL = "https://data.gov.tw/dataset/8066"
SOURCE_URL = "https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx"
MARKET_NAMESPACE = "moa_market_8066"
PRODUCT_NAMESPACE = "moa_market_8066_crop"
FILTER_POLICY = "verified-taipei-8066-markets-v1"
PRICE_FORMULA = "sum(price_twd_per_kg*volume_kg)/sum(volume_kg)"
# Mirrors the market-count gate in tpw.scoring; the Taipei scope never relaxes it.
MINIMUM_MARKET_COUNT = 2
DAY_STATUSES = frozenset({"traded", "no_valid_trade", "scheduled_closed", "missing", "calendar_feed_discrepancy"})
ITEM_STATUSES = frozenset({"observed", "no_valid_trade", "no_taipei_observation"})
SCOPE_STATUSES = frozenset({"all_markets_observed", "partial_markets_observed", "no_taipei_observation"})
GATE_STATUSES = frozenset({"insufficient", "not_evaluated"})
COMMODITY_FAMILIES = frozenset({"fruit", "vegetable"})
SCHEDULE_STATUSES = frozenset({"expected_open", "exceptional_open", "scheduled_closed", "unknown"})
FIELDS = frozenset({
    "schema_version", "scope_id", "scope_label", "market_level", "frequency", "as_of_date",
    "requested_date", "publication_status", "source", "filter_policy", "national_fallback",
    "snapshot_hash", "expected_market_count", "observed_market_count", "scope_status", "method",
    "markets", "market_days", "items", "observations",
})
SOURCE_FIELDS = frozenset({"source_id", "dataset_id", "dataset_url", "source_url", "source_status", "retrieved_at"})
MARKET_FIELDS = frozenset({"market_code", "feed_market_name", "official_name", "geography_role", "evidence_url", "as_of_day_status", "as_of_valid_row_count"})
DAY_FIELDS = frozenset({"date", "market_code", "day_status", "schedule_status", "schedule_reason", "row_count", "valid_row_count"})
ITEM_FIELDS = frozenset({
    "canonical_id", "display_name", "commodity_family", "product_namespace", "products_raw", "status",
    "production_method", "origin_status", "today", "previous_trading_day", "windows", "range_stats",
    "volatility_7d_cv", "volatility_7d_status", "recommendation_gate",
})
OBSERVATION_FIELDS = (
    "observation_period", "frequency", "scope_id", "market_namespace", "market_code", "market_name_raw",
    "geography_role", "source_id", "dataset_id", "source_url", "commodity_family", "product_namespace",
    "product_code_raw", "product_name_raw", "canonical_id", "variant", "grade", "cut", "production_method",
    "market_level", "price_raw", "price_unit_raw", "price_twd_per_kg", "quantity_raw", "quantity_unit",
    "value_status", "origin_status", "origin_evidence_type", "origin_value", "origin_granularity",
    "evidence_ref", "join_key_type", "join_key_value", "row_hash", "retrieved_at",
)
ITEM_CSV_FIELDS = (
    "as_of_date", "requested_date", "scope_id", "canonical_id", "display_name", "commodity_family",
    "status", "products_raw", "market_codes", "market_count", "price_twd_per_kg", "volume_kg",
    "price_7d_twd_per_kg", "coverage_days_7d", "status_7d", "price_30d_twd_per_kg", "coverage_days_30d",
    "status_30d", "price_90d_twd_per_kg", "coverage_days_90d", "status_90d", "recommendation_status",
    "reason_codes", "source_id", "snapshot_hash",
)


class TaipeiAnalysisError(ValueError):
    """The Taipei scope input or published document violated its contract."""


def feed_market_name_key(name):
    # The 8066 feed spells the markets 台北一／台北二 while the verified registry uses 臺北; this
    # is the only alias accepted when matching a row to a verified market identity.
    return str(name).strip().replace("台", "臺")


def taipei_markets(market_registry):
    markets = sorted(
        (
            market
            for market in market_registry["markets"]
            if market["county_slug"] == SCOPE_ID and market["feed_source_id"] == SOURCE_ID
        ),
        key=lambda market: market["market_code"],
    )
    if not markets:
        raise TaipeiAnalysisError("official market registry has no verified Taipei 8066 market")
    return markets


def filter_taipei_rows(rows, markets):
    by_code = {market["market_code"]: market for market in markets}
    selected = []
    for row in rows:
        market = by_code.get(str(row.get("market_code")))
        if market is None or row.get("source_id") != SOURCE_ID:
            continue
        if feed_market_name_key(row.get("market_name", "")) != feed_market_name_key(market["feed_market_name"]):
            raise TaipeiAnalysisError("8066 row market name does not match the verified Taipei market " + market["market_code"])
        selected.append(row)
    return selected


def _valid(row):
    return row["avg_price_twd_per_kg"] > 0 and row["volume_kg"] > 0


def _hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _dates(start, end):
    cursor = dt.date.fromisoformat(start)
    finish = dt.date.fromisoformat(end)
    while cursor <= finish:
        yield cursor.isoformat()
        cursor += dt.timedelta(days=1)


def _schedule(calendar, market_code):
    for market in calendar.get("markets", []):
        if market.get("market_code") == market_code:
            return market["schedule_status"], market["reason"]
    return "unknown", "官方日曆未涵蓋此市場"


def _day_status(row_count, valid_count, schedule_status):
    if valid_count:
        return "calendar_feed_discrepancy" if schedule_status == "scheduled_closed" else "traded"
    if row_count:
        return "no_valid_trade"
    return "scheduled_closed" if schedule_status == "scheduled_closed" else "missing"


def market_days(taipei_rows, markets, start, end, calendar_for):
    days = []
    for date in _dates(start, end):
        calendar = calendar_for(date)
        for market in markets:
            code = market["market_code"]
            rows = [row for row in taipei_rows if row["transaction_date"] == date and str(row["market_code"]) == code]
            valid_count = sum(_valid(row) for row in rows)
            schedule_status, reason = _schedule(calendar, code)
            days.append({
                "date": date,
                "market_code": code,
                "day_status": _day_status(len(rows), valid_count, schedule_status),
                "schedule_status": schedule_status,
                "schedule_reason": reason,
                "row_count": len(rows),
                "valid_row_count": valid_count,
            })
    return days


def recommendation_gate(status, series_row):
    if status == "no_taipei_observation":
        reasons = ["NO_TAIPEI_OBSERVATION"]
    elif status == "no_valid_trade":
        reasons = ["NO_VALID_TRADE"]
    else:
        today = series_row["today"]
        windows = series_row["windows"]
        reasons = []
        if not windows["7d"]["status"] == windows["30d"]["status"] == "valid":
            reasons.append("COVERAGE_INSUFFICIENT")
        if today["market_count"] < MINIMUM_MARKET_COUNT:
            reasons.append("MARKET_COUNT_INSUFFICIENT")
        if today["quality_warnings"]:
            reasons.append("DATA_QUALITY_WARNING")
    if reasons:
        return {"status": "insufficient", "reason_codes": reasons}
    # Passing the market-data gates is not a recommendation: no versioned Taipei Buy Score exists.
    return {"status": "not_evaluated", "reason_codes": ["TAIPEI_BUY_SCORE_NOT_DEFINED"]}


def _item(item, series_row, today_rows):
    rows = [row for row in today_rows if row["canonical_id"] == item["canonical_id"]]
    valid = [row for row in rows if _valid(row)]
    status = "observed" if valid else "no_valid_trade" if rows else "no_taipei_observation"
    observed = status == "observed"
    return {
        "canonical_id": item["canonical_id"],
        "display_name": item["display_name"],
        "commodity_family": item["category"],
        "product_namespace": PRODUCT_NAMESPACE,
        "products_raw": [
            {"product_code_raw": code, "product_name_raw": name}
            for code, name in sorted({(row["crop_code"], row["crop_name_raw"]) for row in rows})
        ],
        "status": status,
        "production_method": "unknown",
        "origin_status": "unknown",
        "today": {
            "price_twd_per_kg": series_row["today"]["price_twd_per_kg"],
            "volume_kg": series_row["today"]["volume_kg"],
            "market_count": series_row["today"]["market_count"],
            "market_codes": sorted({str(row["market_code"]) for row in valid}),
            "valid_row_count": len(valid),
            "excluded_row_count": len(rows) - len(valid),
            "quality_warnings": series_row["today"]["quality_warnings"],
        } if observed else None,
        "previous_trading_day": series_row["previous_trading_day"] if observed else None,
        "windows": series_row["windows"] if observed else None,
        "range_stats": series_row["range_stats"] if observed else None,
        "volatility_7d_cv": series_row["volatility_7d_cv"] if observed else None,
        "volatility_7d_status": series_row["volatility_7d_status"] if observed else "insufficient",
        "recommendation_gate": recommendation_gate(status, series_row),
    }


def _observation(row):
    return {
        "observation_period": row["transaction_date"],
        "frequency": "daily",
        "scope_id": SCOPE_ID,
        "market_namespace": MARKET_NAMESPACE,
        "market_code": str(row["market_code"]),
        "market_name_raw": row["market_name"],
        "geography_role": "market_location",
        "source_id": row["source_id"],
        "dataset_id": DATASET_ID,
        "source_url": SOURCE_URL,
        "commodity_family": row["category"],
        "product_namespace": PRODUCT_NAMESPACE,
        "product_code_raw": row["crop_code"],
        "product_name_raw": row["crop_name_raw"],
        "canonical_id": row["canonical_id"],
        "variant": None,
        "grade": None,
        "cut": None,
        "production_method": "unknown",
        "market_level": "wholesale",
        "price_raw": row["avg_price_twd_per_kg"],
        "price_unit_raw": "元/公斤",
        "price_twd_per_kg": row["avg_price_twd_per_kg"],
        "quantity_raw": row["volume_kg"],
        "quantity_unit": "公斤",
        "value_status": "valid" if _valid(row) else "excluded_zero_price_or_volume",
        "origin_status": "unknown",
        "origin_evidence_type": None,
        "origin_value": None,
        "origin_granularity": None,
        "evidence_ref": None,
        "join_key_type": None,
        "join_key_value": None,
        "row_hash": row["row_hash"],
        "retrieved_at": row.get("fetched_at"),
    }


def build_taipei_analysis(rows, as_of_date, publication_status, items, market_registry, calendar_for, source_status):
    as_of_date = dt.date.fromisoformat(as_of_date).isoformat()
    requested_date = publication_status["requested_date"]
    if publication_status.get("resolved_date") != as_of_date:
        raise TaipeiAnalysisError("publication status does not resolve to the Taipei as-of date")
    markets = taipei_markets(market_registry)
    configured = {item["canonical_id"] for item in items}
    taipei_rows = [row for row in filter_taipei_rows(rows, markets) if row.get("canonical_id") in configured]
    # The same filtered rows feed the as-of day and every historical window.
    history = sorted(
        (row for row in taipei_rows if row["transaction_date"] <= as_of_date),
        key=lambda row: (row["transaction_date"], str(row["market_code"]), row["crop_code"], row["row_hash"]),
    )
    series = {row["canonical_id"]: row for row in build_series(aggregate(history), as_of_date)}
    today_rows = [row for row in history if row["transaction_date"] == as_of_date]
    window_start = (dt.date.fromisoformat(as_of_date) - dt.timedelta(days=WINDOWS["7d"][0] - 1)).isoformat()
    days = market_days(taipei_rows, markets, window_start, requested_date, calendar_for)
    as_of_days = {row["market_code"]: row for row in days if row["date"] == as_of_date}
    observed_market_count = sum(as_of_days[market["market_code"]]["valid_row_count"] > 0 for market in markets)
    scope_status = (
        "no_taipei_observation" if observed_market_count == 0
        else "all_markets_observed" if observed_market_count == len(markets)
        else "partial_markets_observed"
    )
    retrieved = sorted({row["fetched_at"] for row in today_rows if isinstance(row.get("fetched_at"), str)})
    document = {
        "schema_version": SCHEMA_VERSION,
        "scope_id": SCOPE_ID,
        "scope_label": SCOPE_LABEL,
        "market_level": "wholesale",
        "frequency": "daily",
        "as_of_date": as_of_date,
        "requested_date": requested_date,
        "publication_status": publication_status["status"],
        "source": {
            "source_id": SOURCE_ID,
            "dataset_id": DATASET_ID,
            "dataset_url": DATASET_URL,
            "source_url": SOURCE_URL,
            "source_status": source_status,
            "retrieved_at": retrieved[-1] if retrieved else None,
        },
        "filter_policy": FILTER_POLICY,
        "national_fallback": False,
        "snapshot_hash": _hash(history),
        "expected_market_count": len(markets),
        "observed_market_count": observed_market_count,
        "scope_status": scope_status,
        "method": {
            "price_formula": PRICE_FORMULA,
            "windows": {name: {"days": window_days, "minimum_days": minimum} for name, (window_days, minimum) in WINDOWS.items()},
            "minimum_market_count": MINIMUM_MARKET_COUNT,
            "buy_score": "not_evaluated",
        },
        "markets": [
            {
                "market_code": market["market_code"],
                "feed_market_name": market["feed_market_name"],
                "official_name": market["official_name"],
                "geography_role": "market_location",
                "evidence_url": market["evidence_url"],
                "as_of_day_status": as_of_days[market["market_code"]]["day_status"],
                "as_of_valid_row_count": as_of_days[market["market_code"]]["valid_row_count"],
            }
            for market in markets
        ],
        "market_days": days,
        "items": [_item(item, series.get(item["canonical_id"]), today_rows) for item in sorted(items, key=lambda value: value["canonical_id"])],
        "observations": [_observation(row) for row in today_rows],
    }
    return validate_taipei_analysis(document)


def _require(condition, message):
    if not condition:
        raise TaipeiAnalysisError(message)


def _iso_date(value, label):
    try:
        _require(isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value, label + " must use YYYY-MM-DD")
    except ValueError as exc:
        raise TaipeiAnalysisError(label + " must use YYYY-MM-DD") from exc
    return value


def _positive_or_none(value, label):
    _require(value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0), label + " must be positive or null")


def validate_taipei_analysis(document):
    _require(isinstance(document, dict) and set(document) == FIELDS, "Taipei analysis fields do not match the contract")
    _require(document["schema_version"] == SCHEMA_VERSION, "Taipei analysis schema_version is unsupported")
    _require(document["scope_id"] == SCOPE_ID and document["scope_label"] == SCOPE_LABEL, "Taipei analysis scope is invalid")
    _require(document["market_level"] == "wholesale" and document["frequency"] == "daily", "Taipei analysis market level or frequency is invalid")
    _require(document["national_fallback"] is False, "Taipei analysis must never fall back to nationwide rows")
    _require(document["filter_policy"] == FILTER_POLICY, "Taipei analysis filter policy is unsupported")
    as_of = _iso_date(document["as_of_date"], "as_of_date")
    requested = _iso_date(document["requested_date"], "requested_date")
    _require(as_of <= requested, "Taipei as_of_date cannot be after requested_date")
    _require(document["publication_status"] in MARKET_STATES, "publication_status must be a market status code")
    source = document["source"]
    _require(isinstance(source, dict) and set(source) == SOURCE_FIELDS, "Taipei source fields do not match the contract")
    _require((source["source_id"], source["dataset_id"], source["dataset_url"], source["source_url"]) == (SOURCE_ID, DATASET_ID, DATASET_URL, SOURCE_URL), "Taipei source lineage is invalid")
    _require(isinstance(source["source_status"], str) and source["source_status"], "Taipei source_status must be a non-empty string")
    _require(isinstance(document["snapshot_hash"], str) and document["snapshot_hash"].startswith("sha256:") and len(document["snapshot_hash"]) == 71, "Taipei snapshot_hash is invalid")
    method = document["method"]
    _require(method == {
        "price_formula": PRICE_FORMULA,
        "windows": {name: {"days": window_days, "minimum_days": minimum} for name, (window_days, minimum) in WINDOWS.items()},
        "minimum_market_count": MINIMUM_MARKET_COUNT,
        "buy_score": "not_evaluated",
    }, "Taipei method does not match the published contract")
    markets = document["markets"]
    _require(isinstance(markets, list) and markets and len(markets) == document["expected_market_count"], "Taipei markets do not match the expected market count")
    codes = []
    for market in markets:
        _require(isinstance(market, dict) and set(market) == MARKET_FIELDS, "Taipei market fields do not match the contract")
        _require(market["geography_role"] == "market_location", "a Taipei market is a market location, never an origin")
        _require(market["as_of_day_status"] in DAY_STATUSES, "Taipei market day status is invalid")
        codes.append(market["market_code"])
    _require(len(codes) == len(set(codes)), "Taipei market codes must be unique")
    observed = sum(market["as_of_valid_row_count"] > 0 for market in markets)
    _require(document["observed_market_count"] == observed, "Taipei observed market count is inconsistent")
    expected_scope = "no_taipei_observation" if observed == 0 else "all_markets_observed" if observed == len(markets) else "partial_markets_observed"
    _require(document["scope_status"] == expected_scope, "Taipei scope status is inconsistent")
    for day in document["market_days"]:
        _require(isinstance(day, dict) and set(day) == DAY_FIELDS, "Taipei market day fields do not match the contract")
        _require(day["market_code"] in codes and day["day_status"] in DAY_STATUSES and day["schedule_status"] in SCHEDULE_STATUSES, "Taipei market day is invalid")
        _require(day["day_status"] == _day_status(day["row_count"], day["valid_row_count"], day["schedule_status"]), "Taipei market day status is inconsistent")
    _require({(day["date"], day["market_code"]) for day in document["market_days"]} >= {(as_of, code) for code in codes}, "Taipei market days must cover the as-of date")
    _require(isinstance(document["items"], list) and document["items"], "Taipei analysis must list the configured items")
    item_ids = [item.get("canonical_id") if isinstance(item, dict) else None for item in document["items"]]
    _require(len(item_ids) == len(set(item_ids)), "Taipei item canonical ids must be unique")
    for item in document["items"]:
        _require(isinstance(item, dict) and set(item) == ITEM_FIELDS, "Taipei item fields do not match the contract")
        _require(item["status"] in ITEM_STATUSES and item["commodity_family"] in COMMODITY_FAMILIES, "Taipei item status or commodity family is invalid")
        _require(item["production_method"] == "unknown" and item["origin_status"] == "unknown", "Taipei items must not claim a production method or origin")
        gate = item["recommendation_gate"]
        _require(isinstance(gate, dict) and gate.get("status") in GATE_STATUSES and gate.get("reason_codes"), "Taipei recommendation gate is invalid")
        if item["status"] == "observed":
            today = item["today"]
            _positive_or_none(today["price_twd_per_kg"], "Taipei item price")
            _require(today["price_twd_per_kg"] is not None and set(today["market_codes"]) <= set(codes), "an observed Taipei item needs a price from verified Taipei markets")
            _require(today["market_count"] == len(today["market_codes"]), "Taipei item market count is inconsistent")
            if today["market_count"] < MINIMUM_MARKET_COUNT:
                _require(gate["status"] == "insufficient", "a single-market Taipei item cannot pass the recommendation gate")
        else:
            _require(all(item[key] is None for key in ("today", "previous_trading_day", "windows", "range_stats", "volatility_7d_cv")), "an unobserved Taipei item must not publish prices")
            _require(gate["status"] == "insufficient", "an unobserved Taipei item cannot pass the recommendation gate")
    for observation in document["observations"]:
        _require(isinstance(observation, dict) and set(observation) == set(OBSERVATION_FIELDS), "Taipei observation fields do not match the contract")
        _require(observation["observation_period"] == as_of and observation["market_code"] in codes, "Taipei observation is outside the as-of Taipei scope")
        _require(observation["geography_role"] == "market_location" and observation["origin_status"] == "unknown" and observation["production_method"] == "unknown", "Taipei observation must not claim an origin or production method")
        _require((observation["source_id"], observation["dataset_id"], observation["market_level"], observation["frequency"]) == (SOURCE_ID, DATASET_ID, "wholesale", "daily"), "Taipei observation lineage is invalid")
        _require(observation["value_status"] == ("valid" if observation["price_twd_per_kg"] > 0 and observation["quantity_raw"] > 0 else "excluded_zero_price_or_volume"), "Taipei observation value status is inconsistent")
    return document


def _csv_text(fieldnames, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row[key] is None else row[key] for key in fieldnames})
    return buffer.getvalue()


def _item_csv_row(document, item):
    today = item["today"] or {}
    windows = item["windows"] or {}
    row = {
        "as_of_date": document["as_of_date"],
        "requested_date": document["requested_date"],
        "scope_id": document["scope_id"],
        "canonical_id": item["canonical_id"],
        "display_name": item["display_name"],
        "commodity_family": item["commodity_family"],
        "status": item["status"],
        "products_raw": "|".join(product["product_code_raw"] + ":" + product["product_name_raw"] for product in item["products_raw"]),
        "market_codes": "|".join(today.get("market_codes", [])),
        "market_count": today.get("market_count"),
        "price_twd_per_kg": today.get("price_twd_per_kg"),
        "volume_kg": today.get("volume_kg"),
        "recommendation_status": item["recommendation_gate"]["status"],
        "reason_codes": "|".join(item["recommendation_gate"]["reason_codes"]),
        "source_id": document["source"]["source_id"],
        "snapshot_hash": document["snapshot_hash"],
    }
    for name in WINDOWS:
        window = windows.get(name) or {}
        row["price_" + name + "_twd_per_kg"] = window.get("price_twd_per_kg")
        row["coverage_days_" + name] = window.get("coverage_days")
        row["status_" + name] = window.get("status")
    return row


def taipei_csv_documents(document):
    return {
        "items.csv": _csv_text(ITEM_CSV_FIELDS, [_item_csv_row(document, item) for item in document["items"]]),
        "observations.csv": _csv_text(OBSERVATION_FIELDS, document["observations"]),
    }
