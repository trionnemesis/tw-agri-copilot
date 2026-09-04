"""Strict contract for the site-wide produce category registry.

``config/produce-categories.json`` is the single source of truth for which
produce categories exist, whether each has an official (item x county x
month) season registry, and which categories participate in the market
watchlist and Buy Score. This replaces the fifteen call sites that used to
hard-code the fruit/vegetable binary (Issue #44 Part B, work order section
6.1 / section 7).

Livestock and aquaculture are registered with
``season_semantics = "no_official_season_registry"``: the agency has not
published an (item x county x month) season registry for either today
(Issue #44 BC-2 / BC-3), so ``tpw.season_map`` and ``tpw.season_extensions``
must always resolve their county cells to an explicit ``unknown`` instead of
guessing (SPEC.md section 6.2, implementation requirement 6 -- cited
throughout this codebase as "SPEC section 6.2.6").
"""

from __future__ import annotations

import functools
import hashlib
import json
import pathlib
import re
import urllib.parse
from dataclasses import dataclass


CATEGORY_REGISTRY_PATH = pathlib.PurePosixPath("config/produce-categories.json")
SEASON_SEMANTICS = frozenset({"official_season_registry", "no_official_season_registry"})
# The rule this cites: SPEC.md section 6.2, implementation requirement 6 -- an item absent
# from the season data MUST read as unknown, never as out-of-season. Issue #44 BC-2 is the
# concrete case (livestock has no official season registry at all); BC-3 (aquaculture) is
# the same rule applied to a second category. tpw.season_map and tpw.season_extensions both
# cite this constant so the two enforcement points can never drift in wording.
NO_OFFICIAL_SEASON_REGISTRY_CITATION = "SPEC §6.2.6, Issue #44 BC-2"
CATEGORY_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
SOURCE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*")
_ENTRY_FIELDS = frozenset({
    "id", "label", "season_semantics", "season_source",
    "market_watchlist", "buy_score_eligible", "icon_fallback_symbol", "note",
})
_SEASON_SOURCE_FIELDS = frozenset({"source_id", "source_url", "allowed_hosts"})
_BUY_SCORE_ELIGIBLE_IDS = frozenset({"fruit", "vegetable"})
_REQUIRED_WATCHLIST_CATEGORIES = ("fruit", "vegetable")


class CategoryRegistryError(ValueError):
    """A checked-in produce category registry violated its contract."""


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    season_semantics: str
    season_source: dict | None
    market_watchlist: bool
    buy_score_eligible: bool
    icon_fallback_symbol: str
    note: str


@dataclass(frozen=True)
class CategoryRegistry:
    categories: tuple[Category, ...]
    content_hash: str

    def ids(self):
        """Registered category ids, in checked-in (display) order."""
        return tuple(category.id for category in self.categories)

    def by_id(self, category_id):
        for category in self.categories:
            if category.id == category_id:
                return category
        raise CategoryRegistryError(f"unknown produce category: {category_id!r}")

    def official_ids(self):
        return tuple(category.id for category in self.categories if category.season_semantics == "official_season_registry")

    def no_official(self):
        return [category for category in self.categories if category.season_semantics == "no_official_season_registry"]

    def watchlist_ids(self):
        return tuple(category.id for category in self.categories if category.market_watchlist)


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise CategoryRegistryError("produce category registry JSON contains a duplicate key")
        value[key] = item
    return value


def _reject_constant(value):
    raise CategoryRegistryError(f"produce category registry JSON contains non-standard constant {value}")


def _nonempty_text(value, label):
    if not isinstance(value, str) or not value or value != value.strip():
        raise CategoryRegistryError(f"{label} must be a non-empty trimmed string")
    return value


def _https_source_url(value, allowed_hosts, label):
    _nonempty_text(value, label)
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise CategoryRegistryError(f"{label} is not a valid URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path
        or parsed.fragment
    ):
        raise CategoryRegistryError(f"{label} must use an allowlisted HTTPS URL")
    return value


def validate_category_registry(payload, content_hash):
    """Validate a parsed produce-categories.json payload and return a CategoryRegistry.

    ``content_hash`` is attached to the returned registry as-is (it is not itself
    format-checked here); ``load_category_registry`` is what guarantees it is really
    ``"sha256:" + sha256(file bytes)``, so in-memory tests may pass any placeholder.
    """
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "categories"}:
        raise CategoryRegistryError("produce category registry fields do not match the contract")
    if payload["schema_version"] != "1.0":
        raise CategoryRegistryError("produce category registry schema version is invalid")
    raw_categories = payload["categories"]
    if not isinstance(raw_categories, list) or not raw_categories:
        raise CategoryRegistryError("produce category registry must contain at least one category")

    categories = []
    ids = []
    labels = []
    for raw in raw_categories:
        if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
            raise CategoryRegistryError("produce category entry fields do not match the contract")
        category_id = raw["id"]
        if not isinstance(category_id, str) or not CATEGORY_ID_PATTERN.fullmatch(category_id):
            raise CategoryRegistryError("produce category id must match ^[a-z][a-z0-9_]*$: " + repr(category_id))
        label = _nonempty_text(raw["label"], f"produce category {category_id} label")
        semantics = raw["season_semantics"]
        if semantics not in SEASON_SEMANTICS:
            raise CategoryRegistryError(f"produce category {category_id} season_semantics is invalid")

        season_source = raw["season_source"]
        if semantics == "official_season_registry":
            if not isinstance(season_source, dict) or set(season_source) != _SEASON_SOURCE_FIELDS:
                raise CategoryRegistryError(f"produce category {category_id} requires a season_source")
            source_id = season_source["source_id"]
            if not isinstance(source_id, str) or not SOURCE_ID_PATTERN.fullmatch(source_id):
                raise CategoryRegistryError(f"produce category {category_id} season_source.source_id is invalid")
            allowed_hosts = season_source["allowed_hosts"]
            if (
                not isinstance(allowed_hosts, list)
                or not allowed_hosts
                or len(allowed_hosts) != len(set(allowed_hosts))
                or any(not isinstance(host, str) or not host.strip() for host in allowed_hosts)
            ):
                raise CategoryRegistryError(f"produce category {category_id} season_source.allowed_hosts must be a non-empty unique list")
            _https_source_url(season_source["source_url"], set(allowed_hosts), f"produce category {category_id} season_source.source_url")
        elif season_source is not None:
            raise CategoryRegistryError(f"produce category {category_id} must not declare a season_source")

        market_watchlist = raw["market_watchlist"]
        buy_score_eligible = raw["buy_score_eligible"]
        if not isinstance(market_watchlist, bool):
            raise CategoryRegistryError(f"produce category {category_id} market_watchlist must be a boolean")
        if not isinstance(buy_score_eligible, bool):
            raise CategoryRegistryError(f"produce category {category_id} buy_score_eligible must be a boolean")
        if buy_score_eligible and category_id not in _BUY_SCORE_ELIGIBLE_IDS:
            raise CategoryRegistryError(
                "produce category buy_score_eligible=true is only allowed for fruit or vegetable "
                "(SPEC.md section 9.2.1): " + repr(category_id)
            )

        icon_fallback_symbol = raw["icon_fallback_symbol"]
        expected_symbol = f"produce-{category_id}-fallback"
        if icon_fallback_symbol != expected_symbol:
            raise CategoryRegistryError(
                f"produce category {category_id} icon_fallback_symbol must be {expected_symbol!r}"
            )
        note = _nonempty_text(raw["note"], f"produce category {category_id} note")

        categories.append(Category(
            id=category_id,
            label=label,
            season_semantics=semantics,
            season_source=season_source,
            market_watchlist=market_watchlist,
            buy_score_eligible=buy_score_eligible,
            icon_fallback_symbol=icon_fallback_symbol,
            note=note,
        ))
        ids.append(category_id)
        labels.append(label)

    if len(ids) != len(set(ids)):
        raise CategoryRegistryError("produce category ids must be unique")
    if len(labels) != len(set(labels)):
        raise CategoryRegistryError("produce category labels must be unique")

    by_id = {category.id: category for category in categories}
    for required_id in _REQUIRED_WATCHLIST_CATEGORIES:
        category = by_id.get(required_id)
        if category is None or category.season_semantics != "official_season_registry" or not category.market_watchlist:
            raise CategoryRegistryError(
                f"produce category registry must contain {required_id!r} as an "
                "official_season_registry watchlist category (SPEC.md section 7.2.5 / 11.7)"
            )

    return CategoryRegistry(categories=tuple(categories), content_hash=content_hash)


def load_category_registry(root):
    """Load and validate config/produce-categories.json from an explicit repository root.

    CLI code (tpw.cli) MUST call this with its own ROOT so hermetic tests that copy the
    repository into a temporary directory see their own (possibly modified) registry file.
    """
    root = pathlib.Path(root)
    path = root / CATEGORY_REGISTRY_PATH
    try:
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8")
        payload = json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except CategoryRegistryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CategoryRegistryError("produce category registry must be valid UTF-8 JSON") from exc
    content_hash = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
    return validate_category_registry(payload, content_hash)


@functools.lru_cache(maxsize=1)
def default_category_registry():
    """The checked-in registry, loaded once per process from this file's own repository.

    The root is inferred from this module's location
    (``pathlib.Path(__file__).resolve().parents[2]``), NOT from any test-isolation seam --
    it is not aware of ``mock.patch('tpw.cli.ROOT', ...)``. Callers that have an explicit
    root available (tpw.cli, and anything reachable from it) MUST call
    ``load_category_registry(root)`` instead, or a hermetic test that edits a temporary
    copy of config/produce-categories.json will silently keep reading the real one. This
    default exists only for callers with no root to pass, such as tpw.render and direct
    unit tests of a single well-known category.
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    return load_category_registry(root)


def category_label(category_id, registry=None):
    """Human label for a category id; raises CategoryRegistryError on an unknown id.

    This is the loud-failure replacement for the ``'水果' if category == 'fruit' else '蔬菜'``
    ternaries that used to be scattered across tpw.render: an unrecognised category is a bug,
    never a silent fallback to one of the two original labels.
    """
    registry = registry or default_category_registry()
    return registry.by_id(category_id).label
