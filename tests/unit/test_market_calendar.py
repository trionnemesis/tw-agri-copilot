import copy
import json
import pathlib
import unittest

from tpw.market_calendar import (
    CalendarContractError,
    evaluate_market_calendar,
    load_calendar_config,
    load_calendar_payload,
    validate_calendar_payload,
)


ROOT = pathlib.Path(__file__).parents[2]


class MarketCalendarTest(unittest.TestCase):
    def test_official_fixture_covers_the_complete_2026_schedule(self):
        config = load_calendar_config(ROOT)
        payload = load_calendar_payload(ROOT, 2026)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["closed_day_count"], 80)
        self.assertEqual(payload["trading_day_count"], 285)
        self.assertEqual(len(payload["entries"]), 365)
        self.assertEqual(
            payload["content_hash"],
            config["sources"][0]["documents"][0]["expected_content_hash"],
        )

    def test_special_closures_regular_monday_and_exceptional_monday(self):
        cases = {
            "2026-08-28": ("scheduled_closed", "中元節後循例休市"),
            "2026-08-29": ("scheduled_closed", "中元節後循例休市"),
            "2026-08-31": ("scheduled_closed", "一般週一休市"),
            "2026-09-28": ("exceptional_open", "取消原週一休市"),
            "2026-08-27": ("expected_open", "年度日程交易日"),
        }
        for day, (status, reason) in cases.items():
            with self.subTest(day=day):
                evaluated = evaluate_market_calendar(ROOT, day)
                self.assertEqual(evaluated["schedule_status"], status)
                self.assertIn(reason, evaluated["reason"])
                self.assertEqual(
                    {market["market_code"] for market in evaluated["markets"]},
                    {"104", "109"},
                )

    def test_unknown_year_does_not_claim_an_official_schedule(self):
        evaluated = evaluate_market_calendar(ROOT, "2027-01-01")
        self.assertEqual(evaluated["schedule_status"], "unknown")
        self.assertIsNone(evaluated["content_hash"])
        self.assertIsNone(evaluated["retrieved_at"])
        self.assertTrue(
            all(market["schedule_status"] == "unknown" for market in evaluated["markets"])
        )

    def test_schema_drift_fails_closed(self):
        payload = load_calendar_payload(ROOT, 2026)
        duplicate = copy.deepcopy(payload)
        duplicate["entries"][1]["calendar_date"] = duplicate["entries"][0]["calendar_date"]
        with self.assertRaisesRegex(CalendarContractError, "every date exactly once"):
            validate_calendar_payload(duplicate)
        malformed = json.loads(json.dumps(payload))
        malformed["entries"][0]["schedule_status"] = "closed-ish"
        with self.assertRaisesRegex(CalendarContractError, "schedule status"):
            validate_calendar_payload(malformed)
