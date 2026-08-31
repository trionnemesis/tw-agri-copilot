import datetime as dt
import unittest

from tpw.analytics import build_series, change_pct


class AnalyticsTest(unittest.TestCase):
    def rows(self, count=35):
        start = dt.date(2026, 7, 22)
        rows = []
        for index in range(count):
            rows.append(
                {
                    "transaction_date": (start + dt.timedelta(days=index)).isoformat(),
                    "canonical_id": "banana",
                    "weighted_avg_price_twd_per_kg": 30 - index * 0.2,
                    "total_volume_kg": 100 + index,
                    "market_count": 2,
                    "quality_warnings": [],
                }
            )
        return rows

    def test_previous_day_windows_coverage_and_volatility(self):
        series = build_series(self.rows(), "2026-08-25")[0]
        self.assertEqual(series["previous_trading_day"]["date"], "2026-08-24")
        self.assertLess(series["previous_trading_day"]["change_pct"], 0)
        self.assertEqual(series["windows"]["7d"]["coverage_days"], 7)
        self.assertEqual(series["windows"]["30d"]["status"], "valid")
        self.assertEqual(series["windows"]["90d"]["coverage_days"], 35)
        self.assertEqual(series["volatility_7d_status"], "valid")

        seven_range = series["range_stats"]["7d"]
        self.assertEqual(seven_range["status"], "valid")
        self.assertEqual(seven_range["observed_days"], 7)
        self.assertEqual(seven_range["max_date"], "2026-08-19")
        self.assertEqual(seven_range["min_date"], "2026-08-25")
        self.assertGreater(
            seven_range["max_price_twd_per_kg"],
            seven_range["min_price_twd_per_kg"],
        )

    def test_previous_valid_day_skips_missing_and_division_by_zero(self):
        rows = self.rows(4)
        rows[-2]["weighted_avg_price_twd_per_kg"] = None
        rows[-2]["total_volume_kg"] = 0
        series = build_series(rows, rows[-1]["transaction_date"])[0]
        self.assertEqual(series["previous_trading_day"]["date"], rows[-3]["transaction_date"])
        self.assertEqual(series["windows"]["30d"]["status"], "insufficient")
        self.assertEqual(series["range_stats"]["30d"]["status"], "insufficient")
        self.assertEqual(series["range_stats"]["30d"]["observed_days"], 3)
        self.assertIsNone(change_pct(10, 0))

    def test_range_stats_flat_price_are_deterministic(self):
        rows = self.rows(7)
        for row in rows:
            row["weighted_avg_price_twd_per_kg"] = 25.0
        series = build_series(rows, rows[-1]["transaction_date"])[0]
        stats = series["range_stats"]["7d"]
        self.assertEqual(stats["min_price_twd_per_kg"], 25.0)
        self.assertEqual(stats["max_price_twd_per_kg"], 25.0)
        self.assertEqual(stats["min_date"], rows[0]["transaction_date"])
        self.assertEqual(stats["max_date"], rows[0]["transaction_date"])

    def test_range_stats_ignore_invalid_price_or_volume(self):
        rows = self.rows(7)
        rows[1]["weighted_avg_price_twd_per_kg"] = None
        rows[1]["total_volume_kg"] = 0
        rows[2]["total_volume_kg"] = 0
        series = build_series(rows, rows[-1]["transaction_date"])[0]
        stats = series["range_stats"]["7d"]
        self.assertEqual(stats["observed_days"], 5)
        self.assertEqual(stats["status"], "valid")
        self.assertNotEqual(stats["min_date"], rows[2]["transaction_date"])
