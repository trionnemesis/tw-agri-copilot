import datetime as dt
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .market import RETRYABLE_STATUS, UpstreamUnavailable


REGISTRY_URL = "https://data.moa.gov.tw/Service/OpenData/Resume/ResumeData_Plus.aspx"
REGISTRY_SOURCE_PAGE = "https://data.moa.gov.tw/open_detail.aspx?id=063"
REGISTRY_LICENSE_URL = "https://data.gov.tw/license"
REGISTRY_SOURCE_ID = "moa_traceability_7556"
REGISTRY_SOURCE_ROLE = "authoritative_registry"
REGISTRY_ADAPTER_VERSION = "1.0.0"
REGISTRY_SCHEMA_VERSION = "7556-v1"
TRACEABILITY_WARNING = "此為同品項的公開產銷履歷紀錄，非本日市場成交來源證明。"
REQUIRED_REGISTRY_FIELDS = frozenset(
    {
        "Tracecode",
        "Producer",
        "OrgID",
        "ProductName",
        "Place",
        "FarmerName",
        "PackDate",
        "CertificationName",
        "ValidDate",
        "StoreInfo",
        "OperationDetail",
        "ResumeDetail",
        "ProcessDetail",
        "CertificateDetail",
        "LandSecNO",
        "ParentTraceCode",
        "Log_UpdateTime",
        "TraceCodelist",
    }
)


def _text(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _date(value):
    text = _text(value)
    if text is None:
        return None
    candidate = text[:10].replace("/", "-")
    try:
        return dt.date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def _coarse_place(value):
    text = _text(value)
    if text is None:
        return None
    for marker in ("縣", "市"):
        if marker in text:
            return text[: text.index(marker) + 1]
    return None


def _content_hash(rows):
    encoded = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validity(valid_date, as_of_date):
    if valid_date is None:
        return "unknown"
    return "active" if valid_date >= as_of_date else "expired"


def _mapping(items):
    by_id = {item["canonical_id"]: item for item in items}
    by_name = {}
    for item in items:
        names = [
            item["display_name"],
            *item.get("aliases", []),
            *item.get("traceability_names", []),
        ]
        for name in names:
            text = _text(name)
            if text in by_name and by_name[text] != item["canonical_id"]:
                raise ValueError("traceability name maps to multiple configured items")
            by_name[text] = item["canonical_id"]
    return by_id, by_name


def normalize_registry(
    raw_rows,
    items,
    as_of_date,
    retrieved_at,
    *,
    source_status="live",
    content_hash=None,
    allow_canonical_hint=False,
):
    as_of_date = dt.date.fromisoformat(as_of_date).isoformat()
    if not isinstance(raw_rows, list) or not raw_rows:
        raise UpstreamUnavailable("traceability registry returned no rows")
    by_id, by_name = _mapping(items)
    output = []
    seen = {}
    missing_tracecode_count = 0
    unmapped_record_count = 0
    duplicate_count = 0
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("traceability registry row must be an object")
        tracecode = _text(raw.get("Tracecode"))
        if tracecode is None:
            missing_tracecode_count += 1
            continue
        canonical_id = None
        if allow_canonical_hint and raw.get("canonical_id") in by_id:
            canonical_id = raw["canonical_id"]
        if canonical_id is None:
            canonical_id = by_name.get(_text(raw.get("ProductName")))
        if canonical_id is None:
            unmapped_record_count += 1
            continue
        valid_date = _date(raw.get("ValidDate"))
        row = {
            "schema_version": "2.0",
            "record_type": "traceability_registry_lot",
            "tracecode": tracecode,
            "producer": _text(raw.get("Producer")),
            "org_id": _text(raw.get("OrgID")),
            "product_name_raw": _text(raw.get("ProductName"))
            or by_id[canonical_id]["display_name"],
            "canonical_id": canonical_id,
            "place": _coarse_place(raw.get("Place")),
            "pack_date": _date(raw.get("PackDate")),
            "certification_name": _text(raw.get("CertificationName")),
            "valid_date": valid_date,
            "certification_status": _validity(valid_date, as_of_date),
            "source_updated_date": _date(raw.get("Log_UpdateTime")),
            "source_id": REGISTRY_SOURCE_ID,
            "source_role": REGISTRY_SOURCE_ROLE,
            "source_status": source_status,
            "retrieved_at": retrieved_at,
            "source_url": REGISTRY_SOURCE_PAGE,
            "semantic_warning": TRACEABILITY_WARNING,
        }
        previous = seen.get(tracecode)
        if previous is not None:
            if previous != row:
                raise ValueError("traceability registry has a conflicting tracecode")
            duplicate_count += 1
            continue
        seen[tracecode] = row
        output.append(row)
    output.sort(key=lambda row: (row["canonical_id"], row["tracecode"]))
    profile = {
        "schema_version": "1.0",
        "record_type": "traceability_registry_profile",
        "source_id": REGISTRY_SOURCE_ID,
        "source_role": REGISTRY_SOURCE_ROLE,
        "source_url": REGISTRY_SOURCE_PAGE,
        "api_url": REGISTRY_URL,
        "license_url": REGISTRY_LICENSE_URL,
        "source_status": source_status,
        "source_schema_version": REGISTRY_SCHEMA_VERSION,
        "adapter_version": REGISTRY_ADAPTER_VERSION,
        "as_of_date": as_of_date,
        "retrieved_at": retrieved_at,
        "content_hash": content_hash or _content_hash(raw_rows),
        "raw_record_count": len(raw_rows),
        "published_record_count": len(output),
        "active_record_count": sum(
            row["certification_status"] == "active" for row in output
        ),
        "expired_record_count": sum(
            row["certification_status"] == "expired" for row in output
        ),
        "unknown_validity_count": sum(
            row["certification_status"] == "unknown" for row in output
        ),
        "operator_count": len(
            {row["org_id"] for row in output if row.get("org_id")}
        ),
        "mapped_item_count": len({row["canonical_id"] for row in output}),
        "unmapped_record_count": unmapped_record_count,
        "missing_tracecode_count": missing_tracecode_count,
        "duplicate_count": duplicate_count,
        "privacy_policy": "coarse_county_and_business_identity_only",
    }
    validate_registry_snapshot(output, profile)
    return output, profile


def validate_registry_snapshot(rows, profile):
    if not isinstance(rows, list) or not isinstance(profile, dict):
        raise ValueError("traceability registry snapshot must contain records and profile")
    required_profile = {
        "schema_version",
        "record_type",
        "source_id",
        "source_role",
        "source_url",
        "api_url",
        "source_status",
        "source_schema_version",
        "adapter_version",
        "as_of_date",
        "retrieved_at",
        "content_hash",
        "raw_record_count",
        "published_record_count",
        "active_record_count",
        "operator_count",
        "mapped_item_count",
    }
    if not required_profile.issubset(profile):
        raise ValueError("traceability registry profile is incomplete")
    if profile["source_id"] != REGISTRY_SOURCE_ID:
        raise ValueError("traceability registry source_id is invalid")
    if profile["source_role"] != REGISTRY_SOURCE_ROLE:
        raise ValueError("traceability registry source role is invalid")
    if profile["source_status"] not in ("fixture", "live", "stale"):
        raise ValueError("traceability registry source status is invalid")
    if not str(profile["content_hash"]).startswith("sha256:"):
        raise ValueError("traceability registry content hash is invalid")
    if profile["published_record_count"] != len(rows):
        raise ValueError("traceability registry profile count does not match records")
    forbidden = {
        "FarmerName",
        "StoreInfo",
        "OperationDetail",
        "ResumeDetail",
        "ProcessDetail",
        "CertificateDetail",
        "LandSecNO",
        "ParentTraceCode",
        "TraceCodelist",
        "farmer_name",
        "store_info",
        "land_section_number",
    }
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("record_type") != "traceability_registry_lot":
            raise ValueError("traceability registry record type is invalid")
        if forbidden.intersection(row):
            raise ValueError("traceability public record contains a forbidden field")
        if not row.get("tracecode") or row["tracecode"] in identities:
            raise ValueError("traceability registry tracecode must be unique")
        identities.add(row["tracecode"])
        if row.get("source_id") != REGISTRY_SOURCE_ID:
            raise ValueError("traceability registry row source is invalid")
        if row.get("certification_status") not in ("active", "expired", "unknown"):
            raise ValueError("traceability certification status is invalid")
        place = row.get("place")
        if place and not place.endswith(("縣", "市")):
            raise ValueError("traceability place is not coarse-grained")
    return profile


def _read_page(url, opener, timeout, attempts, backoff_seconds, sleeper):
    last_error = None
    for attempt in range(attempts):
        try:
            response = opener(url, timeout=timeout)
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
            if status != 200:
                if status in RETRYABLE_STATUS:
                    raise RuntimeError(f"retryable upstream HTTP status {status}")
                raise ValueError(f"traceability upstream HTTP status {status}")
            if not body.strip() or body.lstrip().startswith(b"<"):
                raise RuntimeError("traceability upstream response is empty or HTML")
            if "json" not in content_type.lower():
                raise RuntimeError("traceability upstream response is not JSON")
            return body
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS:
                raise ValueError(f"traceability upstream HTTP status {exc.code}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, RuntimeError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            sleeper(backoff_seconds * (2**attempt))
    raise UpstreamUnavailable(
        f"traceability upstream unavailable after {attempts} attempts"
    ) from last_error


def fetch_registry(
    top=1000,
    max_pages=200,
    opener=urllib.request.urlopen,
    timeout=60,
    attempts=3,
    backoff_seconds=1.0,
    sleeper=time.sleep,
    urls=None,
):
    if top < 1 or max_pages < 1 or attempts < 1:
        raise ValueError("traceability fetch bounds must be positive")
    all_rows = []
    page_signatures = set()
    for page in range(max_pages):
        query = urllib.parse.urlencode({"$top": top, "$skip": page * top})
        url = REGISTRY_URL + "?" + query
        if urls is not None:
            urls.append(url)
        body = _read_page(
            url, opener, timeout, attempts, backoff_seconds, sleeper
        )
        try:
            rows = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("traceability upstream returned malformed JSON") from exc
        if not isinstance(rows, list):
            raise ValueError("traceability upstream JSON must be a collection")
        if len(rows) > top:
            raise ValueError("traceability upstream ignored the requested page bound")
        for row in rows:
            if not isinstance(row, dict) or not REQUIRED_REGISTRY_FIELDS.issubset(row):
                raise ValueError("traceability upstream row schema drift")
        if not rows:
            if page == 0:
                raise UpstreamUnavailable("traceability registry returned no rows")
            break
        signature = hashlib.sha256(body).hexdigest()
        if signature in page_signatures:
            raise ValueError("duplicate traceability pagination page")
        page_signatures.add(signature)
        all_rows.extend(rows)
        if len(rows) < top:
            break
    else:
        raise UpstreamUnavailable("maximum traceability pages reached")
    return all_rows, _content_hash(all_rows)


def filter_traceability(raw_rows, items, fetched_at="fixture", as_of_date="2026-08-25"):
    rows, _profile = normalize_registry(
        raw_rows,
        items,
        as_of_date,
        fetched_at,
        source_status="fixture",
        allow_canonical_hint=True,
    )
    return rows
