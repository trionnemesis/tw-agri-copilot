import json
import pathlib
import unittest
import xml.etree.ElementTree as ET

from tpw.produce_icons import (
    FALLBACK_ICON_REGISTRY,
    ICON_FIDELITIES,
    PRODUCE_ICON_REGISTRY,
    SPRITE_MAX_BYTES,
    read_produce_icon_sprite,
    resolve_produce_icon,
    uncovered_display_names,
    validate_produce_icon_registry,
    validate_produce_icon_sprite,
)


ROOT = pathlib.Path(__file__).parents[2]


class ProduceIconTest(unittest.TestCase):
    def test_uncovered_catalog_names_are_reported_not_raised(self):
        # The published catalogue is the agency's full monthly list and rotates every month, so the
        # registry can only ever be a superset of one month. Coverage is reported, never asserted
        # equal, and an uncovered name still renders through the category fallback.
        rows = [
            {"category": "fruit", "display_name": "香蕉"},
            {"category": "vegetable", "display_name": "青蔥"},
            {"category": "fruit", "display_name": "尚未繪製的水果"},
        ]
        self.assertEqual(uncovered_display_names(rows), [("fruit", "尚未繪製的水果")])
        self.assertEqual(uncovered_display_names(rows[:2]), [])
        self.assertEqual(
            resolve_produce_icon("fruit", "尚未繪製的水果"), FALLBACK_ICON_REGISTRY["fruit"]
        )
        self.assertIn(("fruit", "釋迦"), PRODUCE_ICON_REGISTRY)
        self.assertNotIn(("fruit", "番荔枝"), PRODUCE_ICON_REGISTRY)

    def test_every_published_catalog_name_resolves_into_the_sprite(self):
        current = json.loads((ROOT / "site/data/current.json").read_text())
        symbol_ids = validate_produce_icon_registry()
        self.assertTrue(current["season_catalog"])
        for row in current["season_catalog"]:
            spec = resolve_produce_icon(row["category"], row["display_name"])
            self.assertIn(spec.symbol_id, symbol_ids)
            self.assertIn(spec.fidelity, ICON_FIDELITIES)

    def test_resolution_is_exact_and_unknown_names_use_only_category_fallback(self):
        banana = resolve_produce_icon("fruit", "香蕉")
        self.assertEqual((banana.symbol_id, banana.fidelity), ("produce-fruit-banana", "exact"))
        for value in (" 香蕉", "香蕉 ", "香蕉\u3000", "番荔枝", "BANANA", "<script>alert(1)</script>"):
            self.assertEqual(resolve_produce_icon("fruit", value), FALLBACK_ICON_REGISTRY["fruit"])
        self.assertEqual(resolve_produce_icon("vegetable", "香蕉"), FALLBACK_ICON_REGISTRY["vegetable"])
        self.assertEqual(resolve_produce_icon("vegetable", "新蔬菜"), FALLBACK_ICON_REGISTRY["vegetable"])

    def test_invalid_lookup_inputs_fail_closed(self):
        for category, display_name in (("all", "香蕉"), ("", "香蕉"), ("fruit", ""), ("fruit", "   "), ("fruit", None), ("fruit", 1)):
            with self.subTest(category=category, display_name=display_name):
                with self.assertRaises(ValueError):
                    resolve_produce_icon(category, display_name)

    def test_sprite_is_small_safe_and_has_exact_registry_symbol_set(self):
        content = read_produce_icon_sprite()
        symbol_ids = validate_produce_icon_sprite(content)
        self.assertLessEqual(len(content), SPRITE_MAX_BYTES)
        self.assertEqual(symbol_ids, validate_produce_icon_registry())
        self.assertEqual(len(symbol_ids), len(PRODUCE_ICON_REGISTRY) + len(FALLBACK_ICON_REGISTRY))
        root = ET.fromstring(content)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        lowered = content.lower()
        for forbidden in (b"<script", b"<!doctype", b"<!entity", b"data:", b"javascript:"):
            self.assertNotIn(forbidden, lowered)

    def test_sprite_validator_rejects_external_payloads_and_symbol_drift(self):
        content = read_produce_icon_sprite()
        with self.assertRaises(ValueError):
            validate_produce_icon_sprite(content.replace(b"</svg>", b"<!-- data:image/png;base64,AA -->\n</svg>"))
        with self.assertRaises(ValueError):
            validate_produce_icon_sprite(content.replace(b'fill="none"', b'fill="url(https://example.invalid/a.svg)"', 1))
        with self.assertRaises(ValueError):
            validate_produce_icon_sprite(content.replace(b'fill="none"', br'fill="\75 rl(\68 ttps://example.invalid/a.svg)"', 1))
        with self.assertRaises(ValueError):
            validate_produce_icon_sprite(content.replace(b'<path ', b'<path id="produce-fruit-banana" ', 1))
        with self.assertRaises(ValueError):
            validate_produce_icon_sprite(content.replace(b'<path ', b'<evil:path xmlns:evil="urn:evil" ', 1))
        extra = b'<symbol id="produce-fruit-extra" viewBox="0 0 24 24"><path d="M1 1h1"/></symbol>'
        with self.assertRaises(ValueError):
            validate_produce_icon_sprite(content.replace(b"</svg>", extra + b"\n</svg>"))


if __name__ == "__main__":
    unittest.main()
