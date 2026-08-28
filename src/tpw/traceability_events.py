import datetime as dt
import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

from .market import RETRYABLE_STATUS, UpstreamUnavailable


EVENT_URL = "https://data.moa.gov.tw/Service/OpenData/FromM/TAPData.aspx"
EVENT_SOURCE_PAGE = "https://data.moa.gov.tw/open_detail.aspx?id=H44"
EVENT_LICENSE_URL = "https://data.gov.tw/license"
EVENT_SOURCE_ID = "moa_traceability_market_h44"
EVENT_SOURCE_ROLE = "authoritative_market_event"
EVENT_DATASET_SEMANTICS = "traceability_market_event"
EVENT_ADAPTER_VERSION = "1.0.0"
EVENT_SCHEMA_VERSION = "H44-v1"
EVENT_WARNING = (
    "H44 是獨立的產銷履歷／有機農產品市場交易事件；溯源代號不等於 7556 履歷碼，"
    "且事件不納入行情彙總或 Buy Score。"
)
REQUIRED_EVENT_FIELDS = frozenset(
    {
        "交易日期",
        "作物代號",
        "作物名稱",
        "市場代號",
        "市場名稱",
        "交易金額_元",
        "交易量_公斤",
        "溯源代號",
    }
)


def _text(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _event_date(value):
    text = _text(value)
    if text is None:
        raise ValueError("traceability market event date is missing")
    if len(text) == 8 and text.isdigit():
        candidate = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    else:
        candidate = text[:10].replace("/", "-")
    try:
        return dt.date.fromisoformat(candidate).isoformat()
    except ValueError as exc:
        raise ValueError("traceability market event date is invalid") from exc


def _number(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"traceability market event {label} is invalid")
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise ValueError(f"traceability market event {label} is invalid") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"traceability market event {label} is invalid")
    return int(number) if number.is_integer() else number


def _content_hash(rows):
    encoded = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _event_id(raw):
    identity = {field: raw.get(field) for field in sorted(REQUIRED_EVENT_FIELDS)}
    encoded = json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "h44:" + hashlib.sha256(encoded).hexdigest()


def _mapping(items):
    by_code = {}
    by_name = {}
    for item in items:
        for code in item.get("market_crop_codes", []):
            code = _text(code)
            if code in by_code and by_code[code] != item["canonical_id"]:
                raise ValueError("market crop code maps to multiple configured items")
            by_code[code] = item["canonical_id"]
        for name in (
            item["display_name"],
            *item.get("aliases", []),
            *item.get("traceability_names", []),
        ):
            name = _text(name)
            if name in by_name and by_name[name] != item["canonical_id"]:
                raise ValueError("market event name maps to multiple configured items")
            by_name[name] = item["canonical_id"]
    return by_code, by_name


def normalize_market_events(
    raw_rows,
    items,
    requested_date,
    retrieved_at,
    *,
    source_status="live",
    content_hash=None,
):
    requested_date = dt.date.fromisoformat(requested_date).isoformat()
    if not isinstance(raw_rows, list) or not raw_rows:
        raise UpstreamUnavailable("traceability market events returned no rows")
    by_code, by_name = _mapping(items)
    output = []
    seen = set()
    duplicate_count = 0
    unmapped_record_count = 0
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("traceability market event row must be an object")
        crop_code = _text(raw.get("作物代號"))
        crop_name = _text(raw.get("作物名稱"))
        market_code = _text(raw.get("市場代號"))
        market_name = _text(raw.get("市場名稱"))
        provenance_code = _text(raw.get("溯源代號"))
        if not all((crop_code, crop_name, market_code, market_name, provenance_code)):
            raise ValueError("traceability market event identity is incomplete")
        event_date = _event_date(raw.get("交易日期"))
        if event_date != requested_date:
            raise ValueError("traceability market event is outside the requested date")
        event_id = _event_id(raw)
        if event_id in seen:
            duplicate_count += 1
            continue
        seen.add(event_id)
        canonical_id = by_code.get(crop_code) or by_name.get(crop_name)
        if canonical_id is None:
            unmapped_record_count += 1
            continue
        output.append(
            {
                "schema_version": "1.0",
                "record_type": "traceability_market_event",
                "event_id": event_id,
                "transaction_date": event_date,
                "market_code": market_code,
                "market_name": market_name,
                "crop_code": crop_code,
                "crop_name_raw": crop_name,
                "canonical_id": canonical_id,
                "transaction_amount_twd": _number(raw.get("交易金額_元"), "amount"),
                "transaction_volume_kg": _number(raw.get("交易量_公斤"), "volume"),
                "traceability_class_code": provenance_code,
                "dataset_semantics": EVENT_DATASET_SEMANTICS,
                "source_id": EVENT_SOURCE_ID,
                "source_role": EVENT_SOURCE_ROLE,
                "source_status": source_status,
                "retrieved_at": retrieved_at,
                "source_url": EVENT_SOURCE_PAGE,
                "eligible_for_market_aggregate": False,
                "affects_buy_score": False,
                "semantic_warning": EVENT_WARNING,
            }
        )
    output.sort(
        key=lambda row: (
            row["transaction_date"],
            row["canonical_id"],
            row["market_code"],
            row["crop_code"],
            row["event_id"],
        )
    )
    profile = {
        "schema_version": "1.0",
        "record_type": "traceability_market_event_profile",
        "source_id": EVENT_SOURCE_ID,
        "source_role": EVENT_SOURCE_ROLE,
        "dataset_semantics": EVENT_DATASET_SEMANTICS,
        "source_url": EVENT_SOURCE_PAGE,
        "api_url": EVENT_URL,
        "license_url": EVENT_LICENSE_URL,
        "source_status": source_status,
        "source_schema_version": EVENT_SCHEMA_VERSION,
        "adapter_version": EVENT_ADAPTER_VERSION,
        "requested_date": requested_date,
        "retrieved_at": retrieved_at,
        "content_hash": content_hash or _content_hash(raw_rows),
        "raw_record_count": len(raw_rows),
        "published_record_count": len(output),
        "mapped_item_count": len({row["canonical_id"] for row in output}),
        "market_count": len({row["market_code"] for row in output}),
        "unmapped_record_count": unmapped_record_count,
        "duplicate_count": duplicate_count,
        "eligible_for_market_aggregate": False,
        "affects_buy_score": False,
    }
    validate_market_event_snapshot(output, profile)
    return output, profile


def validate_market_event_snapshot(rows, profile):
    if not isinstance(rows, list) or not isinstance(profile, dict):
        raise ValueError("traceability market event snapshot must contain records and profile")
    required_profile = {
        "schema_version",
        "record_type",
        "source_id",
        "source_role",
        "dataset_semantics",
        "source_url",
        "api_url",
        "source_status",
        "source_schema_version",
        "adapter_version",
        "requested_date",
        "retrieved_at",
        "content_hash",
        "raw_record_count",
        "published_record_count",
        "mapped_item_count",
        "market_count",
        "eligible_for_market_aggregate",
        "affects_buy_score",
    }
    if not required_profile.issubset(profile):
        raise ValueError("traceability market event profile is incomplete")
    if profile["source_id"] != EVENT_SOURCE_ID:
        raise ValueError("traceability market event source_id is invalid")
    if profile["source_role"] != EVENT_SOURCE_ROLE:
        raise ValueError("traceability market event source role is invalid")
    if profile["dataset_semantics"] != EVENT_DATASET_SEMANTICS:
        raise ValueError("traceability market event semantics are invalid")
    if profile["source_status"] not in ("fixture", "live", "stale"):
        raise ValueError("traceability market event source status is invalid")
    if not str(profile["content_hash"]).startswith("sha256:"):
        raise ValueError("traceability market event content hash is invalid")
    if profile["published_record_count"] != len(rows):
        raise ValueError("traceability market event profile count does not match records")
    if profile["eligible_for_market_aggregate"] is not False:
        raise ValueError("traceability market event profile cannot enter market aggregates")
    if profile["affects_buy_score"] is not False:
        raise ValueError("traceability market event profile cannot affect Buy Score")
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("record_type") != "traceability_market_event":
            raise ValueError("traceability market event record type is invalid")
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id.startswith("h44:") or event_id in identities:
            raise ValueError("traceability market event identity is invalid")
        identities.add(event_id)
        if row.get("source_id") != EVENT_SOURCE_ID or row.get("source_role") != EVENT_SOURCE_ROLE:
            raise ValueError("traceability market event source is invalid")
        if row.get("source_status") != profile["source_status"]:
            raise ValueError("traceability market event row status does not match profile")
        if row.get("dataset_semantics") != EVENT_DATASET_SEMANTICS:
            raise ValueError("traceability market event row semantics are invalid")
        if row.get("eligible_for_market_aggregate") is not False:
            raise ValueError("traceability market event cannot enter market aggregates")
        if row.get("affects_buy_score") is not False:
            raise ValueError("traceability market event cannot affect Buy Score")
        if row.get("transaction_date") != profile["requested_date"]:
            raise ValueError("traceability market event date does not match profile")
        for field in ("transaction_amount_twd", "transaction_volume_kg"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError("traceability market event numeric field is invalid")
    if profile["mapped_item_count"] != len({row["canonical_id"] for row in rows}):
        raise ValueError("traceability market event mapped item count is invalid")
    if profile["market_count"] != len({row["market_code"] for row in rows}):
        raise ValueError("traceability market event market count is invalid")
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
                raise ValueError(f"traceability market event upstream HTTP status {status}")
            if not body.strip() or body.lstrip().startswith(b"<"):
                raise RuntimeError("traceability market event response is empty or HTML")
            if "json" not in content_type.lower():
                raise RuntimeError("traceability market event response is not JSON")
            return body
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS:
                raise ValueError(
                    f"traceability market event upstream HTTP status {exc.code}"
                ) from exc
            last_error = exc
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError,
            RuntimeError,
        ) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            sleeper(backoff_seconds * (2**attempt))
    raise UpstreamUnavailable(
        f"traceability market event upstream unavailable after {attempts} attempts"
    ) from last_error


def fetch_market_events(
    requested_date,
    top=1000,
    max_pages=200,
    opener=urllib.request.urlopen,
    timeout=60,
    attempts=3,
    backoff_seconds=1.0,
    sleeper=time.sleep,
    urls=None,
):
    requested_date = dt.date.fromisoformat(requested_date).isoformat()
    if top < 1 or max_pages < 1 or attempts < 1:
        raise ValueError("traceability market event fetch bounds must be positive")
    compact_date = requested_date.replace("-", "")
    all_rows = []
    page_signatures = set()
    for page in range(max_pages):
        query = urllib.parse.urlencode(
            {
                "StartDate": compact_date,
                "EndDate": compact_date,
                "$top": top,
                "$skip": page * top,
            }
        )
        url = EVENT_URL + "?" + query
        if urls is not None:
            urls.append(url)
        body = _read_page(
            url, opener, timeout, attempts, backoff_seconds, sleeper
        )
        try:
            page_rows = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("traceability market event upstream returned malformed JSON") from exc
        if not isinstance(page_rows, list):
            raise ValueError("traceability market event upstream JSON must be an array")
        if not page_rows:
            if page == 0:
                raise UpstreamUnavailable("traceability market event upstream returned no rows")
            break
        for row in page_rows:
            if not isinstance(row, dict) or not REQUIRED_EVENT_FIELDS.issubset(row):
                raise ValueError("traceability market event upstream schema drift")
        signature = _content_hash(page_rows)
        if signature in page_signatures:
            raise ValueError("traceability market event upstream repeated a page")
        page_signatures.add(signature)
        all_rows.extend(page_rows)
        if len(page_rows) < top:
            break
    else:
        raise ValueError("traceability market event pagination exceeded safety bound")
    return all_rows, _content_hash(all_rows)
