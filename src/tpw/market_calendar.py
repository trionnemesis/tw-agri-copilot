"""Official market calendar fixtures and controlled TAPMC refresh support."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import tempfile
import urllib.error
import urllib.request


SCHEDULE_STATUSES = {
    "expected_open",
    "scheduled_closed",
    "exceptional_open",
    "unknown",
}
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


class CalendarUnavailable(ValueError):
    """A transport or availability failure that must not replace the fixture."""


class CalendarContractError(ValueError):
    """A document, parser, or normalized-calendar contract failure."""


def _date(value: str, field: str = "calendar_date") -> dt.date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CalendarContractError(f"{field} must use YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise CalendarContractError(f"{field} must be a real date") from exc


def _datetime(value: str, field: str = "retrieved_at") -> dt.datetime:
    if not isinstance(value, str):
        raise CalendarContractError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CalendarContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CalendarContractError(f"{field} must include a timezone")
    return parsed


def _year_dates(year: int) -> list[dt.date]:
    first = dt.date(year, 1, 1)
    stop = dt.date(year + 1, 1, 1)
    return [first + dt.timedelta(days=offset) for offset in range((stop - first).days)]


def _hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def load_calendar_config(root: pathlib.Path) -> dict:
    path = pathlib.Path(root) / "config/market-calendar.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalendarContractError("market calendar config must be valid JSON") from exc
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("sources"), list):
        raise CalendarContractError("invalid market calendar config")
    if len(payload["sources"]) != 1:
        raise CalendarContractError("calendar config must define exactly one source")
    source = payload["sources"][0]
    if source.get("source_role") != "calendar" or not source.get("source_id"):
        raise CalendarContractError("calendar source role or id is invalid")
    markets = source.get("market_codes")
    if not isinstance(markets, list) or not markets:
        raise CalendarContractError("calendar source must define market codes")
    codes = []
    for market in markets:
        if set(market) != {"market_code", "market_name"}:
            raise CalendarContractError("invalid calendar market registry entry")
        if not all(isinstance(market[key], str) and market[key].strip() for key in market):
            raise CalendarContractError("calendar market fields must be non-empty strings")
        codes.append(market["market_code"])
    if len(codes) != len(set(codes)):
        raise CalendarContractError("duplicate calendar market code")
    documents = source.get("documents")
    if not isinstance(documents, list) or not documents:
        raise CalendarContractError("calendar source must define documents")
    years = []
    for document in documents:
        required = {
            "calendar_year",
            "roc_year",
            "calendar_version",
            "document_url",
            "expected_content_hash",
            "expected_closed_days",
            "expected_trading_days",
            "parser_version",
            "normalized_path",
        }
        if set(document) != required:
            raise CalendarContractError("invalid calendar document config fields")
        year = document["calendar_year"]
        if not isinstance(year, int) or year < 2000 or document["roc_year"] != year - 1911:
            raise CalendarContractError("calendar year mapping is invalid")
        if not str(document["document_url"]).startswith("https://www.tapmc.com.tw/"):
            raise CalendarContractError("calendar document must use the official TAPMC HTTPS host")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(document["expected_content_hash"])):
            raise CalendarContractError("invalid expected calendar content hash")
        if document["expected_closed_days"] + document["expected_trading_days"] != len(_year_dates(year)):
            raise CalendarContractError("calendar day counts do not cover the year")
        normalized = pathlib.PurePosixPath(document["normalized_path"])
        if normalized.is_absolute() or ".." in normalized.parts or normalized.parts[:2] != ("data", "market-calendar"):
            raise CalendarContractError("normalized calendar path is unsafe")
        years.append(year)
    if len(years) != len(set(years)):
        raise CalendarContractError("duplicate calendar year")
    return payload


def _source_and_document(config: dict, year: int) -> tuple[dict, dict | None]:
    source = config["sources"][0]
    document = next(
        (item for item in source["documents"] if item["calendar_year"] == year),
        None,
    )
    return source, document


def validate_calendar_payload(payload: dict) -> dict:
    required = {
        "schema_version",
        "source_id",
        "source_role",
        "document_url",
        "calendar_year",
        "calendar_version",
        "retrieved_at",
        "content_hash",
        "parser_version",
        "market_codes",
        "closed_day_count",
        "trading_day_count",
        "entries",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise CalendarContractError("normalized calendar fields do not match schema")
    if payload["schema_version"] != "1.0" or payload["source_role"] != "calendar":
        raise CalendarContractError("normalized calendar version or role is invalid")
    if not isinstance(payload["source_id"], str) or not payload["source_id"]:
        raise CalendarContractError("normalized calendar source id is invalid")
    if not str(payload["document_url"]).startswith("https://www.tapmc.com.tw/"):
        raise CalendarContractError("normalized calendar document URL is invalid")
    if not isinstance(payload["calendar_year"], int):
        raise CalendarContractError("calendar_year must be an integer")
    year = payload["calendar_year"]
    if not isinstance(payload["calendar_version"], str) or not payload["calendar_version"]:
        raise CalendarContractError("calendar_version must be non-empty")
    _datetime(payload["retrieved_at"])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(payload["content_hash"])):
        raise CalendarContractError("normalized calendar content hash is invalid")
    if not isinstance(payload["parser_version"], str) or not payload["parser_version"]:
        raise CalendarContractError("parser_version must be non-empty")
    markets = payload["market_codes"]
    if not isinstance(markets, list) or not markets:
        raise CalendarContractError("normalized calendar market registry is empty")
    market_codes = []
    for market in markets:
        if not isinstance(market, dict) or set(market) != {"market_code", "market_name"}:
            raise CalendarContractError("normalized calendar market entry is invalid")
        if not all(isinstance(market[key], str) and market[key] for key in market):
            raise CalendarContractError("normalized calendar market fields are invalid")
        market_codes.append(market["market_code"])
    if len(market_codes) != len(set(market_codes)):
        raise CalendarContractError("normalized calendar contains duplicate markets")
    entries = payload["entries"]
    if not isinstance(entries, list):
        raise CalendarContractError("normalized calendar entries must be a list")
    expected_dates = [day.isoformat() for day in _year_dates(year)]
    actual_dates = []
    closed_count = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"calendar_date", "schedule_status", "reason"}:
            raise CalendarContractError("normalized calendar entry fields are invalid")
        date = _date(entry["calendar_date"])
        if date.year != year:
            raise CalendarContractError("normalized calendar entry is outside calendar_year")
        if entry["schedule_status"] not in SCHEDULE_STATUSES - {"unknown"}:
            raise CalendarContractError("normalized calendar schedule status is invalid")
        if not isinstance(entry["reason"], str) or not entry["reason"].strip():
            raise CalendarContractError("normalized calendar reason must be non-empty")
        actual_dates.append(entry["calendar_date"])
        closed_count += entry["schedule_status"] == "scheduled_closed"
    if actual_dates != expected_dates:
        raise CalendarContractError("normalized calendar must contain every date exactly once in order")
    if payload["closed_day_count"] != closed_count:
        raise CalendarContractError("normalized calendar closed-day count is inconsistent")
    if payload["trading_day_count"] != len(entries) - closed_count:
        raise CalendarContractError("normalized calendar trading-day count is inconsistent")
    return payload


def _normalize_pdf_text(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")")


def _extract_groups(segment: str, year: int) -> list[list[dt.date]]:
    pattern = re.compile(
        r"(?:(\d{1,2})月(\d{1,2})日至(\d{1,2})月(\d{1,2})日)"
        r"|(?:(\d{1,2})月(\d{1,2}(?:、\d{1,2})*)日)"
    )
    groups = []
    for match in pattern.finditer(segment):
        if match.group(1):
            start = dt.date(year, int(match.group(1)), int(match.group(2)))
            end = dt.date(year, int(match.group(3)), int(match.group(4)))
            if end < start or (end - start).days > 14:
                raise CalendarContractError("calendar date range is invalid")
            groups.append([start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)])
        else:
            month = int(match.group(5))
            groups.append([dt.date(year, month, int(day)) for day in match.group(6).split("、")])
    return groups


def parse_tapmc_calendar_text(text: str, document: dict) -> list[dict]:
    """Parse the approved 115-year footnote rules into a complete 2026 schedule."""

    if not isinstance(text, str) or not text.strip():
        raise CalendarContractError("calendar PDF parser returned no text")
    normalized = _normalize_pdf_text(text)
    required_markers = (
        "115年度臺北市果菜批發市場休市日程表",
        "休市日安排原則為逢週一休市",
        "取消休市日者，計有",
        "調整至2月26日補休",
        "週四為休市日",
    )
    if any(marker not in normalized for marker in required_markers):
        raise CalendarContractError("calendar PDF format or footnote rules changed")
    year = document["calendar_year"]
    if year != 2026 or document["parser_version"] != "tapmc-calendar-v1":
        raise CalendarContractError("no parser is registered for this calendar document")
    try:
        special_segment = normalized.split("包括：", 1)[1].split("。二、", 1)[0]
        open_segment = normalized.split("取消休市日者，計有", 1)[1].split("。另", 1)[0]
        makeup_segment = normalized.split("調整至", 1)[1].split("補休", 1)[0]
        thursday_segment = normalized.split("增加", 1)[1].split("週四為休市日", 1)[0]
    except (IndexError, ValueError) as exc:
        raise CalendarContractError("calendar PDF rule sections are incomplete") from exc
    special_groups = _extract_groups(special_segment, year)
    exceptional_groups = _extract_groups(open_segment, year)
    makeup_groups = _extract_groups(makeup_segment, year)
    thursday_groups = _extract_groups(thursday_segment, year)
    if [len(special_groups), len(exceptional_groups), len(makeup_groups), len(thursday_groups)] != [7, 5, 1, 17]:
        raise CalendarContractError("calendar PDF date groups changed")
    if any(len(group) != 1 for group in exceptional_groups + makeup_groups + thursday_groups):
        raise CalendarContractError("calendar PDF exceptional date shape changed")
    special_labels = (
        "春節初一至初五休市",
        "正月初九天公生（禁屠日）休市",
        "元宵節後循例休市",
        "清明節循例休市",
        "端午節後循例休市",
        "中元節後循例休市",
        "中秋節後循例休市",
    )
    special_reasons = {
        day: label
        for group, label in zip(special_groups, special_labels, strict=True)
        for day in group
    }
    exceptional = {group[0] for group in exceptional_groups}
    makeup = {group[0] for group in makeup_groups}
    thursdays = {group[0] for group in thursday_groups}
    if any(day.weekday() != 0 for day in exceptional):
        raise CalendarContractError("calendar exceptional-open dates must be Mondays")
    if any(day.weekday() != 3 for day in thursdays):
        raise CalendarContractError("calendar added-closure dates must be Thursdays")
    all_dates = _year_dates(year)
    mondays = {day for day in all_dates if day.weekday() == 0}
    closed = (mondays - exceptional) | set(special_reasons) | makeup | thursdays
    if len(closed) != document["expected_closed_days"]:
        raise CalendarContractError("parsed closed-day count does not match approved document")
    if len(all_dates) - len(closed) != document["expected_trading_days"]:
        raise CalendarContractError("parsed trading-day count does not match approved document")
    entries = []
    for day in all_dates:
        if day in exceptional:
            status = "exceptional_open"
            reason = "節前／節慶交易，取消原週一休市"
        elif day in closed:
            status = "scheduled_closed"
            if day in special_reasons:
                reason = special_reasons[day]
            elif day in makeup:
                reason = "2月23日取消休市之補休"
            elif day in thursdays:
                reason = "年度日程增休（週四）"
            else:
                reason = "一般週一休市"
        else:
            status = "expected_open"
            reason = "年度日程交易日"
        entries.append(
            {
                "calendar_date": day.isoformat(),
                "schedule_status": status,
                "reason": reason,
            }
        )
    return entries


def build_calendar_payload(
    source: dict,
    document: dict,
    text: str,
    content_hash: str,
    retrieved_at: str,
) -> dict:
    if content_hash != document["expected_content_hash"]:
        raise CalendarContractError("calendar document hash is not approved")
    payload = {
        "schema_version": "1.0",
        "source_id": source["source_id"],
        "source_role": source["source_role"],
        "document_url": document["document_url"],
        "calendar_year": document["calendar_year"],
        "calendar_version": document["calendar_version"],
        "retrieved_at": retrieved_at,
        "content_hash": content_hash,
        "parser_version": document["parser_version"],
        "market_codes": source["market_codes"],
        "closed_day_count": document["expected_closed_days"],
        "trading_day_count": document["expected_trading_days"],
        "entries": parse_tapmc_calendar_text(text, document),
    }
    return validate_calendar_payload(payload)


def _read_pdf(url: str, opener, timeout: int = 30) -> bytes:
    try:
        response = opener(url, timeout=timeout)
        status = getattr(response, "status", 200)
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_DOCUMENT_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise CalendarUnavailable("calendar document is unavailable") from exc
    if status != 200:
        raise CalendarUnavailable(f"calendar document returned HTTP {status}")
    if "application/pdf" not in content_type.lower():
        raise CalendarContractError("calendar document content type is not PDF")
    if not body or not body.startswith(b"%PDF-"):
        raise CalendarContractError("calendar document is empty or not a PDF")
    if len(body) > MAX_DOCUMENT_BYTES:
        raise CalendarContractError("calendar document exceeds size limit")
    return body


def extract_pdf_text(body: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise CalendarContractError(
            "controlled calendar refresh requires the optional calendar dependency"
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(body))
        if len(reader.pages) != 1:
            raise CalendarContractError("calendar PDF page count changed")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except CalendarContractError:
        raise
    except Exception as exc:
        raise CalendarContractError("calendar PDF parser failed") from exc
    if not text.strip():
        raise CalendarContractError("calendar PDF parser returned no text")
    return text


def refresh_market_calendar(
    root: pathlib.Path,
    year: int,
    *,
    opener=urllib.request.urlopen,
    text_extractor=extract_pdf_text,
    retrieved_at: str | None = None,
) -> dict:
    root = pathlib.Path(root)
    config = load_calendar_config(root)
    source, document = _source_and_document(config, year)
    if document is None:
        raise CalendarContractError(f"calendar year {year} is not configured")
    body = _read_pdf(document["document_url"], opener)
    content_hash = _hash(body)
    if content_hash != document["expected_content_hash"]:
        raise CalendarContractError("calendar document hash changed; review is required")
    text = text_extractor(body)
    retrieved_at = retrieved_at or dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = build_calendar_payload(source, document, text, content_hash, retrieved_at)
    target = root / document["normalized_path"]
    if target.exists():
        existing = validate_calendar_payload(json.loads(target.read_text(encoding="utf-8")))
        comparable = lambda value: {key: item for key, item in value.items() if key != "retrieved_at"}
        if comparable(existing) == comparable(payload):
            return existing
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        temporary = pathlib.Path(handle.name)
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def load_calendar_payload(root: pathlib.Path, year: int) -> dict | None:
    root = pathlib.Path(root)
    config = load_calendar_config(root)
    source, document = _source_and_document(config, year)
    if document is None:
        return None
    path = root / document["normalized_path"]
    if not path.exists():
        return None
    payload = validate_calendar_payload(json.loads(path.read_text(encoding="utf-8")))
    if payload["source_id"] != source["source_id"]:
        raise CalendarContractError("normalized calendar source does not match config")
    if payload["content_hash"] != document["expected_content_hash"]:
        raise CalendarContractError("normalized calendar hash does not match config")
    if payload["market_codes"] != source["market_codes"]:
        raise CalendarContractError("normalized calendar markets do not match config")
    return payload


def evaluate_market_calendar(root: pathlib.Path, calendar_date: str) -> dict:
    day = _date(calendar_date)
    config = load_calendar_config(root)
    source, document = _source_and_document(config, day.year)
    payload = load_calendar_payload(root, day.year)
    market_registry = source["market_codes"]
    if payload is None:
        reason = "尚無此年度經驗證的官方日曆 fixture"
        return {
            "schema_version": "1.0",
            "calendar_date": day.isoformat(),
            "schedule_status": "unknown",
            "reason": reason,
            "source_id": source["source_id"],
            "source_role": "calendar",
            "calendar_year": day.year,
            "calendar_version": document["calendar_version"] if document else None,
            "document_url": document["document_url"] if document else None,
            "retrieved_at": None,
            "content_hash": None,
            "parser_version": document["parser_version"] if document else None,
            "markets": [
                {**market, "schedule_status": "unknown", "reason": reason}
                for market in market_registry
            ],
        }
    entry = payload["entries"][(day - dt.date(day.year, 1, 1)).days]
    if entry["calendar_date"] != day.isoformat():
        raise CalendarContractError("calendar date index is inconsistent")
    return {
        "schema_version": "1.0",
        "calendar_date": day.isoformat(),
        "schedule_status": entry["schedule_status"],
        "reason": entry["reason"],
        "source_id": payload["source_id"],
        "source_role": payload["source_role"],
        "calendar_year": payload["calendar_year"],
        "calendar_version": payload["calendar_version"],
        "document_url": payload["document_url"],
        "retrieved_at": payload["retrieved_at"],
        "content_hash": payload["content_hash"],
        "parser_version": payload["parser_version"],
        "markets": [
            {**market, "schedule_status": entry["schedule_status"], "reason": entry["reason"]}
            for market in payload["market_codes"]
        ],
    }


def validate_calendar_evaluation(value: dict, requested_date: str) -> dict:
    required = {
        "schema_version",
        "calendar_date",
        "schedule_status",
        "reason",
        "source_id",
        "source_role",
        "calendar_year",
        "calendar_version",
        "document_url",
        "retrieved_at",
        "content_hash",
        "parser_version",
        "markets",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CalendarContractError("calendar evaluation fields are invalid")
    if value["schema_version"] != "1.0" or value["source_role"] != "calendar":
        raise CalendarContractError("calendar evaluation version or role is invalid")
    if value["calendar_date"] != requested_date:
        raise CalendarContractError("calendar evaluation date does not match requested date")
    if value["schedule_status"] not in SCHEDULE_STATUSES:
        raise CalendarContractError("calendar evaluation status is invalid")
    if not isinstance(value["reason"], str) or not value["reason"]:
        raise CalendarContractError("calendar evaluation reason is invalid")
    if not isinstance(value["markets"], list) or not value["markets"]:
        raise CalendarContractError("calendar evaluation markets are empty")
    for market in value["markets"]:
        if set(market) != {"market_code", "market_name", "schedule_status", "reason"}:
            raise CalendarContractError("calendar evaluation market fields are invalid")
        if market["schedule_status"] != value["schedule_status"]:
            raise CalendarContractError("calendar evaluation market status is inconsistent")
    if value["schedule_status"] == "unknown":
        if any(value[key] is not None for key in ("retrieved_at", "content_hash")):
            raise CalendarContractError("unknown calendar evaluation cannot claim fixture evidence")
    else:
        _datetime(value["retrieved_at"])
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(value["content_hash"])):
            raise CalendarContractError("calendar evaluation content hash is invalid")
        if not str(value["document_url"]).startswith("https://www.tapmc.com.tw/"):
            raise CalendarContractError("calendar evaluation document URL is invalid")
    return value
