import copy
import json
import unittest

from tpw.advice import DISCLAIMER, fallback_advice, generate_advice, provider_input


SCORES = [
    {
        "canonical_id": "banana",
        "score": 88,
        "verdict": "priority",
        "verdict_label": "優先採買",
        "seasonality_status": "in_season",
        "today_price": 20,
        "previous_trading_day_change_pct": -2,
        "vs_7d_pct": -5,
        "vs_30d_pct": -10,
        "volume_vs_7d_pct": 30,
        "market_count": 2,
        "coverage": {"days_7d": 7, "days_30d": 30, "days_90d": 35},
        "reason_codes": ["IN_SEASON", "PRICE_AT_OR_BELOW_7D"],
    }
]


class AdviceTest(unittest.TestCase):
    def test_fallback_is_deterministic_and_input_is_minimized(self):
        first = fallback_advice(SCORES, "2026-08-25")
        self.assertEqual(first, fallback_advice(SCORES, "2026-08-25"))
        self.assertEqual(first["generation_mode"], "deterministic_fallback")
        self.assertEqual(str(first["generation_mode"]), "規則分析模式")
        serialized = json.loads(json.dumps(first, ensure_ascii=False))
        self.assertEqual(serialized["generation_mode"], "deterministic_fallback")
        self.assertNotIn("components", provider_input(SCORES, "2026-08-25")["items"][0])

    def test_invalid_or_prohibited_provider_output_falls_back(self):
        def provider(_evidence):
            return {
                "schema_version": "1.0", "language": "zh-Hant", "as_of_date": "2026-08-25",
                "headline": "一定便宜", "summary": "x", "priority_items": [], "watch_items": [],
                "disclaimer": DISCLAIMER, "model": "fixture", "prompt_version": "tpw-advice-v1",
                "input_hash": "ignored", "generated_at": "2026-08-25T00:00:00Z"
            }
        before = copy.deepcopy(SCORES)
        result = generate_advice(SCORES, "2026-08-25", enabled=True, provider=provider)
        self.assertEqual(result["generation_mode"], "deterministic_fallback")
        self.assertEqual(SCORES, before)
