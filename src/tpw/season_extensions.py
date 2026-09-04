"""Contract for the optional, human-curated seasonality extension slot.

Issue #44 Part B keeps livestock and aquaculture out of the official AFA season
catalog: there is no S-grade official (item x county x month) season registry
for either category today (SPEC.md section 6.2, implementation requirement 6;
Issue #44 BC-2 / BC-3). This module defines where a *future*, separately
reviewed adapter for a newly-official category would write its monthly rows --
``data/seasonality/extensions/<YYYY-MM>.json`` -- and the strict, fail-closed
contract those rows must satisfy before ``tpw.cli`` merges them into the
published catalog (work order section 6.4).

No extension file is committed by this work order. ``load_extension_catalog``
returns an empty list when the file for a month is absent, which is exactly
today's live-publication behaviour: merging in an empty list is a no-op, so
the AFA-only catalog is unaffected until a real adapter, with S-grade
discovery evidence, is added in its own reviewed change.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import urllib.parse

from .categories import CategoryRegistryError, NO_OFFICIAL_SEASON_REGISTRY_CITATION
from .season_map import SOURCE_STATUSES
from .seasonality import CATEGORIES as _AFA_CATEGORIES


EXTENSION_DIR = pathlib.PurePosixPath("data/seasonality/extensions")
# The AFA catalog row shape (see tpw.seasonality.build_catalog) plus source_id, which the
# AFA rows do not carry because tpw.seasonality.SOURCE_URL is a single module constant --
# an extension row can come from any registered official_season_registry category, so it
# must say which source_id it satisfies.
REQUIRED_FIELDS = frozenset({
    "schema_version", "month", "canonical_id", "display_name", "source_display_names",
    "category", "counties", "county_count", "district_count", "varieties", "variety_count",
    "source_url", "source_status", "fetched_at", "source_id",
})
# fruit/vegetable rows may only come from the AFA adapter (tpw.seasonality); this is a
# structural fact about which adapter owns which category's season rows, not something
# derived from a registry flag (market_watchlist/buy_score_eligible are orthogonal to
# "who is allowed to publish this category's season catalog"). Derived from
# tpw.seasonality.CATEGORIES (rather than hard-coded again) so the two can never drift.
AFA_OWNED_CATEGORIES = frozenset(_AFA_CATEGORIES)


class SeasonExtensionError(ValueError):
    """A checked-in or loaded seasonality extension file violated its contract."""


def extension_path(root, month):
    return pathlib.Path(root) / EXTENSION_DIR / (month + ".json")


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SeasonExtensionError("seasonality extension JSON contains a duplicate key")
        value[key] = item
    return value


def _reject_constant(value):
    raise SeasonExtensionError(f"seasonality extension JSON contains non-standard constant {value}")


def _nonempty_text(value, label):
    if not isinstance(value, str) or not value or value != value.strip():
        raise SeasonExtensionError(f"{label} must be a non-empty trimmed string")
    return value


def _nonnegative_int(value, label):
    # bool is an int subclass and 1.0 == 1 in Python, so both would otherwise silently pass an
    # `== len(...)` check; reject them explicitly rather than let a malformed count reach
    # site/data/current.json and render literally (e.g. "True 個產地縣市").
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SeasonExtensionError(f"{label} must be a non-negative integer")
    return value


def _real_month(value, label="month"):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise SeasonExtensionError(f"{label} must use YYYY-MM")
    try:
        dt.date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise SeasonExtensionError(f"{label} must be a real month") from exc
    return value


def _https_url(value, allowed_hosts, label):
    _nonempty_text(value, label)
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise SeasonExtensionError(f"{label} is not a valid URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path
        or parsed.fragment
    ):
        raise SeasonExtensionError(f"{label} must use an allowlisted HTTPS URL")
    return value


def validate_extension_rows(rows, month, registry):
    """Validate a parsed extension file's rows and return them sorted by (category, display_name)."""
    _real_month(month, "seasonality extension request month")
    if not isinstance(rows, list):
        raise SeasonExtensionError("seasonality extension file must be a JSON list")

    seen_keys = set()
    status_by_category = {}
    validated = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != REQUIRED_FIELDS:
            raise SeasonExtensionError(
                "seasonality extension row fields do not match the AFA catalog row contract plus source_id"
            )
        if row["schema_version"] != "1.0":
            raise SeasonExtensionError("seasonality extension row schema_version is invalid")
        if row["month"] != month:
            raise SeasonExtensionError("seasonality extension row month does not match the requested month")

        category_id = row["category"]
        try:
            category = registry.by_id(category_id)
        except CategoryRegistryError as exc:
            raise SeasonExtensionError("seasonality extension row category is unregistered: " + repr(category_id)) from exc
        if category.season_semantics == "no_official_season_registry":
            raise SeasonExtensionError(
                "seasonality extension row uses a category with no official season registry "
                "(" + NO_OFFICIAL_SEASON_REGISTRY_CITATION + "): " + repr(category_id)
            )
        if category_id in AFA_OWNED_CATEGORIES:
            raise SeasonExtensionError(
                "seasonality extension rows must not use an AFA-owned category "
                "(fruit/vegetable can only come from the AFA adapter): " + repr(category_id)
            )

        display_name = _nonempty_text(row["display_name"], "seasonality extension display_name")
        key = (category_id, display_name)
        if key in seen_keys:
            raise SeasonExtensionError("seasonality extension contains a duplicate (category, display_name): " + repr(key))
        seen_keys.add(key)

        status = row["source_status"]
        if status not in SOURCE_STATUSES:
            raise SeasonExtensionError("seasonality extension source_status is invalid")
        existing_status = status_by_category.get(category_id)
        if existing_status is not None and existing_status != status:
            raise SeasonExtensionError("seasonality extension must use one source_status per category: " + repr(category_id))
        status_by_category[category_id] = status

        season_source = category.season_source or {}
        if row["source_id"] != season_source.get("source_id"):
            raise SeasonExtensionError(
                "seasonality extension source_id does not match the category's registered season_source: "
                + repr(category_id)
            )
        allowed_hosts = season_source.get("allowed_hosts") or []
        _https_url(row["source_url"], allowed_hosts, "seasonality extension source_url")

        if row["canonical_id"] is not None:
            raise SeasonExtensionError("seasonality extension canonical_id must be null")

        source_display_names = row["source_display_names"]
        if not isinstance(source_display_names, list) or not source_display_names:
            raise SeasonExtensionError("seasonality extension source_display_names must be a non-empty list")
        for name in source_display_names:
            _nonempty_text(name, "seasonality extension source display name")

        counties = row["counties"]
        if not isinstance(counties, list) or not counties or len(counties) != len(set(counties)):
            raise SeasonExtensionError("seasonality extension counties must be a unique non-empty list")
        for county in counties:
            _nonempty_text(county, "seasonality extension county")
        county_count = _nonnegative_int(row["county_count"], "seasonality extension county_count")
        if county_count != len(counties):
            raise SeasonExtensionError("seasonality extension county_count does not match counties")

        varieties = row["varieties"]
        if not isinstance(varieties, list):
            raise SeasonExtensionError("seasonality extension varieties must be a list")
        for variety in varieties:
            _nonempty_text(variety, "seasonality extension variety")
        variety_count = _nonnegative_int(row["variety_count"], "seasonality extension variety_count")
        if variety_count != len(varieties):
            raise SeasonExtensionError("seasonality extension variety_count does not match varieties")

        _nonnegative_int(row["district_count"], "seasonality extension district_count")

        _nonempty_text(row["fetched_at"], "seasonality extension fetched_at")

        validated.append(dict(row))

    return sorted(validated, key=lambda item: (item["category"], item["display_name"]))


def load_extension_catalog(root, month, registry):
    """Load and validate data/seasonality/extensions/<month>.json; [] when the file is absent."""
    path = extension_path(root, month)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        rows = json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except SeasonExtensionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SeasonExtensionError("seasonality extension file must be valid UTF-8 JSON") from exc
    return validate_extension_rows(rows, month, registry)


def merge_season_catalog(afa_rows, extension_rows):
    """Merge AFA catalog rows with validated extension rows, by display_name.

    The committed AFA catalog is already sorted by display_name (see
    ``tpw.seasonality.build_catalog``), and Python's ``sorted`` is stable, so with no
    extension rows (today's live-publication default) this returns a list equal to
    ``afa_rows``, in the same order. Extension rows are inserted only where their own
    display_name places them; ties keep their relative input order.
    """
    return sorted(list(afa_rows) + list(extension_rows), key=lambda row: row["display_name"])
