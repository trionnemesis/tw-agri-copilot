import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


CATEGORIES = ("fruit", "vegetable")
ICON_FIDELITIES = ("exact", "representative", "category_fallback")
SPRITE_PATH = Path(__file__).with_name("assets") / "produce-icons.svg"
SPRITE_MAX_BYTES = 64 * 1024
_SAFE_SYMBOL_ID = re.compile(r"^produce-(?:fruit|vegetable)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_ALLOWED_SVG_ELEMENTS = {"svg", "symbol", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon"}
_ALLOWED_SVG_ATTRIBUTES = {
    "svg": frozenset(),
    "symbol": frozenset({"id", "viewbox", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin"}),
    "g": frozenset({"transform"}),
    "path": frozenset({"d", "transform"}),
    "circle": frozenset({"cx", "cy", "r", "transform"}),
    "ellipse": frozenset({"cx", "cy", "rx", "ry", "transform"}),
    "rect": frozenset({"x", "y", "width", "height", "rx", "ry", "transform"}),
    "line": frozenset({"x1", "x2", "y1", "y2", "transform"}),
    "polyline": frozenset({"points", "transform"}),
    "polygon": frozenset({"points", "transform"}),
}


@dataclass(frozen=True)
class ProduceIconSpec:
    symbol_id: str
    fidelity: str


PRODUCE_ICON_REGISTRY = {
    ("fruit", "文旦柚"): ProduceIconSpec("produce-fruit-pomelo", "representative"),
    ("fruit", "木瓜"): ProduceIconSpec("produce-fruit-papaya", "exact"),
    ("fruit", "柿子"): ProduceIconSpec("produce-fruit-persimmon", "exact"),
    ("fruit", "楊桃"): ProduceIconSpec("produce-fruit-starfruit", "exact"),
    ("fruit", "檸檬"): ProduceIconSpec("produce-fruit-lemon", "exact"),
    ("fruit", "溫帶梨"): ProduceIconSpec("produce-fruit-temperate-pear", "representative"),
    ("fruit", "甜瓜"): ProduceIconSpec("produce-fruit-melon", "representative"),
    ("fruit", "番石榴"): ProduceIconSpec("produce-fruit-guava", "exact"),
    ("fruit", "百香果"): ProduceIconSpec("produce-fruit-passion-fruit", "exact"),
    ("fruit", "紅龍果"): ProduceIconSpec("produce-fruit-dragon-fruit", "exact"),
    ("fruit", "葡萄"): ProduceIconSpec("produce-fruit-grapes", "exact"),
    ("fruit", "蓮霧"): ProduceIconSpec("produce-fruit-wax-apple", "exact"),
    ("fruit", "蘋果"): ProduceIconSpec("produce-fruit-apple", "exact"),
    ("fruit", "西瓜"): ProduceIconSpec("produce-fruit-watermelon", "exact"),
    ("fruit", "酪梨"): ProduceIconSpec("produce-fruit-avocado", "exact"),
    ("fruit", "釋迦"): ProduceIconSpec("produce-fruit-custard-apple", "exact"),
    ("fruit", "香蕉"): ProduceIconSpec("produce-fruit-banana", "exact"),
    ("fruit", "高接梨"): ProduceIconSpec("produce-fruit-grafted-pear", "representative"),
    ("fruit", "鳳梨"): ProduceIconSpec("produce-fruit-pineapple", "exact"),
    ("fruit", "龍眼"): ProduceIconSpec("produce-fruit-longan", "exact"),
    ("vegetable", "甘藍"): ProduceIconSpec("produce-vegetable-cabbage", "exact"),
    ("vegetable", "甜椒"): ProduceIconSpec("produce-vegetable-sweet-pepper", "exact"),
    ("vegetable", "番茄"): ProduceIconSpec("produce-vegetable-tomato", "exact"),
    ("vegetable", "箭竹筍"): ProduceIconSpec("produce-vegetable-arrow-bamboo-shoot", "representative"),
    ("vegetable", "結球白菜"): ProduceIconSpec("produce-vegetable-napa-cabbage", "exact"),
    ("vegetable", "絲瓜"): ProduceIconSpec("produce-vegetable-loofah", "exact"),
    ("vegetable", "綠竹筍"): ProduceIconSpec("produce-vegetable-green-bamboo-shoot", "representative"),
    ("vegetable", "胡瓜"): ProduceIconSpec("produce-vegetable-cucumber", "exact"),
    ("vegetable", "花椰菜"): ProduceIconSpec("produce-vegetable-cauliflower", "exact"),
    ("vegetable", "苦瓜"): ProduceIconSpec("produce-vegetable-bitter-melon", "exact"),
    ("vegetable", "茄子"): ProduceIconSpec("produce-vegetable-eggplant", "exact"),
    ("vegetable", "茭白筍"): ProduceIconSpec("produce-vegetable-water-bamboo", "representative"),
    ("vegetable", "菇類"): ProduceIconSpec("produce-vegetable-mushrooms", "representative"),
    ("vegetable", "蘿蔔"): ProduceIconSpec("produce-vegetable-radish", "representative"),
    ("vegetable", "辣椒"): ProduceIconSpec("produce-vegetable-chili", "exact"),
    ("vegetable", "金針"): ProduceIconSpec("produce-vegetable-daylily-bud", "representative"),
    ("vegetable", "長豇豆"): ProduceIconSpec("produce-vegetable-yardlong-bean", "exact"),
    ("vegetable", "青蔥"): ProduceIconSpec("produce-vegetable-scallion", "exact"),
    ("vegetable", "麻竹筍"): ProduceIconSpec("produce-vegetable-makino-bamboo-shoot", "representative"),
}

FALLBACK_ICON_REGISTRY = {
    "fruit": ProduceIconSpec("produce-fruit-fallback", "category_fallback"),
    "vegetable": ProduceIconSpec("produce-vegetable-fallback", "category_fallback"),
}


def validate_produce_icon_registry():
    if set(FALLBACK_ICON_REGISTRY) != set(CATEGORIES):
        raise ValueError("produce icon fallbacks must cover fruit and vegetable")
    symbol_ids = []
    for key, spec in PRODUCE_ICON_REGISTRY.items():
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("produce icon registry keys must be category/name tuples")
        category, display_name = key
        if category not in CATEGORIES:
            raise ValueError("invalid produce icon category")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("invalid produce icon display name")
        if spec.fidelity not in ("exact", "representative"):
            raise ValueError("registered produce icon fidelity must be exact or representative")
        symbol_ids.append(spec.symbol_id)
    for category, spec in FALLBACK_ICON_REGISTRY.items():
        if category not in CATEGORIES or spec.fidelity != "category_fallback":
            raise ValueError("invalid produce icon fallback")
        symbol_ids.append(spec.symbol_id)
    if any(not isinstance(symbol_id, str) or not _SAFE_SYMBOL_ID.fullmatch(symbol_id) for symbol_id in symbol_ids):
        raise ValueError("unsafe produce icon symbol id")
    if len(symbol_ids) != len(set(symbol_ids)):
        raise ValueError("produce icon symbol ids must be unique")
    return frozenset(symbol_ids)


def resolve_produce_icon(category, display_name):
    if category not in CATEGORIES:
        raise ValueError("invalid produce icon category")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("invalid produce icon display name")
    return PRODUCE_ICON_REGISTRY.get((category, display_name), FALLBACK_ICON_REGISTRY[category])


def _local_name(value):
    return value.rsplit("}", 1)[-1]


def validate_produce_icon_sprite(content):
    expected = validate_produce_icon_registry()
    if not isinstance(content, bytes) or not content:
        raise ValueError("produce icon sprite must be non-empty bytes")
    if len(content) > SPRITE_MAX_BYTES:
        raise ValueError("produce icon sprite exceeds 64 KiB")
    lowered = content.lower()
    if any(token in lowered for token in (b"<!doctype", b"<!entity", b"<?", b"data:")):
        raise ValueError("produce icon sprite contains a prohibited external construct")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("produce icon sprite is not valid XML") from exc
    if root.tag != f"{{{_SVG_NAMESPACE}}}svg":
        raise ValueError("produce icon sprite root must be SVG")
    if any(_local_name(child.tag) != "symbol" for child in root):
        raise ValueError("produce icon sprite root may contain only symbols")
    symbol_ids = []
    all_ids = []
    for element in root.iter():
        if not isinstance(element.tag, str) or not element.tag.startswith(f"{{{_SVG_NAMESPACE}}}"):
            raise ValueError("produce icon sprite elements must use the SVG namespace")
        element_name = _local_name(element.tag)
        if element_name not in _ALLOWED_SVG_ELEMENTS:
            raise ValueError("produce icon sprite contains a prohibited element")
        for raw_name, raw_value in element.attrib.items():
            name = _local_name(raw_name).lower()
            value = str(raw_value).lower()
            if raw_name != _local_name(raw_name) or name not in _ALLOWED_SVG_ATTRIBUTES[element_name]:
                raise ValueError("produce icon sprite contains a prohibited attribute")
            if any(token in value for token in ("url(", "javascript:", "data:", "http:", "https:")):
                raise ValueError("produce icon sprite contains an external attribute value")
            if name == "id":
                all_ids.append(raw_value)
        if element_name == "symbol":
            symbol_id = element.get("id")
            if not symbol_id or not _SAFE_SYMBOL_ID.fullmatch(symbol_id):
                raise ValueError("produce icon sprite has an unsafe symbol id")
            if element.get("viewBox") != "0 0 24 24":
                raise ValueError("produce icon symbols must use viewBox 0 0 24 24")
            expected_style = {
                "fill": "none", "stroke": "currentColor", "stroke-width": "1.75",
                "stroke-linecap": "round", "stroke-linejoin": "round",
            }
            if any(element.get(name) != value for name, value in expected_style.items()) or not list(element):
                raise ValueError("produce icon symbols must use the shared non-empty line style")
            symbol_ids.append(symbol_id)
    if len(symbol_ids) != len(set(symbol_ids)):
        raise ValueError("produce icon sprite symbol ids must be unique")
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("produce icon sprite ids must be globally unique")
    if frozenset(symbol_ids) != expected:
        raise ValueError("produce icon sprite and registry symbol sets differ")
    return frozenset(symbol_ids)


def read_produce_icon_sprite(path=SPRITE_PATH):
    content = Path(path).read_bytes()
    validate_produce_icon_sprite(content)
    return content
