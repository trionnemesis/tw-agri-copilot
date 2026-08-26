import unittest

from tpw.seasonality import build_seasonality


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
