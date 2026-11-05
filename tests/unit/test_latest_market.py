import copy
import unittest

from tpw.latest_market import build_latest_market, validate_latest_market


ITEMS = [
    {"canonical_id": "banana", "display_name": "香蕉", "category": "fruit"},
    {"canonical_id": "mango", "display_name": "芒果", "category": "fruit"},
]


def row(day="2026-11-05", crop="banana", **extra):
    return {"transaction_date": day, "canonical_id": crop, "source_id": "moa_market_8066",
            "avg_price_twd_per_kg": 20, "volume_kg": 10, "market_code": "104", **extra}


class LatestMarketTest(unittest.TestCase):
    def build(self, rows, **kwargs):
        return build_latest_market(rows, ITEMS, "2026-11-05", "2026-10-28", **kwargs)

    def test_partial_latest_does_not_carry_forward_missing_crop(self):
        payload = self.build([row("2026-10-28", "mango"), row(), row(market_code="109", avg_price_twd_per_kg=40, volume_kg=30)])
        self.assertEqual(payload["as_of_date"], "2026-11-05")
        self.assertEqual(payload["complete_reference_date"], "2026-10-28")
        self.assertEqual(payload["valid_watchlist_count"], 1)
        self.assertEqual(payload["covered_watchlist_count"], 1)
        self.assertFalse(payload["affects_buy_score"])
        self.assertEqual(payload["items"][0]["price_twd_per_kg"], 35)
        missing = payload["items"][1]
        self.assertEqual(missing["observation_status"], "missing")
        self.assertTrue(all(missing[key] is None for key in ("price_twd_per_kg", "volume_kg", "market_count")))

    def test_future_fixture_unknown_and_non_authoritative_rows_are_excluded(self):
        payload = self.build([row("2026-10-28"), row("2026-11-06"), row(fetched_at="fixture"), row(source_status="fixture"), row(crop="unknown"), row(source_id="unknown"), row(source_role="contextual"), row(dataset_semantics="other")])
        self.assertEqual(payload["as_of_date"], "2026-10-28")
        self.assertEqual(payload["valid_watchlist_count"], 1)

    def test_fixture_opt_in_remains_explicit(self):
        payload = self.build([row(fetched_at="fixture")], include_fixtures=True)
        self.assertEqual(payload["source_status"], "fixture")
        self.assertEqual(payload["valid_watchlist_count"], 1)

    def test_invalid_only_observations_are_distinct_from_missing(self):
        payload = self.build([row(avg_price_twd_per_kg=0)])
        self.assertEqual(payload["as_of_date"], "2026-11-05")
        self.assertEqual(payload["covered_watchlist_count"], 1)
        self.assertEqual(payload["valid_watchlist_count"], 0)
        self.assertEqual(payload["items"][0]["observation_status"], "no_valid_trade")
        self.assertIsNone(payload["items"][0]["volume_kg"])

    def test_no_history_does_not_invent_a_date(self):
        payload = self.build([])
        self.assertIsNone(payload["as_of_date"])
        self.assertEqual(payload["covered_watchlist_count"], 0)
        self.assertTrue(all(item["observation_status"] == "missing" for item in payload["items"]))

    def test_tampering_fails_closed(self):
        payload = self.build([row()])
        variants = [
            {"covered_watchlist_count": 2}, {"valid_watchlist_count": 2},
            {"as_of_date": "2026-11-06"}, {"affects_buy_score": True},
            {"items": [payload["items"][0], payload["items"][0]]},
        ]
        for changes in variants:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_latest_market({**payload, **changes})
        for value in (0, 123, float("nan")):
            changed = copy.deepcopy(payload)
            changed["items"][1]["price_twd_per_kg"] = value
            with self.assertRaises(ValueError):
                validate_latest_market(changed)
        for value in (float("inf"), float("nan"), -1):
            changed = copy.deepcopy(payload)
            changed["items"][0]["price_twd_per_kg"] = value
            with self.assertRaises(ValueError):
                validate_latest_market(changed)
