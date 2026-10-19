import copy
import datetime as dt
import hashlib
import json
import pathlib
import random
import unittest

from tpw.analytics import aggregate
from tpw.season_map import load_official_market_registry
from tpw.taipei_analysis import (
    FIELDS,
    ITEM_FIELDS,
    MINIMUM_MARKET_COUNT,
    OBSERVATION_FIELDS,
    TaipeiAnalysisError,
    build_taipei_analysis,
    failed_taipei_analysis,
    feed_market_name_key,
    taipei_csv_documents,
    validate_taipei_analysis,
)


ROOT = pathlib.Path(__file__).parents[2]
AS_OF = "2026-08-25"
ITEMS = [
    {"canonical_id": "banana", "display_name": "香蕉", "category": "fruit"},
    {"canonical_id": "cabbage", "display_name": "甘藍", "category": "vegetable"},
]
CROPS = {"banana": ("A1", "香蕉", "fruit"), "cabbage": ("LA2", "甘藍-初秋", "vegetable")}
MARKET_NAMES = {"104": "台北二", "109": "台北一", "400": "台中市", "241": "三重區"}


def row(date, market, canonical_id, price, volume):
    crop_code, crop_name, category = CROPS[canonical_id]
    value = {
        "transaction_date": date,
        "market_code": market,
        "market_name": MARKET_NAMES[market],
        "crop_code": crop_code,
        "crop_name_raw": crop_name,
        "canonical_id": canonical_id,
        "display_name": crop_name,
        "category": category,
        "avg_price_twd_per_kg": price,
        "volume_kg": volume,
        "source_id": "moa_market_8066",
        "dataset_semantics": "wholesale_market_daily_transaction",
        "fetched_at": "fixture",
    }
    value["row_hash"] = "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return value


def history(days=35, markets=("104", "109")):
    end = dt.date.fromisoformat(AS_OF)
    rows = []
    for offset in range(days):
        date = (end - dt.timedelta(days=offset)).isoformat()
        for market in markets:
            for index, canonical_id in enumerate(sorted(CROPS)):
                rows.append(row(date, market, canonical_id, 20 + index * 10 + offset * 0.1 + (market == "109"), 100 + offset))
    return rows


def publication(requested=AS_OF, status="complete"):
    return {"requested_date": requested, "resolved_date": AS_OF, "status": status}


def calendar(closed=()):
    def evaluate(date):
        schedule = "scheduled_closed" if date in closed else "expected_open"
        reason = "一般週一休市" if schedule == "scheduled_closed" else "年度日程交易日"
        return {"markets": [{"market_code": code, "market_name": name, "schedule_status": schedule, "reason": reason} for code, name in (("109", "臺北一"), ("104", "臺北二"))]}
    return evaluate


class TaipeiAnalysisTest(unittest.TestCase):
    registry = load_official_market_registry(ROOT)

    def analyse(self, rows, requested=AS_OF, closed=(), status="complete"):
        return build_taipei_analysis(rows, AS_OF, publication(requested, status), ITEMS, self.registry, calendar(closed), "fixture")

    def item(self, document, canonical_id):
        return next(item for item in document["items"] if item["canonical_id"] == canonical_id)

    def test_volume_weighted_price_is_exact(self):
        document = self.analyse([row(AS_OF, "104", "banana", 100, 10), row(AS_OF, "109", "banana", 200, 30)])
        today = self.item(document, "banana")["today"]
        self.assertEqual(today["price_twd_per_kg"], 175)
        self.assertEqual(today["volume_kg"], 40)
        self.assertEqual(today["market_codes"], ["104", "109"])

    def test_non_taipei_rows_never_change_taipei_statistics(self):
        rows = history()
        baseline = self.analyse(rows)
        extreme = [row(value["transaction_date"], market, value["canonical_id"], 99999, 1_000_000) for value in rows for market in ("400", "241") if value["market_code"] == "104"]
        polluted = self.analyse(rows + extreme)
        self.assertEqual(polluted, baseline)
        self.assertEqual(taipei_csv_documents(polluted), taipei_csv_documents(baseline))
        # The same extreme rows do move the nationwide aggregate, so the equality above is the filter at work.
        national = {(value["transaction_date"], value["canonical_id"]): value["weighted_avg_price_twd_per_kg"] for value in aggregate(rows)}
        national_polluted = {(value["transaction_date"], value["canonical_id"]): value["weighted_avg_price_twd_per_kg"] for value in aggregate(rows + extreme)}
        self.assertNotEqual(national, national_polluted)

    def test_history_uses_the_same_filter_as_the_as_of_day(self):
        rows = [value for value in history(35) if value["transaction_date"] == AS_OF]
        rows += [value for value in history(35, markets=("400",)) if value["transaction_date"] != AS_OF]
        windows = self.item(self.analyse(rows), "banana")["windows"]
        self.assertEqual(windows["7d"]["coverage_days"], 1)
        self.assertEqual(windows["7d"]["status"], "insufficient")
        self.assertEqual(windows["30d"]["coverage_days"], 1)
        self.assertEqual(self.item(self.analyse(rows), "banana")["recommendation_gate"], {"status": "insufficient", "reason_codes": ["COVERAGE_INSUFFICIENT"]})

    def test_no_taipei_rows_does_not_fall_back_to_nationwide_prices(self):
        rows = [value for value in history() if value["transaction_date"] != AS_OF]
        rows += [row(AS_OF, "400", "banana", 30, 500), row(AS_OF, "400", "cabbage", 25, 500)]
        document = self.analyse(rows)
        self.assertEqual(document["scope_status"], "no_taipei_observation")
        self.assertEqual(document["observed_market_count"], 0)
        self.assertIs(document["national_fallback"], False)
        self.assertEqual(document["observations"], [])
        for item in document["items"]:
            self.assertEqual(item["status"], "no_taipei_observation")
            self.assertIsNone(item["today"])
            self.assertIsNone(item["windows"])
            self.assertEqual(item["recommendation_gate"], {"status": "insufficient", "reason_codes": ["NO_TAIPEI_OBSERVATION"]})
        self.assertEqual({day["day_status"] for day in document["market_days"] if day["date"] == AS_OF}, {"missing"})
        self.assertNotIn("30.0", taipei_csv_documents(document)["items.csv"])

    def test_single_taipei_market_keeps_statistics_but_stays_insufficient(self):
        rows = [value for value in history() if not (value["transaction_date"] == AS_OF and value["market_code"] == "109")]
        document = self.analyse(rows)
        banana = self.item(document, "banana")
        self.assertEqual(document["scope_status"], "partial_markets_observed")
        self.assertEqual(banana["status"], "observed")
        self.assertEqual(banana["today"]["market_count"], 1)
        self.assertIsNotNone(banana["today"]["price_twd_per_kg"])
        self.assertEqual(banana["recommendation_gate"], {"status": "insufficient", "reason_codes": ["MARKET_COUNT_INSUFFICIENT"]})
        self.assertEqual({market["market_code"]: market["as_of_day_status"] for market in document["markets"]}, {"104": "traded", "109": "missing"})

    def test_two_markets_with_coverage_are_not_evaluated_rather_than_recommended(self):
        gate = self.item(self.analyse(history()), "banana")["recommendation_gate"]
        self.assertEqual(gate, {"status": "not_evaluated", "reason_codes": ["TAIPEI_BUY_SCORE_NOT_DEFINED"]})

    def test_closure_missing_day_and_zero_price_are_distinct(self):
        closed = "2026-08-24"
        missing = "2026-08-23"
        rows = [value for value in history() if value["transaction_date"] not in (closed, missing)]
        rows = [value for value in rows if not (value["transaction_date"] == AS_OF and value["canonical_id"] == "cabbage")]
        rows += [row(AS_OF, "104", "cabbage", 0, 120), row(AS_OF, "109", "cabbage", 25, 0)]
        document = self.analyse(rows, requested="2026-08-26", closed=(closed,), status="pending")
        days = {(day["date"], day["market_code"]): day for day in document["market_days"]}
        self.assertEqual(days[(closed, "104")]["day_status"], "scheduled_closed")
        self.assertEqual(days[(missing, "104")]["day_status"], "missing")
        self.assertEqual(days[("2026-08-26", "109")]["day_status"], "missing")
        self.assertEqual(days[("2026-08-26", "109")]["schedule_status"], "expected_open")
        cabbage = self.item(document, "cabbage")
        self.assertEqual(cabbage["status"], "no_valid_trade")
        self.assertIsNone(cabbage["today"])
        self.assertEqual(cabbage["recommendation_gate"]["reason_codes"], ["NO_VALID_TRADE"])
        statuses = {observation["value_status"] for observation in document["observations"] if observation["canonical_id"] == "cabbage"}
        self.assertEqual(statuses, {"excluded_zero_price_or_volume"})
        self.assertEqual(document["requested_date"], "2026-08-26")
        self.assertEqual(document["as_of_date"], AS_OF)

    def test_trade_on_an_officially_closed_day_is_a_discrepancy(self):
        document = self.analyse(history(), closed=(AS_OF,))
        self.assertEqual({market["as_of_day_status"] for market in document["markets"]}, {"calendar_feed_discrepancy"})

    def test_market_identity_drift_fails_closed(self):
        drifted = row(AS_OF, "104", "banana", 30, 10)
        drifted["market_name"] = "台中市"
        with self.assertRaises(TaipeiAnalysisError):
            self.analyse(history() + [drifted])
        self.assertEqual(feed_market_name_key("台北一"), feed_market_name_key("臺北一"))

    def test_output_is_deterministic_and_order_independent(self):
        rows = history()
        shuffled = list(rows)
        random.Random(51).shuffle(shuffled)
        first = self.analyse(rows)
        second = self.analyse(shuffled)
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(encode(first), encode(second))
        self.assertEqual(taipei_csv_documents(first), taipei_csv_documents(second))

    def test_publication_must_resolve_to_the_as_of_date(self):
        with self.assertRaises(TaipeiAnalysisError):
            build_taipei_analysis(history(), AS_OF, {"requested_date": AS_OF, "resolved_date": "2026-08-24", "status": "complete"}, ITEMS, self.registry, calendar(), "fixture")

    def test_validator_rejects_boundary_violations(self):
        document = self.analyse([value for value in history() if not (value["transaction_date"] == AS_OF and value["market_code"] == "109")])
        tampering = (
            lambda value: value.update(national_fallback=True),
            lambda value: value["items"][0]["recommendation_gate"].update(status="eligible"),
            lambda value: value["items"][0]["recommendation_gate"].update(status="not_evaluated"),
            lambda value: value["items"][0].update(origin_status="verified"),
            lambda value: value["observations"][0].update(geography_role="origin_region"),
            lambda value: value["markets"][1].update(as_of_valid_row_count=3),
            lambda value: value.update(extra=True),
        )
        for tamper in tampering:
            changed = copy.deepcopy(document)
            tamper(changed)
            with self.assertRaises(TaipeiAnalysisError):
                validate_taipei_analysis(changed)
        unobserved = self.analyse([value for value in history() if value["transaction_date"] != AS_OF])
        unobserved["items"][0]["today"] = {"price_twd_per_kg": 0}
        with self.assertRaises(TaipeiAnalysisError):
            validate_taipei_analysis(unobserved)

    def test_failed_analysis_publishes_the_reason_and_no_statistics(self):
        document = failed_taipei_analysis(AS_OF, publication("2026-08-26", "pending"), "success", "TaipeiAnalysisError: drift")
        self.assertEqual((document["analysis_status"], document["scope_status"], document["failure_reason"]), ("failed", "analysis_failed", "TaipeiAnalysisError: drift"))
        self.assertIs(document["national_fallback"], False)
        self.assertEqual([document[key] for key in ("markets", "market_days", "items", "observations")], [[], [], [], []])
        self.assertEqual(taipei_csv_documents(document)["items.csv"].count("\n"), 1)
        tampering = (
            lambda value: value.update(failure_reason=""),
            lambda value: value.update(items=self.analyse(history())["items"]),
            lambda value: value.update(snapshot_hash="sha256:" + "0" * 64),
            lambda value: value.update(analysis_status="published"),
        )
        for tamper in tampering:
            changed = copy.deepcopy(document)
            tamper(changed)
            with self.assertRaises(TaipeiAnalysisError):
                validate_taipei_analysis(changed)
        published = self.analyse(history())
        published["failure_reason"] = "stale reason"
        with self.assertRaises(TaipeiAnalysisError):
            validate_taipei_analysis(published)

    def test_schema_documents_the_validated_contract(self):
        schema = json.loads((ROOT / "schema/taipei-analysis.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), FIELDS)
        self.assertEqual(set(schema["properties"]["items"]["items"]["required"]), ITEM_FIELDS)
        self.assertEqual(schema["properties"]["observations"]["items"]["required"], list(OBSERVATION_FIELDS))

    def test_market_count_gate_matches_the_scoring_config(self):
        scoring = json.loads((ROOT / "config/scoring.yml").read_text(encoding="utf-8"))
        self.assertEqual(MINIMUM_MARKET_COUNT, scoring["eligibility"]["minimum_market_count"])


if __name__ == "__main__":
    unittest.main()
