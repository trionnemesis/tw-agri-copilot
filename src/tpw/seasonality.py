import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .market import RETRYABLE_STATUS, UpstreamUnavailable


URL = "https://www.afa.gov.tw/cht/index.php"
SOURCE_URL = "https://www.afa.gov.tw/cht/index.php?code=list&ids=1103"
CATEGORIES = {
    "fruit": {"type": "1", "label": "水果"},
    "vegetable": {"type": "2", "label": "蔬菜"},
}
REQUIRED_FIELDS = ("種類", "農產品", "品種名稱", "縣市", "行政區", "盛產月份")


class _SeasonalityPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_found = False
        self.rows = []
        self.next_href = None
        self._table_depth = 0
        self._row = None
        self._field = None
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("title") == "下一頁":
            self.next_href = attributes.get("href")
        if tag == "table":
            classes = set(attributes.get("class", "").split())
            if self._table_depth:
                self._table_depth += 1
            elif "table-a-products" in classes:
                self.table_found = True
                self._table_depth = 1
            return
        if not self._table_depth:
            return
        if tag == "tr":
            self._row = {}
        elif tag == "td" and self._row is not None:
            self._field = attributes.get("data-th")
            self._chunks = []

    def handle_data(self, data):
        if self._field is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag):
        if not self._table_depth:
            return
        if tag == "td" and self._field is not None:
            self._row[self._field] = " ".join("".join(self._chunks).split())
            self._field = None
            self._chunks = []
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._table_depth -= 1


def _month_number(month):
    return dt.date.fromisoformat(month + "-01").month


def parse_page(body, category, month, current_page=1):
    if category not in CATEGORIES:
        raise ValueError("invalid seasonality category")
    try:
        text = body.decode("utf-8-sig") if isinstance(body, bytes) else str(body)
    except UnicodeDecodeError as exc:
        raise ValueError("seasonality response is not UTF-8") from exc
    parser = _SeasonalityPageParser()
    parser.feed(text)
    if not parser.table_found:
        raise ValueError("seasonality response lacks the official result table")

    expected_label = CATEGORIES[category]["label"]
    expected_month = _month_number(month)
    rows = []
    for raw in parser.rows:
        if not raw.get("農產品"):
            continue
        missing = [field for field in REQUIRED_FIELDS if field not in raw]
        if missing:
            raise ValueError("seasonality row missing required fields: " + ", ".join(missing))
        if raw["種類"] != expected_label:
            raise ValueError("seasonality row category does not match request")
        months = {int(value) for value in re.findall(r"(\d{1,2})\s*月", raw["盛產月份"])}
        if expected_month not in months or any(value < 1 or value > 12 for value in months):
            raise ValueError("seasonality row month does not match request")
        rows.append(
            {
                "category": category,
                "display_name": raw["農產品"],
                "variety": raw["品種名稱"],
                "county": raw["縣市"],
                "district": raw["行政區"],
                "months": sorted(months),
            }
        )
    if not rows:
        raise UpstreamUnavailable("seasonality upstream returned no rows")

    next_page = None
    if parser.next_href and parser.next_href != "#":
        query = urllib.parse.parse_qs(urllib.parse.urlparse(parser.next_href).query)
        try:
            next_page = int(query["page"][0])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("seasonality pagination link is invalid") from exc
        if next_page != current_page + 1:
            raise ValueError("seasonality pagination is not sequential")
        if query.get("type", [None])[0] != CATEGORIES[category]["type"]:
            raise ValueError("seasonality pagination changed category")
        if query.get("period", [None])[0] not in (str(expected_month), "now"):
            raise ValueError("seasonality pagination changed month")
    return rows, next_page


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
                raise ValueError(f"seasonality upstream HTTP status {status}")
            if not body.strip() or "html" not in content_type.lower():
                raise RuntimeError("seasonality upstream response is empty or not HTML")
            return body
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_STATUS:
                raise ValueError(f"seasonality upstream HTTP status {exc.code}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, RuntimeError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            sleeper(backoff_seconds * (2**attempt))
    raise UpstreamUnavailable(
        f"seasonality upstream unavailable after {attempts} attempts"
    ) from last_error


def fetch_category(
    category,
    month,
    opener=urllib.request.urlopen,
    max_pages=50,
    timeout=30,
    attempts=3,
    backoff_seconds=1.0,
    sleeper=time.sleep,
    urls=None,
):
    if category not in CATEGORIES:
        raise ValueError("invalid seasonality category")
    if attempts < 1:
        raise ValueError("attempts must be positive")
    month_number = _month_number(month)
    rows = []
    page_signatures = set()
    page = 1
    while page <= max_pages:
        query = urllib.parse.urlencode(
            {
                "code": "list",
                "ids": "1103",
                "mod_code": "search",
                "type": CATEGORIES[category]["type"],
                "period": month_number,
                "page": page,
            }
        )
        url = URL + "?" + query
        if urls is not None:
            urls.append(url)
        body = _read_page(url, opener, timeout, attempts, backoff_seconds, sleeper)
        page_rows, next_page = parse_page(body, category, month, page)
        signature = tuple(
            (row["display_name"], row["variety"], row["county"], row["district"], tuple(row["months"]))
            for row in page_rows
        )
        if signature in page_signatures:
            raise ValueError("duplicate seasonality pagination page")
        page_signatures.add(signature)
        rows.extend(page_rows)
        if next_page is None:
            break
        page = next_page
    else:
        raise ValueError("maximum seasonality pages reached")
    return rows


def fetch_official(month, **kwargs):
    rows = []
    for category in CATEGORIES:
        rows.extend(fetch_category(category, month, **kwargs))
    keyed = {
        (
            row["category"],
            row["display_name"],
            row["variety"],
            row["county"],
            row["district"],
            tuple(row["months"]),
        ): row
        for row in rows
    }
    return [keyed[key] for key in sorted(keyed)]


def build_catalog(raw_rows, month, fetched_at):
    _month_number(month)
    grouped = {}
    for row in raw_rows:
        if row.get("category") not in CATEGORIES or not row.get("display_name"):
            raise ValueError("invalid seasonality source row")
        key = (row["category"], row["display_name"])
        group = grouped.setdefault(key, {"counties": set(), "districts": set(), "varieties": set()})
        if row.get("county"):
            group["counties"].add(row["county"])
        if row.get("district"):
            group["districts"].add(row["district"])
        if row.get("variety"):
            group["varieties"].add(row["variety"])
    return [
        {
            "schema_version": "1.0",
            "month": month,
            "canonical_id": None,
            "display_name": display_name,
            "source_display_names": [display_name],
            "category": category,
            "counties": sorted(values["counties"]),
            "county_count": len(values["counties"]),
            "district_count": len(values["districts"]),
            "varieties": sorted(values["varieties"]),
            "variety_count": len(values["varieties"]),
            "source_url": SOURCE_URL,
            "source_status": "live",
            "fetched_at": fetched_at,
        }
        for (category, display_name), values in sorted(grouped.items(), key=lambda value: value[0][1])
    ]


def map_catalog(items, catalog, month):
    aliases = {}
    configured = {}
    for item in items:
        configured[item["canonical_id"]] = item
        names = item.get("seasonality_names") or [item["display_name"]]
        for name in names:
            key = (item["category"], name)
            if key in aliases:
                raise ValueError("duplicate seasonality name mapping: " + name)
            aliases[key] = item["canonical_id"]

    mapped = {}
    unmatched = []
    for row in catalog:
        canonical_id = aliases.get((row["category"], row["display_name"]))
        if canonical_id is None:
            unmatched.append(dict(row))
            continue
        item = configured[canonical_id]
        group = mapped.setdefault(
            canonical_id,
            {
                **row,
                "canonical_id": canonical_id,
                "display_name": item["display_name"],
                "source_display_names": set(),
                "counties": set(),
                "varieties": set(),
                "district_count": 0,
            },
        )
        group["source_display_names"].update(row["source_display_names"])
        group["counties"].update(row["counties"])
        group["varieties"].update(row["varieties"])
        group["district_count"] += row["district_count"]

    mapped_rows = []
    for row in mapped.values():
        row["source_display_names"] = sorted(row["source_display_names"])
        row["counties"] = sorted(row["counties"])
        row["county_count"] = len(row["counties"])
        row["varieties"] = sorted(row["varieties"])
        row["variety_count"] = len(row["varieties"])
        mapped_rows.append(row)
    catalog_rows = sorted(mapped_rows + unmatched, key=lambda row: row["display_name"])

    by_id = {row["canonical_id"]: row for row in mapped_rows}
    source_status = catalog_rows[0]["source_status"] if catalog_rows else "live"
    fetched_at = catalog_rows[0].get("fetched_at", "") if catalog_rows else ""
    seasonality_rows = []
    for item in sorted(items, key=lambda value: value["display_name"]):
        row = by_id.get(item["canonical_id"])
        counties = row["counties"] if row else []
        seasonality_rows.append(
            {
                "schema_version": "1.0",
                "month": month,
                "canonical_id": item["canonical_id"],
                "display_name": item["display_name"],
                "category": item["category"],
                "seasonality_status": "in_season" if row else "unknown",
                "counties": counties,
                "county_count": len(counties),
                "source_url": SOURCE_URL,
                "source_status": source_status,
                "verified_at": fetched_at,
            }
        )
    return seasonality_rows, catalog_rows


def build_seasonality(items, manual_config, month):
    parsed = dt.date.fromisoformat(month + "-01")
    configured = {entry["canonical_id"]: entry for entry in manual_config["items"]}
    unknown = set(configured) - {item["canonical_id"] for item in items}
    if unknown:
        raise ValueError("seasonality contains unknown canonical ids: " + ", ".join(sorted(unknown)))
    output = []
    for item in sorted(items, key=lambda value: value["display_name"]):
        entry = configured.get(item["canonical_id"])
        if entry is None:
            status = "unknown"
            counties = []
        else:
            months = {int(value) for value in entry["months"]}
            if any(value < 1 or value > 12 for value in months):
                raise ValueError("seasonality month must be 1..12")
            status = "in_season" if parsed.month in months else "out_of_season"
            counties = sorted(set(entry.get("counties", [])))
        output.append(
            {
                "schema_version": "1.0",
                "month": month,
                "canonical_id": item["canonical_id"],
                "display_name": item["display_name"],
                "category": item["category"],
                "seasonality_status": status,
                "counties": counties,
                "county_count": len(counties),
                "source_url": manual_config["source_url"],
                "source_status": "fallback",
                "verified_at": manual_config["verified_at"],
            }
        )
    return output


def catalog_from_seasonality(rows):
    return [
        {
            "schema_version": "1.0",
            "month": row["month"],
            "canonical_id": row["canonical_id"],
            "display_name": row["display_name"],
            "source_display_names": [row["display_name"]],
            "category": row["category"],
            "counties": row["counties"],
            "county_count": row["county_count"],
            "district_count": 0,
            "varieties": [],
            "variety_count": 0,
            "source_url": row["source_url"],
            "source_status": row["source_status"],
            "fetched_at": row["verified_at"],
        }
        for row in rows
        if row["seasonality_status"] == "in_season"
    ]


def with_source_status(rows, status):
    if status not in ("live", "stale", "fallback"):
        raise ValueError("invalid seasonality source status")
    return [{**row, "source_status": status} for row in rows]


def load_manual(path, items, month):
    return build_seasonality(items, json.loads(path.read_text()), month)
