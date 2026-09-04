"""Strict contracts for the checked-in county season-map data layer."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .categories import CategoryRegistry, NO_OFFICIAL_SEASON_REGISTRY_CITATION, SEASON_SEMANTICS, load_category_registry


COUNTY_REGISTRY_PATH = pathlib.PurePosixPath("config/county-registry.json")
MARKET_REGISTRY_PATH = pathlib.PurePosixPath("config/official-produce-markets.json")
BOUNDARY_SOURCE_PATH = pathlib.PurePosixPath("config/map-boundary-source.json")
COUNTY_SVG_PATH = pathlib.PurePosixPath("src/tpw/assets/taiwan-counties.svg")
COUNTY_COUNT = 22
COUNTY_SVG_MAX_BYTES = 128 * 1024
SOURCE_STATUSES = frozenset({"live", "stale", "fallback"})
FEED_COVERAGE_STATUSES = frozenset({"observed", "not_observed", "unknown"})
HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
COUNTY_CODE_PATTERN = re.compile(r"[0-9]{5}")
MARKET_CODE_PATTERN = re.compile(r"[0-9]{3}")
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SVG_PATH_ID_PATTERN = re.compile(r"county-shape-[a-z0-9]+(?:-[a-z0-9]+)*")
SVG_PATH_DATA_PATTERN = re.compile(r"[MLZ0-9., -]+")
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
MARKET_HOST_ALLOWLIST = frozenset({"www.tapmc.com.tw"})
BOUNDARY_HOST_ALLOWLIST = frozenset({"data.gov.tw", "www.tgos.tw"})
INSET_REGION_CODES = {
    "penghu-inset": "10016",
    "kinmen-inset": "09020",
    "lienchiang-inset": "09007",
}


class SeasonMapContractError(ValueError):
    """A checked-in map input or derived payload violated its contract."""


@dataclass(frozen=True)
class SeasonMapConfig:
    county_registry: dict
    market_registry: dict
    boundary_source: dict
    svg: bytes
    county_registry_hash: str
    market_registry_hash: str
    geometry_hash: str
    category_registry: CategoryRegistry
    category_registry_hash: str


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SeasonMapContractError("season-map JSON contains a duplicate key")
        value[key] = item
    return value


def _reject_constant(value):
    raise SeasonMapContractError(f"season-map JSON contains non-standard constant {value}")


def _load_json(path, label):
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except SeasonMapContractError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SeasonMapContractError(f"{label} must be valid UTF-8 JSON") from exc


def _hash_bytes(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value):
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SeasonMapContractError("season-map value is not canonical JSON") from exc
    return _hash_bytes(encoded)


def _require_object(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise SeasonMapContractError(f"{label} fields do not match the contract")
    return value


def _nonempty_text(value, label):
    if not isinstance(value, str) or not value or value != value.strip():
        raise SeasonMapContractError(f"{label} must be a non-empty trimmed string")
    return value


def _real_date(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SeasonMapContractError(f"{label} must use YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SeasonMapContractError(f"{label} must be a real date") from exc


def _real_month(value, label="as_of_month"):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise SeasonMapContractError(f"{label} must use YYYY-MM")
    try:
        dt.date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise SeasonMapContractError(f"{label} must be a real month") from exc
    return value


def _https_url(value, allowed_hosts, label):
    _nonempty_text(value, label)
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise SeasonMapContractError(f"{label} is not a valid URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path
        or parsed.fragment
    ):
        raise SeasonMapContractError(f"{label} must use an allowlisted HTTPS URL")
    return value


def load_county_registry(root):
    root = pathlib.Path(root)
    payload = _load_json(root / COUNTY_REGISTRY_PATH, "county registry")
    _require_object(payload, {"schema_version", "geometry_source", "counties"}, "county registry")
    if payload["schema_version"] != "1.0":
        raise SeasonMapContractError("county registry schema version is invalid")
    source = _require_object(
        payload["geometry_source"],
        {"dataset_url", "source_hash", "geometry_version", "converter_version"},
        "county registry geometry source",
    )
    if source["dataset_url"] != "https://data.gov.tw/dataset/7442":
        raise SeasonMapContractError("county registry dataset URL is invalid")
    if not isinstance(source["source_hash"], str) or not HASH_PATTERN.fullmatch(source["source_hash"]):
        raise SeasonMapContractError("county registry source hash is invalid")
    _nonempty_text(source["geometry_version"], "county registry geometry version")
    _nonempty_text(source["converter_version"], "county registry converter version")
    counties = payload["counties"]
    if not isinstance(counties, list) or len(counties) != COUNTY_COUNT:
        raise SeasonMapContractError("county registry must contain exactly 22 counties")
    codes = []
    slugs = []
    display_names = []
    path_ids = []
    aliases = {}
    fields = {"county_code", "slug", "display_name", "source_names", "svg_path_id"}
    for county in counties:
        _require_object(county, fields, "county registry entry")
        if not isinstance(county["county_code"], str) or not COUNTY_CODE_PATTERN.fullmatch(county["county_code"]):
            raise SeasonMapContractError("county code must contain five digits")
        if not isinstance(county["slug"], str) or not SLUG_PATTERN.fullmatch(county["slug"]):
            raise SeasonMapContractError("county slug is invalid")
        _nonempty_text(county["display_name"], "county display name")
        expected_path_id = "county-shape-" + county["slug"]
        if county["svg_path_id"] != expected_path_id or not SVG_PATH_ID_PATTERN.fullmatch(county["svg_path_id"]):
            raise SeasonMapContractError("county SVG path id does not match its slug")
        source_names = county["source_names"]
        if not isinstance(source_names, list) or not source_names:
            raise SeasonMapContractError("county source_names must be a non-empty list")
        if len(source_names) != len(set(source_names)):
            raise SeasonMapContractError("county source_names contains a duplicate")
        if county["display_name"] not in source_names:
            raise SeasonMapContractError("county display name must be an exact source alias")
        for source_name in source_names:
            _nonempty_text(source_name, "county source name")
            previous = aliases.get(source_name)
            if previous is not None and previous != county["slug"]:
                raise SeasonMapContractError("county source name maps to multiple counties")
            aliases[source_name] = county["slug"]
        codes.append(county["county_code"])
        slugs.append(county["slug"])
        display_names.append(county["display_name"])
        path_ids.append(county["svg_path_id"])
    for values, label in (
        (codes, "county codes"),
        (slugs, "county slugs"),
        (display_names, "county display names"),
        (path_ids, "county SVG path ids"),
    ):
        if len(values) != len(set(values)):
            raise SeasonMapContractError(f"{label} must be unique")
    return payload


def load_official_market_registry(root, county_registry=None):
    root = pathlib.Path(root)
    county_registry = county_registry or load_county_registry(root)
    county_slugs = {county["slug"] for county in county_registry["counties"]}
    payload = _load_json(root / MARKET_REGISTRY_PATH, "official market registry")
    _require_object(payload, {"schema_version", "registry_scope", "markets"}, "official market registry")
    if payload["schema_version"] != "1.0" or payload["registry_scope"] != "verified_entries_only":
        raise SeasonMapContractError("official market registry version or scope is invalid")
    markets = payload["markets"]
    if not isinstance(markets, list) or not markets:
        raise SeasonMapContractError("official market registry must contain verified entries")
    fields = {
        "market_code",
        "feed_market_name",
        "official_name",
        "county_slug",
        "market_kind",
        "official_url",
        "evidence_url",
        "evidence_checked_on",
        "feed_source_id",
        "feed_coverage_status",
    }
    codes = []
    feed_identities = []
    for market in markets:
        _require_object(market, fields, "official market entry")
        if not isinstance(market["market_code"], str) or not MARKET_CODE_PATTERN.fullmatch(market["market_code"]):
            raise SeasonMapContractError("official market code must contain three digits")
        _nonempty_text(market["feed_market_name"], "feed market name")
        _nonempty_text(market["official_name"], "official market name")
        if market["county_slug"] not in county_slugs:
            raise SeasonMapContractError("official market references an unknown county")
        if market["market_kind"] != "fruit_vegetable_wholesale":
            raise SeasonMapContractError("official market kind is invalid")
        _https_url(market["official_url"], MARKET_HOST_ALLOWLIST, "official market URL")
        _https_url(market["evidence_url"], MARKET_HOST_ALLOWLIST, "official market evidence URL")
        _real_date(market["evidence_checked_on"], "official market evidence date")
        if market["feed_source_id"] != "moa_market_8066":
            raise SeasonMapContractError("official market feed source is invalid")
        if market["feed_coverage_status"] not in FEED_COVERAGE_STATUSES:
            raise SeasonMapContractError("official market feed coverage status is invalid")
        codes.append(market["market_code"])
        feed_identities.append((market["market_code"], market["feed_market_name"]))
    if len(codes) != len(set(codes)):
        raise SeasonMapContractError("official market code must be unique")
    if len(feed_identities) != len(set(feed_identities)):
        raise SeasonMapContractError("official feed market identity must be unique")
    by_code = {market["market_code"]: market for market in markets}
    required_taipei = {
        "104": ("臺北二", "第二果菜批發市場"),
        "109": ("臺北一", "第一果菜批發市場"),
    }
    for code, (feed_name, official_name) in required_taipei.items():
        market = by_code.get(code)
        if (
            market is None
            or market["county_slug"] != "taipei-city"
            or market["feed_market_name"] != feed_name
            or market["official_name"] != official_name
            or market["evidence_url"] != "https://www.tapmc.com.tw/Pages/ContactUs"
        ):
            raise SeasonMapContractError("Taipei 104/109 official market evidence is incomplete")
    return payload


def _local_name(value):
    return value.rsplit("}", 1)[-1]


def validate_boundary_svg(content, county_registry):
    if not isinstance(content, bytes) or not content:
        raise SeasonMapContractError("county SVG must be non-empty bytes")
    if len(content) > COUNTY_SVG_MAX_BYTES:
        raise SeasonMapContractError("county SVG exceeds 128 KiB")
    lowered = content.lower()
    if any(token in lowered for token in (b"<!doctype", b"<!entity", b"<?", b"data:")):
        raise SeasonMapContractError("county SVG contains a prohibited external construct")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise SeasonMapContractError("county SVG is not valid XML") from exc
    if root.tag != f"{{{SVG_NAMESPACE}}}svg":
        raise SeasonMapContractError("county SVG root must use the SVG namespace")
    allowed_attributes = {
        "svg": {"viewbox", "role", "aria-labelledby", "data-season-map"},
        "title": {"id"},
        "g": {"data-region"},
        "a": {"href", "aria-label", "data-county-link"},
        "path": {"id", "data-county-path", "fill-rule", "d"},
    }
    all_ids = []
    for element in root.iter():
        if not isinstance(element.tag, str) or not element.tag.startswith(f"{{{SVG_NAMESPACE}}}"):
            raise SeasonMapContractError("county SVG elements must use the SVG namespace")
        element_name = _local_name(element.tag)
        if element_name not in allowed_attributes:
            raise SeasonMapContractError("county SVG contains a prohibited element")
        for raw_name, raw_value in element.attrib.items():
            name = _local_name(raw_name).lower()
            value = str(raw_value).lower()
            if raw_name != _local_name(raw_name) or name not in allowed_attributes[element_name]:
                raise SeasonMapContractError("county SVG contains a prohibited attribute")
            if any(token in value for token in ("url(", "javascript:", "data:", "http:", "https:")):
                raise SeasonMapContractError("county SVG contains an external attribute value")
            if name == "id":
                all_ids.append(raw_value)
    if len(all_ids) != len(set(all_ids)):
        raise SeasonMapContractError("county SVG ids must be globally unique")
    if root.get("viewBox") != "0 0 720 900" or root.get("role") != "img":
        raise SeasonMapContractError("county SVG root metadata is invalid")
    if root.get("aria-labelledby") != "county-map-title" or root.get("data-season-map") != "counties":
        raise SeasonMapContractError("county SVG accessible root metadata is invalid")
    children = list(root)
    if not children or _local_name(children[0].tag) != "title" or children[0].get("id") != "county-map-title":
        raise SeasonMapContractError("county SVG must begin with its accessible title")
    if "".join(children[0].itertext()).strip() != "臺灣二十二縣市產季地圖":
        raise SeasonMapContractError("county SVG title is invalid")
    county_by_slug = {county["slug"]: county for county in county_registry["counties"]}
    expected_ids = {county["svg_path_id"] for county in county_registry["counties"]}
    groups = [element for element in children[1:] if _local_name(element.tag) == "g"]
    if len(groups) != len(children) - 1:
        raise SeasonMapContractError("county SVG root may contain only its title and region groups")
    by_region = {}
    path_ids = []
    anchor_slugs = []
    for group in groups:
        region = group.get("data-region")
        if region in by_region or region not in {"main-island", *INSET_REGION_CODES}:
            raise SeasonMapContractError("county SVG region groups are invalid")
        region_codes = set()
        for anchor in group:
            if _local_name(anchor.tag) != "a" or len(anchor) != 1 or _local_name(anchor[0].tag) != "path":
                raise SeasonMapContractError("county SVG anchors must wrap exactly one path")
            slug = anchor.get("data-county-link")
            county = county_by_slug.get(slug)
            if county is None:
                raise SeasonMapContractError("county SVG anchor references an unknown county")
            path = anchor[0]
            if (
                anchor.get("href") != "#county-" + county["slug"]
                or anchor.get("aria-label") != county["display_name"]
                or path.get("id") != county["svg_path_id"]
                or path.get("data-county-path") != slug
                or path.get("fill-rule") != "evenodd"
                or not path.get("d")
                or not SVG_PATH_DATA_PATTERN.fullmatch(path.get("d"))
            ):
                raise SeasonMapContractError("county SVG anchor or path contract is invalid")
            region_codes.add(county["county_code"])
            path_ids.append(path.get("id"))
            anchor_slugs.append(slug)
        by_region[region] = region_codes
    if set(by_region) != {"main-island", *INSET_REGION_CODES}:
        raise SeasonMapContractError("county SVG must include the main island and three offshore insets")
    for region, code in INSET_REGION_CODES.items():
        if by_region[region] != {code}:
            raise SeasonMapContractError("county SVG offshore inset membership is invalid")
    if by_region["main-island"] != {county["county_code"] for county in county_registry["counties"]} - set(INSET_REGION_CODES.values()):
        raise SeasonMapContractError("county SVG main-island membership is invalid")
    if set(path_ids) != expected_ids or len(path_ids) != COUNTY_COUNT:
        raise SeasonMapContractError("county registry and SVG path sets differ")
    if len(anchor_slugs) != len(set(anchor_slugs)):
        raise SeasonMapContractError("county SVG contains a duplicate interactive county")
    return frozenset(path_ids)


def read_county_svg(root, county_registry=None):
    root = pathlib.Path(root)
    county_registry = county_registry or load_county_registry(root)
    try:
        content = (root / COUNTY_SVG_PATH).read_bytes()
    except OSError as exc:
        raise SeasonMapContractError("county SVG asset is unavailable") from exc
    validate_boundary_svg(content, county_registry)
    return content


def load_boundary_source(root, county_registry=None, svg=None):
    root = pathlib.Path(root)
    county_registry = county_registry or load_county_registry(root)
    svg = svg if svg is not None else read_county_svg(root, county_registry)
    payload = _load_json(root / BOUNDARY_SOURCE_PATH, "map boundary source manifest")
    fields = {
        "schema_version",
        "source_id",
        "dataset_title",
        "provider",
        "dataset_url",
        "resource_url",
        "license_name",
        "license_url",
        "source_archive_name",
        "source_format",
        "source_crs",
        "geometry_version",
        "source_time_position_roc",
        "source_time_indeterminate_position",
        "downloaded_on",
        "source_hash",
        "converter_version",
        "converted_on",
        "conversion",
        "asset_path",
        "geometry_hash",
        "county_codes",
        "attribution",
    }
    _require_object(payload, fields, "map boundary source manifest")
    if payload["schema_version"] != "1.0" or payload["source_id"] != "nlsc_county_boundary_7442":
        raise SeasonMapContractError("map boundary source version or id is invalid")
    for field in ("dataset_title", "provider", "license_name", "geometry_version", "converter_version", "attribution"):
        _nonempty_text(payload[field], "map boundary " + field)
    if payload["dataset_url"] != "https://data.gov.tw/dataset/7442":
        raise SeasonMapContractError("map boundary dataset URL is invalid")
    _https_url(payload["dataset_url"], BOUNDARY_HOST_ALLOWLIST, "map boundary dataset URL")
    _https_url(payload["resource_url"], BOUNDARY_HOST_ALLOWLIST, "map boundary resource URL")
    if payload["license_url"] != "https://data.gov.tw/license":
        raise SeasonMapContractError("map boundary license URL is invalid")
    _https_url(payload["license_url"], BOUNDARY_HOST_ALLOWLIST, "map boundary license URL")
    if not isinstance(payload["source_archive_name"], str) or not re.fullmatch(r"[A-Za-z0-9._-]+\.zip", payload["source_archive_name"]):
        raise SeasonMapContractError("map boundary archive name is invalid")
    if payload["source_format"] != "GML" or payload["source_crs"] != "EPSG:3824":
        raise SeasonMapContractError("map boundary source format or CRS is invalid")
    if not isinstance(payload["source_time_position_roc"], str) or not re.fullmatch(r"\d{3}-\d{2}-\d{2}", payload["source_time_position_roc"]):
        raise SeasonMapContractError("map boundary source time position is invalid")
    if payload["source_time_indeterminate_position"] != "after":
        raise SeasonMapContractError("map boundary indeterminate time position is invalid")
    _real_date(payload["downloaded_on"], "map boundary download date")
    _real_date(payload["converted_on"], "map boundary conversion date")
    if not isinstance(payload["source_hash"], str) or not HASH_PATTERN.fullmatch(payload["source_hash"]):
        raise SeasonMapContractError("map boundary source hash is invalid")
    if not isinstance(payload["geometry_hash"], str) or not HASH_PATTERN.fullmatch(payload["geometry_hash"]):
        raise SeasonMapContractError("map boundary geometry hash is invalid")
    if payload["asset_path"] != str(COUNTY_SVG_PATH):
        raise SeasonMapContractError("map boundary asset path is invalid")
    if payload["geometry_hash"] != _hash_bytes(svg):
        raise SeasonMapContractError("map boundary geometry hash does not match the SVG")
    registry_source = county_registry["geometry_source"]
    for field in ("dataset_url", "source_hash", "geometry_version", "converter_version"):
        if payload[field] != registry_source[field]:
            raise SeasonMapContractError("county registry and boundary lineage differ")
    conversion = _require_object(
        payload["conversion"],
        {
            "view_box",
            "simplification_method",
            "simplification_tolerance_pixels",
            "minimum_ring_area_pixels",
            "maximum_rings_per_county",
            "mainland_filter_bbox",
            "offshore_inset_county_codes",
        },
        "map boundary conversion",
    )
    if conversion["view_box"] != "0 0 720 900" or conversion["simplification_method"] != "Ramer-Douglas-Peucker":
        raise SeasonMapContractError("map boundary conversion method is invalid")
    for field in ("simplification_tolerance_pixels", "minimum_ring_area_pixels"):
        value = conversion[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise SeasonMapContractError("map boundary conversion numeric threshold is invalid")
    maximum_rings = conversion["maximum_rings_per_county"]
    if isinstance(maximum_rings, bool) or not isinstance(maximum_rings, int) or maximum_rings < 1:
        raise SeasonMapContractError("map boundary ring limit is invalid")
    bbox = conversion["mainland_filter_bbox"]
    if not isinstance(bbox, list) or len(bbox) != 4 or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bbox):
        raise SeasonMapContractError("map boundary mainland bbox is invalid")
    if not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        raise SeasonMapContractError("map boundary mainland bbox is unordered")
    inset_codes = conversion["offshore_inset_county_codes"]
    if not isinstance(inset_codes, list) or set(inset_codes) != set(INSET_REGION_CODES.values()) or len(inset_codes) != 3:
        raise SeasonMapContractError("map boundary offshore inset codes are invalid")
    county_codes = [county["county_code"] for county in county_registry["counties"]]
    if payload["county_codes"] != county_codes:
        raise SeasonMapContractError("map boundary manifest and county registry order differ")
    return payload


def load_season_map_config(root):
    root = pathlib.Path(root)
    county_registry = load_county_registry(root)
    svg = read_county_svg(root, county_registry)
    boundary_source = load_boundary_source(root, county_registry, svg)
    market_registry = load_official_market_registry(root, county_registry)
    category_registry = load_category_registry(root)
    return SeasonMapConfig(
        county_registry=county_registry,
        market_registry=market_registry,
        boundary_source=boundary_source,
        svg=svg,
        county_registry_hash=_hash_bytes((root / COUNTY_REGISTRY_PATH).read_bytes()),
        market_registry_hash=_hash_bytes((root / MARKET_REGISTRY_PATH).read_bytes()),
        geometry_hash=_hash_bytes(svg),
        category_registry=category_registry,
        category_registry_hash=category_registry.content_hash,
    )


def _public_market(market):
    return {
        "market_code": market["market_code"],
        "feed_market_name": market["feed_market_name"],
        "official_name": market["official_name"],
        "official_url": market["official_url"],
        "evidence_url": market["evidence_url"],
        "feed_coverage_status": market["feed_coverage_status"],
    }


def build_season_map_payload(root, catalog, resolved_market_date):
    config = load_season_map_config(root)
    _real_date(resolved_market_date, "resolved_market_date")
    if not isinstance(catalog, list) or not catalog:
        raise SeasonMapContractError("seasonality catalog must be a non-empty list")
    aliases = {}
    for county in config.county_registry["counties"]:
        for source_name in county["source_names"]:
            aliases[source_name] = county["slug"]
    categories_by_id = {category.id: category for category in config.category_registry.categories}
    months = set()
    statuses_by_category = {}
    catalog_row_counts = {}
    catalog_keys = set()
    by_county = {county["slug"]: {} for county in config.county_registry["counties"]}
    unmapped = set()
    required_fields = {"month", "category", "display_name", "canonical_id", "source_status", "counties"}
    for row in catalog:
        if not isinstance(row, dict) or not required_fields.issubset(row):
            raise SeasonMapContractError("seasonality catalog row is incomplete")
        month = _real_month(row["month"], "seasonality catalog month")
        months.add(month)
        category_id = row["category"]
        category = categories_by_id.get(category_id)
        if category is None:
            raise SeasonMapContractError("seasonality catalog category is unregistered: " + repr(category_id))
        if category.season_semantics == "no_official_season_registry":
            raise SeasonMapContractError(
                "seasonality catalog row uses a category with no official season registry "
                "(" + NO_OFFICIAL_SEASON_REGISTRY_CITATION + "); its map cells must stay unknown, "
                "not be populated from a catalog row: " + repr(category_id)
            )
        _nonempty_text(row["display_name"], "seasonality display name")
        canonical_id = row["canonical_id"]
        if canonical_id is not None:
            _nonempty_text(canonical_id, "seasonality canonical id")
        if row["source_status"] not in SOURCE_STATUSES:
            raise SeasonMapContractError("seasonality source status is invalid")
        key = (category_id, row["display_name"])
        if key in catalog_keys:
            raise SeasonMapContractError("seasonality catalog contains a duplicate (category, display_name): " + repr(key))
        catalog_keys.add(key)
        existing_status = statuses_by_category.get(category_id)
        if existing_status is not None and existing_status != row["source_status"]:
            raise SeasonMapContractError("seasonality catalog must use one source status per category: " + repr(category_id))
        statuses_by_category[category_id] = row["source_status"]
        catalog_row_counts[category_id] = catalog_row_counts.get(category_id, 0) + 1
        source_counties = row["counties"]
        if not isinstance(source_counties, list) or len(source_counties) != len(set(source_counties)):
            raise SeasonMapContractError("seasonality counties must be a unique list")
        produce = {
            "category": category_id,
            "display_name": row["display_name"],
            "canonical_id": canonical_id,
            "source_status": row["source_status"],
        }
        for source_county in source_counties:
            _nonempty_text(source_county, "seasonality source county")
            slug = aliases.get(source_county)
            if slug is None:
                unmapped.add(source_county)
                continue
            by_county[slug][key] = produce
    if len(months) != 1:
        raise SeasonMapContractError("seasonality catalog must cover exactly one month")
    markets_by_county = {county["slug"]: [] for county in config.county_registry["counties"]}
    for market in config.market_registry["markets"]:
        markets_by_county[market["county_slug"]].append(_public_market(market))
    counties = []
    for county in config.county_registry["counties"]:
        produce = sorted(
            by_county[county["slug"]].values(),
            key=lambda item: (item["category"], item["display_name"]),
        )
        markets = sorted(markets_by_county[county["slug"]], key=lambda item: item["market_code"])
        counties.append(
            {
                "county_code": county["county_code"],
                "slug": county["slug"],
                "display_name": county["display_name"],
                "seasonal_catalog_count": len(produce),
                "local_seasonal_produce": produce,
                "official_markets": markets,
            }
        )
    month = next(iter(months))
    categories_payload = [
        {
            "id": category.id,
            "label": category.label,
            "season_semantics": category.season_semantics,
            "catalog_row_count": catalog_row_counts.get(category.id, 0),
        }
        for category in config.category_registry.categories
    ]
    seasonality_sources = {
        category_id: {"source_status": status}
        for category_id, status in statuses_by_category.items()
    }
    payload = {
        "schema_version": "1.1",
        "as_of_month": month,
        "resolved_market_date": resolved_market_date,
        "inputs": {
            "seasonality_sources": seasonality_sources,
            "seasonality_snapshot_hash": canonical_hash(catalog),
            "county_registry_hash": config.county_registry_hash,
            "market_registry_hash": config.market_registry_hash,
            "geometry_hash": config.geometry_hash,
            "category_registry_hash": config.category_registry_hash,
        },
        "unmapped_source_counties": sorted(unmapped),
        "categories": categories_payload,
        "counties": counties,
    }
    return validate_season_map_payload(
        payload,
        config,
        expected_month=month,
        expected_resolved_market_date=resolved_market_date,
    )


def validate_season_map_payload(
    payload,
    config=None,
    *,
    expected_month=None,
    expected_resolved_market_date=None,
):
    _require_object(
        payload,
        {"schema_version", "as_of_month", "resolved_market_date", "inputs", "unmapped_source_counties", "categories", "counties"},
        "season-map payload",
    )
    if payload["schema_version"] != "1.1":
        raise SeasonMapContractError("season-map schema version is invalid")
    month = _real_month(payload["as_of_month"])
    _real_date(payload["resolved_market_date"], "resolved_market_date")
    if expected_month is not None and month != expected_month:
        raise SeasonMapContractError("season-map month does not match publication context")
    if expected_resolved_market_date is not None and payload["resolved_market_date"] != expected_resolved_market_date:
        raise SeasonMapContractError("season-map market date does not match publication")
    inputs = _require_object(
        payload["inputs"],
        {
            "seasonality_sources", "seasonality_snapshot_hash", "county_registry_hash",
            "market_registry_hash", "geometry_hash", "category_registry_hash",
        },
        "season-map inputs",
    )
    seasonality_sources = inputs["seasonality_sources"]
    if not isinstance(seasonality_sources, dict) or not seasonality_sources:
        raise SeasonMapContractError("season-map seasonality sources must be a non-empty object")
    for category_id, source in seasonality_sources.items():
        _require_object(source, {"source_status"}, "season-map seasonality source")
        if source["source_status"] not in SOURCE_STATUSES:
            raise SeasonMapContractError("season-map seasonality source status is invalid")
    for field in (
        "seasonality_snapshot_hash", "county_registry_hash", "market_registry_hash",
        "geometry_hash", "category_registry_hash",
    ):
        if not isinstance(inputs[field], str) or not HASH_PATTERN.fullmatch(inputs[field]):
            raise SeasonMapContractError("season-map input hash is invalid")
    unmapped = payload["unmapped_source_counties"]
    if not isinstance(unmapped, list) or unmapped != sorted(set(unmapped)):
        raise SeasonMapContractError("unmapped source counties must be sorted and unique")
    for value in unmapped:
        _nonempty_text(value, "unmapped source county")

    categories = payload["categories"]
    if not isinstance(categories, list) or not categories:
        raise SeasonMapContractError("season-map categories must be a non-empty list")
    category_fields = {"id", "label", "season_semantics", "catalog_row_count"}
    category_ids = []
    semantics_by_id = {}
    counts_by_id = {}
    for category in categories:
        _require_object(category, category_fields, "season-map category")
        category_id = category["id"]
        if not isinstance(category_id, str) or not category_id:
            raise SeasonMapContractError("season-map category id is invalid")
        _nonempty_text(category["label"], "season-map category label")
        semantics = category["season_semantics"]
        if semantics not in SEASON_SEMANTICS:
            raise SeasonMapContractError("season-map category season_semantics is invalid")
        count = category["catalog_row_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise SeasonMapContractError("season-map category catalog_row_count is invalid")
        if semantics == "no_official_season_registry" and count != 0:
            raise SeasonMapContractError(
                "season-map no_official_season_registry category must have zero catalog rows "
                "(" + NO_OFFICIAL_SEASON_REGISTRY_CITATION + "): " + repr(category_id)
            )
        category_ids.append(category_id)
        semantics_by_id[category_id] = semantics
        counts_by_id[category_id] = count
    if len(category_ids) != len(set(category_ids)):
        raise SeasonMapContractError("season-map categories must have unique ids")
    categories_with_rows = {category_id for category_id, count in counts_by_id.items() if count > 0}
    if set(seasonality_sources) != categories_with_rows:
        raise SeasonMapContractError("season-map seasonality sources must match the categories with catalog rows")

    counties = payload["counties"]
    if not isinstance(counties, list) or len(counties) != COUNTY_COUNT:
        raise SeasonMapContractError("season-map payload must contain exactly 22 counties")
    county_fields = {"county_code", "slug", "display_name", "seasonal_catalog_count", "local_seasonal_produce", "official_markets"}
    produce_fields = {"category", "display_name", "canonical_id", "source_status"}
    market_fields = {"market_code", "feed_market_name", "official_name", "official_url", "evidence_url", "feed_coverage_status"}
    identities = []
    category_id_set = set(category_ids)
    for county in counties:
        _require_object(county, county_fields, "season-map county")
        if not isinstance(county["county_code"], str) or not COUNTY_CODE_PATTERN.fullmatch(county["county_code"]):
            raise SeasonMapContractError("season-map county code is invalid")
        if not isinstance(county["slug"], str) or not SLUG_PATTERN.fullmatch(county["slug"]):
            raise SeasonMapContractError("season-map county slug is invalid")
        _nonempty_text(county["display_name"], "season-map county display name")
        produce_rows = county["local_seasonal_produce"]
        if not isinstance(produce_rows, list):
            raise SeasonMapContractError("season-map local produce must be a list")
        if isinstance(county["seasonal_catalog_count"], bool) or not isinstance(county["seasonal_catalog_count"], int) or county["seasonal_catalog_count"] < 0:
            raise SeasonMapContractError("season-map catalog count is invalid")
        if county["seasonal_catalog_count"] != len(produce_rows):
            raise SeasonMapContractError("season-map catalog count does not match its rows")
        produce_keys = []
        for produce in produce_rows:
            _require_object(produce, produce_fields, "season-map local produce")
            produce_category = produce["category"]
            if produce_category not in category_id_set:
                raise SeasonMapContractError("season-map produce category is unregistered: " + repr(produce_category))
            if semantics_by_id[produce_category] == "no_official_season_registry":
                raise SeasonMapContractError(
                    "season-map local produce must not use a category with no official season registry "
                    "(" + NO_OFFICIAL_SEASON_REGISTRY_CITATION + "): " + repr(produce_category)
                )
            _nonempty_text(produce["display_name"], "season-map produce display name")
            if produce["canonical_id"] is not None:
                _nonempty_text(produce["canonical_id"], "season-map produce canonical id")
            expected_source = seasonality_sources.get(produce_category)
            if expected_source is None or produce["source_status"] != expected_source["source_status"]:
                raise SeasonMapContractError("season-map produce source status differs from its input")
            produce_keys.append((produce_category, produce["display_name"]))
        if produce_keys != sorted(produce_keys) or len(produce_keys) != len(set(produce_keys)):
            raise SeasonMapContractError("season-map local produce must be sorted and unique")
        market_rows = county["official_markets"]
        if not isinstance(market_rows, list):
            raise SeasonMapContractError("season-map official markets must be a list")
        market_codes = []
        for market in market_rows:
            _require_object(market, market_fields, "season-map official market")
            if not isinstance(market["market_code"], str) or not MARKET_CODE_PATTERN.fullmatch(market["market_code"]):
                raise SeasonMapContractError("season-map market code is invalid")
            _nonempty_text(market["feed_market_name"], "season-map feed market name")
            _nonempty_text(market["official_name"], "season-map official market name")
            _https_url(market["official_url"], MARKET_HOST_ALLOWLIST, "season-map official market URL")
            _https_url(market["evidence_url"], MARKET_HOST_ALLOWLIST, "season-map official market evidence URL")
            if market["feed_coverage_status"] not in FEED_COVERAGE_STATUSES:
                raise SeasonMapContractError("season-map market feed coverage is invalid")
            market_codes.append(market["market_code"])
        if market_codes != sorted(market_codes) or len(market_codes) != len(set(market_codes)):
            raise SeasonMapContractError("season-map markets must be sorted and unique")
        identities.append((county["county_code"], county["slug"], county["display_name"]))
    if len(identities) != len(set(identities)):
        raise SeasonMapContractError("season-map county identities must be unique")

    if config is not None:
        expected_identities = [
            (county["county_code"], county["slug"], county["display_name"])
            for county in config.county_registry["counties"]
        ]
        if identities != expected_identities:
            raise SeasonMapContractError("season-map counties differ from the checked-in registry")
        expected_hashes = {
            "county_registry_hash": config.county_registry_hash,
            "market_registry_hash": config.market_registry_hash,
            "geometry_hash": config.geometry_hash,
            "category_registry_hash": config.category_registry_hash,
        }
        if any(inputs[field] != value for field, value in expected_hashes.items()):
            raise SeasonMapContractError("season-map checked-in input hash differs from its source")
        expected_category_projection = [
            {"id": category.id, "label": category.label, "season_semantics": category.season_semantics}
            for category in config.category_registry.categories
        ]
        actual_category_projection = [
            {"id": category["id"], "label": category["label"], "season_semantics": category["season_semantics"]}
            for category in categories
        ]
        if actual_category_projection != expected_category_projection:
            raise SeasonMapContractError("season-map categories differ from the checked-in registry")
        markets_by_county = {county["slug"]: [] for county in config.county_registry["counties"]}
        for market in config.market_registry["markets"]:
            markets_by_county[market["county_slug"]].append(_public_market(market))
        for county in counties:
            expected_markets = sorted(markets_by_county[county["slug"]], key=lambda item: item["market_code"])
            if county["official_markets"] != expected_markets:
                raise SeasonMapContractError("season-map markets differ from the verified registry")
    return payload
