import json
import pathlib
import tempfile
import unittest

from tpw.categories import load_category_registry
from tpw.season_extensions import (
    SeasonExtensionError,
    extension_path,
    load_extension_catalog,
    merge_season_catalog,
    validate_extension_rows,
)


ROOT = pathlib.Path(__file__).parents[2]

# A test-only official_season_registry category, never committed to config/produce-categories.json:
# only ever written into a temporary copy of that file, per the work order's ban on committing any
# livestock/aquaculture (or other non-fruit/vegetable) season data.
TEST_FISHERY_CATEGORY = {
    "id": "test_fishery",
    "label": "測試漁產",
    "season_semantics": "official_season_registry",
    "season_source": {
        "source_id": "test_fishery_source",
        "source_url": "https://example.test/season",
        "allowed_hosts": ["example.test"],
    },
    "market_watchlist": False,
    "buy_score_eligible": False,
    "icon_fallback_symbol": "produce-test_fishery-fallback",
    "note": "測試用",
}


def _extension_row(**overrides):
    row = {
        "schema_version": "1.0",
        "month": "2026-09",
        "canonical_id": None,
        "display_name": "測試魚甲",
        "source_display_names": ["測試魚甲"],
        "category": "test_fishery",
        "counties": ["臺南市", "嘉義縣"],
        "county_count": 2,
        "district_count": 3,
        "varieties": [],
        "variety_count": 0,
        "source_url": "https://example.test/season",
        "source_status": "live",
        "fetched_at": "fixture",
        "source_id": "test_fishery_source",
    }
    row.update(overrides)
    return row


class _IsolatedRegistryCase(unittest.TestCase):
    """A temp repo copy whose produce-categories.json adds one test-only category.

    No livestock/aquaculture/other real-world season data is ever written -- only this
    synthetic, clearly-fake test_fishery category and rows, confined to a TemporaryDirectory.
    """

    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = pathlib.Path(workspace.name)
        (self.root / "config").mkdir()
        payload = json.loads((ROOT / "config/produce-categories.json").read_text(encoding="utf-8"))
        payload = {**payload, "categories": payload["categories"] + [TEST_FISHERY_CATEGORY]}
        (self.root / "config/produce-categories.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )
        self.registry = load_category_registry(self.root)

    def write_extension(self, month, rows):
        path = extension_path(self.root, month)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


class ExtensionPathTest(unittest.TestCase):
    def test_extension_path_is_scoped_to_the_extensions_directory(self):
        root = pathlib.Path("/repo")
        self.assertEqual(extension_path(root, "2026-09"), root / "data/seasonality/extensions/2026-09.json")


class LoadExtensionCatalogTest(_IsolatedRegistryCase):
    def test_absent_file_returns_empty_list(self):
        self.assertEqual(load_extension_catalog(self.root, "2026-09", self.registry), [])

    def test_valid_extension_file_loads_and_sorts_by_category_then_display_name(self):
        self.write_extension("2026-09", [
            _extension_row(display_name="測試魚甲"),
            _extension_row(display_name="測試魚乙"),
        ])
        rows = load_extension_catalog(self.root, "2026-09", self.registry)
        self.assertEqual([row["display_name"] for row in rows], ["測試魚乙", "測試魚甲"])

    def test_malformed_json_is_rejected(self):
        path = extension_path(self.root, "2026-09")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(SeasonExtensionError):
            load_extension_catalog(self.root, "2026-09", self.registry)

    def test_duplicate_json_key_is_rejected(self):
        path = extension_path(self.root, "2026-09")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[{"month":"2026-09","month":"2026-09"}]', encoding="utf-8")
        with self.assertRaises(SeasonExtensionError):
            load_extension_catalog(self.root, "2026-09", self.registry)


class ValidateExtensionRowsTest(_IsolatedRegistryCase):
    def test_valid_row_round_trips(self):
        rows = validate_extension_rows([_extension_row()], "2026-09", self.registry)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["display_name"], "測試魚甲")

    def test_non_official_season_registry_category_is_rejected_with_citation(self):
        for category in ("livestock", "aquaculture"):
            with self.subTest(category=category):
                with self.assertRaises(SeasonExtensionError) as ctx:
                    validate_extension_rows([_extension_row(category=category)], "2026-09", self.registry)
                message = str(ctx.exception)
                self.assertIn("6.2.6", message)
                self.assertIn("BC-2", message)

    def test_afa_owned_category_is_rejected(self):
        for category in ("fruit", "vegetable"):
            with self.subTest(category=category):
                with self.assertRaises(SeasonExtensionError):
                    validate_extension_rows([_extension_row(category=category)], "2026-09", self.registry)

    def test_unregistered_category_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(category="grain")], "2026-09", self.registry)

    def test_wrong_month_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(month="2026-08")], "2026-09", self.registry)

    def test_mixed_source_status_within_a_category_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows(
                [
                    _extension_row(display_name="測試魚甲", source_status="live"),
                    _extension_row(display_name="測試魚乙", source_status="stale"),
                ],
                "2026-09",
                self.registry,
            )

    def test_different_categories_may_still_use_different_status(self):
        # Not exercised by the checked-in registry (only one non-AFA category is registered
        # for tests), but the rule is per-category, not global: this proves the mixed-status
        # rejection above is keyed by category, not by "any two rows in the file".
        rows = validate_extension_rows(
            [_extension_row(display_name="測試魚甲", source_status="live"), _extension_row(display_name="測試魚乙", source_status="live")],
            "2026-09",
            self.registry,
        )
        self.assertEqual(len(rows), 2)

    def test_wrong_source_id_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(source_id="not_the_registered_source")], "2026-09", self.registry)

    def test_host_outside_allowlist_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(source_url="https://example.invalid/season")], "2026-09", self.registry)

    def test_non_https_source_url_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(source_url="http://example.test/season")], "2026-09", self.registry)

    def test_canonical_id_must_be_null(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(canonical_id="test-fishery-item")], "2026-09", self.registry)

    def test_duplicate_category_display_name_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(), _extension_row()], "2026-09", self.registry)

    def test_empty_or_untrimmed_display_name_is_rejected(self):
        for bad_name in ("", "  ", " 測試魚甲"):
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(SeasonExtensionError):
                    validate_extension_rows([_extension_row(display_name=bad_name)], "2026-09", self.registry)

    def test_county_count_mismatch_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(county_count=99)], "2026-09", self.registry)

    def test_duplicate_or_empty_counties_are_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(counties=["臺南市", "臺南市"], county_count=2)], "2026-09", self.registry)
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(counties=[], county_count=0)], "2026-09", self.registry)

    def test_variety_count_mismatch_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(varieties=["測試魚甲一號"], variety_count=0)], "2026-09", self.registry)

    def test_negative_district_count_is_rejected(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([_extension_row(district_count=-1)], "2026-09", self.registry)

    def test_missing_field_is_rejected(self):
        row = _extension_row()
        del row["fetched_at"]
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([row], "2026-09", self.registry)

    def test_extra_field_is_rejected(self):
        row = _extension_row()
        row["unexpected"] = True
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows([row], "2026-09", self.registry)

    def test_rows_must_be_a_list(self):
        with self.assertRaises(SeasonExtensionError):
            validate_extension_rows({"not": "a list"}, "2026-09", self.registry)


class MergeSeasonCatalogTest(unittest.TestCase):
    def test_merge_with_no_extension_rows_is_identical_to_the_committed_afa_catalog(self):
        afa_rows = json.loads((ROOT / "data/seasonality/catalog/2026-09.json").read_text(encoding="utf-8"))
        merged = merge_season_catalog(afa_rows, [])
        self.assertEqual(merged, afa_rows)
        self.assertEqual(
            json.dumps(merged, ensure_ascii=False, sort_keys=True),
            json.dumps(afa_rows, ensure_ascii=False, sort_keys=True),
        )

    def test_merge_inserts_extension_rows_by_display_name(self):
        afa_rows = [{"display_name": "木瓜"}, {"display_name": "芒果"}, {"display_name": "鳳梨"}]
        extension_rows = [{"display_name": "測試魚甲"}]
        merged = merge_season_catalog(afa_rows, extension_rows)
        self.assertEqual([row["display_name"] for row in merged], ["木瓜", "測試魚甲", "芒果", "鳳梨"])

    def test_merge_does_not_mutate_its_inputs(self):
        afa_rows = [{"display_name": "b"}, {"display_name": "d"}]
        extension_rows = [{"display_name": "c"}]
        merge_season_catalog(afa_rows, extension_rows)
        self.assertEqual(afa_rows, [{"display_name": "b"}, {"display_name": "d"}])
        self.assertEqual(extension_rows, [{"display_name": "c"}])


if __name__ == "__main__":
    unittest.main()
