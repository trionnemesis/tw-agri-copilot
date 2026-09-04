import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

from tpw.categories import (
    CategoryRegistryError,
    SEASON_SEMANTICS,
    category_label,
    default_category_registry,
    load_category_registry,
    validate_category_registry,
)


ROOT = pathlib.Path(__file__).parents[2]
_PLACEHOLDER_HASH = "sha256:" + "0" * 64


def _valid_payload():
    return copy.deepcopy(json.loads((ROOT / "config/produce-categories.json").read_text(encoding="utf-8")))


class CheckedInRegistryTest(unittest.TestCase):
    def test_checked_in_registry_loads_four_categories_in_order(self):
        registry = load_category_registry(ROOT)
        self.assertEqual(registry.ids(), ("fruit", "vegetable", "livestock", "aquaculture"))
        self.assertEqual(registry.watchlist_ids(), ("fruit", "vegetable"))
        self.assertEqual(registry.official_ids(), ("fruit", "vegetable"))
        self.assertEqual([category.id for category in registry.no_official()], ["livestock", "aquaculture"])
        self.assertEqual(registry.by_id("fruit").label, "水果")
        self.assertEqual(registry.by_id("livestock").season_semantics, "no_official_season_registry")
        self.assertIsNone(registry.by_id("aquaculture").season_source)

    def test_content_hash_matches_the_registry_file_bytes(self):
        registry = load_category_registry(ROOT)
        expected = "sha256:" + hashlib.sha256((ROOT / "config/produce-categories.json").read_bytes()).hexdigest()
        self.assertEqual(registry.content_hash, expected)

    def test_default_registry_matches_the_explicitly_loaded_registry(self):
        self.assertEqual(default_category_registry().ids(), load_category_registry(ROOT).ids())
        self.assertEqual(default_category_registry().content_hash, load_category_registry(ROOT).content_hash)

    def test_by_id_raises_on_unknown_category(self):
        registry = load_category_registry(ROOT)
        with self.assertRaises(CategoryRegistryError):
            registry.by_id("grain")

    def test_category_label_resolves_and_unknown_id_raises(self):
        self.assertEqual(category_label("fruit"), "水果")
        self.assertEqual(category_label("vegetable"), "蔬菜")
        self.assertEqual(category_label("livestock"), "畜產")
        self.assertEqual(category_label("aquaculture"), "養殖水產")
        with self.assertRaises(CategoryRegistryError):
            category_label("grain")


class ValidateCategoryRegistryTest(unittest.TestCase):
    def test_valid_fixture_round_trips_in_checked_in_order(self):
        payload = _valid_payload()
        registry = validate_category_registry(payload, _PLACEHOLDER_HASH)
        self.assertEqual(registry.ids(), tuple(entry["id"] for entry in payload["categories"]))
        self.assertEqual(registry.content_hash, _PLACEHOLDER_HASH)

    def test_duplicate_id_fails_closed(self):
        payload = _valid_payload()
        duplicate_id = payload["categories"][0]["id"]
        payload["categories"][1]["id"] = duplicate_id
        # Keep the mutated entry's icon_fallback_symbol consistent with its new id so this
        # isolates the duplicate-id rule rather than tripping the icon_fallback_symbol rule.
        payload["categories"][1]["icon_fallback_symbol"] = f"produce-{duplicate_id}-fallback"
        with self.assertRaisesRegex(CategoryRegistryError, "unique"):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_invalid_id_pattern_fails_closed(self):
        for bad_id in ("Fruit", "1fruit", "fruit-x", "", "fruit x"):
            with self.subTest(bad_id=bad_id):
                payload = _valid_payload()
                payload["categories"][0]["id"] = bad_id
                # icon_fallback_symbol also needs to keep matching so this rejects on the id
                # pattern itself, not on the (also-invalid) icon_fallback_symbol mismatch.
                payload["categories"][0]["icon_fallback_symbol"] = f"produce-{bad_id}-fallback"
                with self.assertRaises(CategoryRegistryError):
                    validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_duplicate_label_fails_closed(self):
        payload = _valid_payload()
        payload["categories"][1]["label"] = payload["categories"][0]["label"]
        with self.assertRaisesRegex(CategoryRegistryError, "unique"):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_untrimmed_or_empty_label_fails_closed(self):
        for bad_label in (" 水果", "水果 ", "", "   "):
            with self.subTest(bad_label=bad_label):
                payload = _valid_payload()
                payload["categories"][0]["label"] = bad_label
                with self.assertRaises(CategoryRegistryError):
                    validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_invalid_season_semantics_fails_closed(self):
        payload = _valid_payload()
        payload["categories"][0]["season_semantics"] = "guessed_seasonal"
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_season_source_required_iff_official(self):
        # official_season_registry without a season_source.
        payload = _valid_payload()
        payload["categories"][0]["season_source"] = None
        with self.assertRaisesRegex(CategoryRegistryError, "season_source"):
            validate_category_registry(payload, _PLACEHOLDER_HASH)
        # no_official_season_registry that declares one anyway.
        payload = _valid_payload()
        payload["categories"][2]["season_source"] = {
            "source_id": "x", "source_url": "https://example.invalid/a", "allowed_hosts": ["example.invalid"],
        }
        with self.assertRaisesRegex(CategoryRegistryError, "season_source"):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_season_source_url_must_be_https_and_allowlisted(self):
        payload = _valid_payload()
        payload["categories"][0]["season_source"]["source_url"] = "http://www.afa.gov.tw/cht/index.php?code=list&ids=1103"
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)
        payload = _valid_payload()
        payload["categories"][0]["season_source"]["source_url"] = "https://example.invalid/a"
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_season_source_allowed_hosts_must_be_non_empty(self):
        payload = _valid_payload()
        payload["categories"][0]["season_source"]["allowed_hosts"] = []
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_buy_score_eligible_only_allowed_for_fruit_and_vegetable(self):
        payload = _valid_payload()
        payload["categories"][2]["buy_score_eligible"] = True
        with self.assertRaisesRegex(CategoryRegistryError, "buy_score_eligible"):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_fruit_and_vegetable_must_stay_official_watchlist_categories(self):
        payload = _valid_payload()
        payload["categories"][0]["market_watchlist"] = False
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)
        payload = _valid_payload()
        payload["categories"] = [entry for entry in payload["categories"] if entry["id"] != "vegetable"]
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_icon_fallback_symbol_must_match_produce_id_fallback(self):
        payload = _valid_payload()
        payload["categories"][0]["icon_fallback_symbol"] = "produce-vegetable-fallback"
        with self.assertRaisesRegex(CategoryRegistryError, "icon_fallback_symbol"):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_unknown_top_level_field_fails_closed(self):
        payload = _valid_payload()
        payload["unexpected"] = True
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_wrong_schema_version_fails_closed(self):
        payload = _valid_payload()
        payload["schema_version"] = "2.0"
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_missing_entry_field_fails_closed(self):
        payload = _valid_payload()
        del payload["categories"][0]["note"]
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_extra_entry_field_fails_closed(self):
        payload = _valid_payload()
        payload["categories"][0]["unexpected"] = True
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_empty_categories_list_fails_closed(self):
        payload = _valid_payload()
        payload["categories"] = []
        with self.assertRaises(CategoryRegistryError):
            validate_category_registry(payload, _PLACEHOLDER_HASH)

    def test_registry_order_is_preserved_not_resorted(self):
        payload = _valid_payload()
        payload["categories"] = [payload["categories"][1], payload["categories"][0]] + payload["categories"][2:]
        registry = validate_category_registry(payload, _PLACEHOLDER_HASH)
        self.assertEqual(registry.ids(), ("vegetable", "fruit", "livestock", "aquaculture"))


class LoadCategoryRegistryStrictJSONTest(unittest.TestCase):
    def test_duplicate_json_key_is_rejected(self):
        raw = (ROOT / "config/produce-categories.json").read_text(encoding="utf-8")
        duplicated = raw.replace('"schema_version": "1.0"', '"schema_version": "1.0", "schema_version": "1.0"', 1)
        with tempfile.TemporaryDirectory() as raw_dir:
            root = pathlib.Path(raw_dir)
            (root / "config").mkdir()
            (root / "config/produce-categories.json").write_text(duplicated, encoding="utf-8")
            with self.assertRaises(CategoryRegistryError):
                load_category_registry(root)

    def test_non_standard_json_constant_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            root = pathlib.Path(raw_dir)
            (root / "config").mkdir()
            (root / "config/produce-categories.json").write_text(
                '{"schema_version":"1.0","categories":[NaN]}', encoding="utf-8",
            )
            with self.assertRaises(CategoryRegistryError):
                load_category_registry(root)

    def test_absent_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            root = pathlib.Path(raw_dir)
            (root / "config").mkdir()
            with self.assertRaises(CategoryRegistryError):
                load_category_registry(root)


class SchemaConsistencyTest(unittest.TestCase):
    def test_schema_file_parses_and_semantics_enum_matches_the_code_constant(self):
        schema = json.loads((ROOT / "schema/produce-categories.schema.json").read_text(encoding="utf-8"))
        item_schema = schema["properties"]["categories"]["items"]
        self.assertEqual(set(item_schema["properties"]["season_semantics"]["enum"]), SEASON_SEMANTICS)
        self.assertEqual(schema["additionalProperties"], False)
        self.assertEqual(item_schema["additionalProperties"], False)

    def test_season_map_schema_category_enums_match_the_registry_ids(self):
        registry = load_category_registry(ROOT)
        schema = json.loads((ROOT / "schema/season-map.schema.json").read_text(encoding="utf-8"))
        categories_id_enum = schema["properties"]["categories"]["items"]["properties"]["id"]["enum"]
        produce_category_enum = (
            schema["properties"]["counties"]["items"]["properties"]["local_seasonal_produce"]
            ["items"]["properties"]["category"]["enum"]
        )
        self.assertEqual(set(categories_id_enum), set(registry.ids()))
        self.assertEqual(set(produce_category_enum), set(registry.ids()))
        self.assertEqual(schema["properties"]["schema_version"], {"const": "1.1"})


if __name__ == "__main__":
    unittest.main()
