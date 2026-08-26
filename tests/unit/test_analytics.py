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

    def test_previous_valid_day_skips_missing_and_division_by_zero(self):
        rows = self.rows(4)
        rows[-2]["weighted_avg_price_twd_per_kg"] = None
        rows[-2]["total_volume_kg"] = 0
        series = build_series(rows, rows[-1]["transaction_date"])[0]
        self.assertEqual(series["previous_trading_day"]["date"], rows[-3]["transaction_date"])
        self.assertEqual(series["windows"]["30d"]["status"], "insufficient")
        self.assertIsNone(change_pct(10, 0))
