import json
import pathlib
import tempfile
import unittest

from tpw.publication import (
    apply_market_calendar,
    classify_market_status,
    load_resolved_market_status,
    source_unavailable_status,
    validate_market_status,
)
from tpw.market_calendar import evaluate_market_calendar


ROOT = pathlib.Path(__file__).parents[2]


class PublicationStatusTest(unittest.TestCase):
    def test_rest_markers_are_market_closed(self):
        observed = [
            {
                "transaction_date": "2026-08-27",
                "crop_code": "rest",
                "crop_name_raw": "休市",
                "canonical_id": None,
            }
        ]
        status = classify_market_status(
            observed, [], "2026-08-27", {"banana", "cabbage"}, "success"
        )
        self.assertEqual(status["status"], "market_closed")
        self.assertEqual(status["covered_watchlist_count"], 0)
        self.assertEqual(status["observed_record_count"], 1)

    def test_official_calendar_separates_expected_open_from_feed_closed_marker(self):
        observed = [
            {
                "transaction_date": "2026-08-27",
                "crop_code": "rest",
                "crop_name_raw": "休市",
                "canonical_id": None,
            }
        ]
        status = classify_market_status(
            observed,
            [],
            "2026-08-27",
            {"banana", "cabbage"},
            "success",
            evaluate_market_calendar(ROOT, "2026-08-27"),
        )
        self.assertEqual(status["status"], "pending")
        self.assertEqual(status["feed_status"], "empty")
        self.assertEqual(status["calendar"]["schedule_status"], "expected_open")

    def test_official_closure_and_feed_conflict_are_distinct(self):
        base = {
            "schema_version": "1.0",
            "requested_date": "2026-08-28",
            "status": "market_closed",
            "source_status": "success",
            "feed_status": "empty",
            "expected_watchlist_count": 20,
            "covered_watchlist_count": 0,
            "observed_record_count": 25,
        }
        calendar = evaluate_market_calendar(ROOT, "2026-08-28")
        closed = apply_market_calendar(base, calendar)
        self.assertEqual(closed["status"], "market_closed")
        self.assertEqual(closed["calendar"]["reason"], "中元節後循例休市")
        conflict = apply_market_calendar(
            {**base, "status": "incomplete", "feed_status": "available"},
            calendar,
            "available",
        )
        self.assertEqual(conflict["status"], "calendar_feed_discrepancy")

    def test_other_markets_can_trade_without_creating_a_taipei_discrepancy(self):
        row = {
            "transaction_date": "2026-08-28",
            "market_code": "423",
            "crop_code": "A1",
            "crop_name_raw": "香蕉",
            "canonical_id": "banana",
        }
        status = classify_market_status(
            [row],
            [row],
            "2026-08-28",
            {"banana"},
            "success",
            evaluate_market_calendar(ROOT, "2026-08-28"),
        )
        self.assertEqual(status["status"], "complete")
        self.assertEqual(status["feed_status"], "available")
        self.assertEqual(status["calendar_feed_status"], "empty")

    def test_partial_rows_are_not_mislabeled_as_closed(self):
        observed = [
            {
                "transaction_date": "2026-08-27",
                "crop_code": "rest",
                "crop_name_raw": "休市",
                "canonical_id": None,
            },
            {
                "transaction_date": "2026-08-27",
                "crop_code": "A1",
                "crop_name_raw": "香蕉",
                "canonical_id": "banana",
            }
        ]
        status = classify_market_status(
            observed, observed, "2026-08-27", {"banana", "cabbage"}, "success"
        )
        self.assertEqual(status["status"], "incomplete")
        self.assertEqual(status["covered_watchlist_count"], 1)

    def test_closed_day_resolves_to_last_complete_date(self):
        status = {
            "schema_version": "1.0",
            "requested_date": "2026-08-27",
            "status": "market_closed",
            "source_status": "success",
            "expected_watchlist_count": 20,
            "covered_watchlist_count": 0,
            "observed_record_count": 4,
        }
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            path = root / "market-status/current.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(status), encoding="utf-8")
            resolved = load_resolved_market_status(root, "2026-08-26", "success", 20)
        self.assertEqual(resolved["resolved_date"], "2026-08-26")
        self.assertEqual(resolved["requested_date"], "2026-08-27")

    def test_invalid_counts_and_unavailable_status_fail_closed(self):
        unavailable = source_unavailable_status("2026-08-27", 20)
        self.assertEqual(unavailable["status"], "source_unavailable")
        unavailable["covered_watchlist_count"] = 21
        with self.assertRaises(ValueError):
            validate_market_status(unavailable)
