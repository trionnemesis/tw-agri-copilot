import json
import pathlib
import tempfile
import unittest

from tpw.trend_quant import CSS_MARKER, enhance_price_trends


class TrendQuantTest(unittest.TestCase):
    def series(self):
        return {
            "canonical_id": "banana",
            "as_of_date": "2026-08-30",
            "today": {
                "price_twd_per_kg": 28.0,
                "volume_kg": 1200.0,
                "market_count": 3,
                "quality_warnings": [],
            },
            "previous_trading_day": {
                "date": "2026-08-29",
                "price_twd_per_kg": 27.0,
                "change_pct": 3.703704,
                "status": "valid",
            },
            "windows": {
                "7d": {
                    "price_twd_per_kg": 27.5,
                    "avg_daily_volume_kg": 1000.0,
                    "coverage_days": 4,
                    "minimum_days": 3,
                    "status": "valid",
                    "today_change_pct": 1.818182,
                    "today_volume_change_pct": 20.0,
                },
                "30d": {
                    "price_twd_per_kg": 27.5,
                    "avg_daily_volume_kg": 1000.0,
                    "coverage_days": 4,
                    "minimum_days": 10,
                    "status": "insufficient",
                    "today_change_pct": 1.818182,
                    "today_volume_change_pct": 20.0,
                },
                "90d": {
                    "price_twd_per_kg": 27.5,
                    "avg_daily_volume_kg": 1000.0,
                    "coverage_days": 4,
                    "minimum_days": 30,
                    "status": "insufficient",
                    "today_change_pct": 1.818182,
                    "today_volume_change_pct": 20.0,
                },
            },
            "range_stats": {
                "7d": {
                    "observed_days": 4,
                    "minimum_days": 3,
                    "min_price_twd_per_kg": 26.0,
                    "min_date": "2026-08-27",
                    "max_price_twd_per_kg": 29.0,
                    "max_date": "2026-08-28",
                    "status": "valid",
                },
                "30d": {
                    "observed_days": 4,
                    "minimum_days": 10,
                    "min_price_twd_per_kg": 26.0,
                    "min_date": "2026-08-27",
                    "max_price_twd_per_kg": 29.0,
                    "max_date": "2026-08-28",
                    "status": "insufficient",
                },
                "90d": {
                    "observed_days": 4,
                    "minimum_days": 30,
                    "min_price_twd_per_kg": 26.0,
                    "min_date": "2026-08-27",
                    "max_price_twd_per_kg": 29.0,
                    "max_date": "2026-08-28",
                    "status": "insufficient",
                },
            },
            "volatility_7d_cv": 0.04,
            "volatility_7d_status": "valid",
            "daily": [
                {"date": "2026-08-27", "price_twd_per_kg": 26.0, "volume_kg": 900.0},
                {"date": "2026-08-28", "price_twd_per_kg": 29.0, "volume_kg": 1000.0},
                {"date": "2026-08-29", "price_twd_per_kg": 27.0, "volume_kg": 1100.0},
                {"date": "2026-08-30", "price_twd_per_kg": 28.0, "volume_kg": 1200.0},
            ],
        }

    def page(self):
        return (
            "<!doctype html><html><body><main>"
            "<section class='section'><div class='grid grid-4'></div></section>"
            "<section class='section'><h2>Buy Score 與產季</h2><p>score</p></section>"
            "<section class='section'><h2>近 120 日價格趨勢</h2>"
            "<div class='chart' role='img' aria-label='近期香港價格趨勢折線圖'>"
            "<svg viewBox='0 0 700 200'><polyline points='0,1 2,3' class='price-line'/></svg></div>"
            "<p class='disclaimer'>批發市場平均行情，非實際零售通路售價。</p>"
            "<div class='table-wrap'><table><tbody><tr><td>keep-me</td></tr></tbody></table></div>"
            "</section></main></body></html>"
        )

    def prepare(self, root):
        (root / "data/series").mkdir(parents=True)
        (root / "site/produce").mkdir(parents=True)
        (root / "site/assets/css").mkdir(parents=True)
        (root / "data/series/banana.json").write_text(
            json.dumps(self.series()), encoding="utf-8"
        )
        (root / "site/produce/banana.html").write_text(self.page(), encoding="utf-8")
        (root / "site/assets/css/app.css").write_text("body{}\n", encoding="utf-8")

    def test_enhancement_is_static_quantitative_and_preserves_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.prepare(root)
            self.assertEqual(enhance_price_trends(root), 1)
            result = (root / "site/produce/banana.html").read_text(encoding="utf-8")

            self.assertIn("價格量化摘要", result)
            self.assertIn("前一交易日", result)
            self.assertIn("7D 波動度 CV", result)
            self.assertIn("30D 有效日", result)
            self.assertIn("最多 120 日價格趨勢 · 實際 4 個有效交易日", result)
            self.assertIn("data-trend-chart='v1'", result)
            self.assertIn("NT$ 28.00/kg", result)
            self.assertIn("30D 高點 NT$ 29.00/kg", result)
            self.assertIn("30D 低點 NT$ 26.00/kg", result)
            self.assertIn("休市與缺資料不補 0", result)
            self.assertIn("資料不足", result)
            self.assertIn("keep-me", result)
            self.assertNotIn("近期香港價格趨勢折線圖", result)

    def test_css_and_html_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.prepare(root)
            enhance_price_trends(root)
            enhance_price_trends(root)
            page = (root / "site/produce/banana.html").read_text(encoding="utf-8")
            css = (root / "site/assets/css/app.css").read_text(encoding="utf-8")
            self.assertEqual(page.count("data-trend-quant='v1'"), 2)
            self.assertEqual(page.count("價格量化摘要"), 1)
            self.assertEqual(css.count(CSS_MARKER), 1)

    def test_invalid_daily_observation_is_not_counted_or_zero_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.prepare(root)
            payload = self.series()
            payload["daily"].insert(
                1,
                {"date": "2026-08-27", "price_twd_per_kg": None, "volume_kg": 0},
            )
            (root / "data/series/banana.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            enhance_price_trends(root)
            result = (root / "site/produce/banana.html").read_text(encoding="utf-8")
            self.assertIn("實際 4 個有效交易日", result)
            self.assertNotIn("最新 NT$ 0.00/kg", result)


if __name__ == "__main__":
    unittest.main()
