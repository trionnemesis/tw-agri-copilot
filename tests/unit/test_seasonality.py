import unittest

from tpw.seasonality import build_catalog, build_seasonality, map_catalog


class SeasonalityTest(unittest.TestCase):
    def test_manual_fallback_preserves_unknown_and_origin_counts(self):
        items = [
            {"canonical_id": "banana", "display_name": "香蕉", "category": "fruit"},
            {"canonical_id": "cucumber", "display_name": "胡瓜", "category": "vegetable"},
        ]
        manual = {
            "source_url": "https://example.test/season",
            "verified_at": "fixture",
            "items": [
                {"canonical_id": "banana", "months": [8], "counties": ["屏東縣", "屏東縣"]}
            ],
        }
        rows = build_seasonality(items, manual, "2026-08")
        by_id = {row["canonical_id"]: row for row in rows}
        self.assertEqual(by_id["banana"]["seasonality_status"], "in_season")
        self.assertEqual(by_id["banana"]["county_count"], 1)
        self.assertEqual(by_id["cucumber"]["seasonality_status"], "unknown")
        self.assertTrue(all(row["source_status"] == "fallback" for row in rows))

    def test_live_catalog_aggregates_origins_and_uses_only_explicit_names(self):
        raw = [
            {"category": "fruit", "display_name": "番荔枝", "variety": "大目種", "county": "臺東縣", "district": "東河鄉", "months": [8]},
            {"category": "fruit", "display_name": "番荔枝", "variety": "軟枝種", "county": "臺東縣", "district": "太麻里鄉", "months": [8]},
            {"category": "vegetable", "display_name": "胡瓜", "variety": "黑刺", "county": "屏東縣", "district": "里港鄉", "months": [8]},
        ]
        items = [
            {"canonical_id": "custard-apple", "display_name": "釋迦", "category": "fruit", "seasonality_names": ["番荔枝"]},
            {"canonical_id": "cucumber", "display_name": "胡瓜", "category": "vegetable", "seasonality_names": ["胡瓜"]},
            {"canonical_id": "banana", "display_name": "香蕉", "category": "fruit", "seasonality_names": ["香蕉"]},
        ]
        catalog = build_catalog(raw, "2026-08", "2026-08-27T00:00:00Z")
        watch, mapped = map_catalog(items, catalog, "2026-08")
        by_id = {row["canonical_id"]: row for row in watch}
        self.assertEqual(by_id["custard-apple"]["counties"], ["臺東縣"])
        self.assertEqual(by_id["custard-apple"]["seasonality_status"], "in_season")
        self.assertEqual(by_id["banana"]["seasonality_status"], "unknown")
        custard = next(row for row in mapped if row["canonical_id"] == "custard-apple")
        self.assertEqual(custard["display_name"], "釋迦")
        self.assertEqual(custard["source_display_names"], ["番荔枝"])
        self.assertEqual(custard["variety_count"], 2)

    def test_similar_but_unconfigured_name_is_not_fuzzy_matched(self):
        raw = [{"category": "fruit", "display_name": "香蕉芭蕉", "variety": "", "county": "高雄市", "district": "旗山區", "months": [8]}]
        items = [{"canonical_id": "banana", "display_name": "香蕉", "category": "fruit", "seasonality_names": ["香蕉"]}]
        watch, catalog = map_catalog(items, build_catalog(raw, "2026-08", "fixture"), "2026-08")
        self.assertEqual(watch[0]["seasonality_status"], "unknown")
        self.assertIsNone(catalog[0]["canonical_id"])
