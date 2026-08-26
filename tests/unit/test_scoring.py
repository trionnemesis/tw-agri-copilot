import unittest

from tpw.scoring import score_item


def series(coverage=30, market_count=2, price=80, average=100, volume=130):
    return {
        "canonical_id": "banana",
        "as_of_date": "2026-08-25",
        "today": {"price_twd_per_kg": price, "volume_kg": volume, "market_count": market_count, "quality_warnings": []},
        "previous_trading_day": {"change_pct": -2},
        "windows": {
            "7d": {"price_twd_per_kg": average, "avg_daily_volume_kg": 100, "coverage_days": min(7, coverage), "status": "valid" if coverage >= 3 else "insufficient"},
            "30d": {"price_twd_per_kg": average, "avg_daily_volume_kg": 100, "coverage_days": coverage, "status": "valid" if coverage >= 10 else "insufficient"},
            "90d": {"price_twd_per_kg": average, "avg_daily_volume_kg": 100, "coverage_days": coverage, "status": "valid" if coverage >= 30 else "insufficient"},
        },
        "volatility_7d_cv": 0.05,
    }


class ScoringTest(unittest.TestCase):
    def test_priority_boundary_is_deterministic(self):
        result = score_item(series(), {"seasonality_status": "in_season"})
        self.assertTrue(result["eligible"])
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["verdict"], "priority")
        self.assertIn("PRICE_AT_OR_BELOW_30D", result["reason_codes"])

    def test_coverage_and_seasonality_are_hard_gates(self):
        insufficient = score_item(series(coverage=5), {"seasonality_status": "in_season"})
        self.assertFalse(insufficient["eligible"])
        self.assertEqual(insufficient["verdict"], "insufficient")
        out = score_item(series(), {"seasonality_status": "out_of_season"})
        self.assertEqual(out["verdict"], "not_ranked")

    def test_market_count_is_a_hard_gate(self):
        result = score_item(series(market_count=1), {"seasonality_status": "in_season"})
        self.assertEqual(result["verdict"], "insufficient")
        self.assertIn("MARKET_COUNT_INSUFFICIENT", result["reason_codes"])
