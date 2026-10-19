import copy
import csv
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from tpw.taipei_monthly import (
    FIELDS,
    SOURCES,
    VERIFIED_AUTHORITATIVE_CONTRACT_STATUS,
    TaipeiMonthlyError,
    build_monthly_analysis,
    failed_monthly_analysis,
    fixture_snapshots,
    ingest_snapshot,
    load_retail_mapping,
    monthly_csv_documents,
    parse_snapshot,
    snapshot_path,
    validate_snapshot_document,
    validate_monthly_analysis,
)


ROOT = pathlib.Path(__file__).parents[2]
PUBLICATION = {"requested_date": "2026-08-25"}
RETAIL_HEADER = "序號,縣市名,縣市別代碼,項目,平均(元/台斤)\n"
SUPPLY_HEADER = "類別,交易量(公斤),平均價格(元/公斤)\n"


def retail_csv(rows):
    return (RETAIL_HEADER + "".join("%d,臺北市,63000,%s,%s\n" % (index, item, value) for index, (item, value) in enumerate(rows, start=1))).encode("utf-8")


def supply_csv(rows):
    return (SUPPLY_HEADER + "".join("%s,%s,%s\n" % row for row in rows)).encode("utf-8")


def roc_name(period):
    return "%d年%d月份行情" % (int(period[:4]) - 1911, int(period[5:]))


class TaipeiMonthlyTest(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.data = pathlib.Path(workspace.name) / "data"

    def ingest(self, source, raw, period, retrieved_at=None, name=None, source_status="fixture"):
        return ingest_snapshot(
            self.data, source, raw, period=period, resource_id="rid-" + period, resource_name=name or roc_name(period),
            resource_url="https://data.taipei/fixture", retrieved_at=retrieved_at or period + "-10T00:00:00Z",
            license="test", source_status=source_status,
        )

    def analyse(self, mapping=None, publication=PUBLICATION):
        return build_monthly_analysis(self.data, "2026-08-25", publication, mapping or {})

    def item(self, document, name):
        return next(item for item in document["retail_items"] if item["item_raw"] == name)

    def test_jin_prices_convert_by_dividing_by_point_six(self):
        self.ingest("retail", retail_csv([("香蕉", "60"), ("芒果", "45"), ("高麗菜", "33")]), "2025-12")
        document = self.analyse()
        self.assertEqual([self.item(document, name)["latest_price_twd_per_kg"] for name in ("香蕉", "芒果", "高麗菜")], [100.0, 75.0, 55.0])
        self.assertEqual(self.item(document, "香蕉")["latest_price_raw"], 60.0)
        self.assertEqual(self.item(document, "香蕉")["price_unit_raw"], "元/台斤")

    def test_non_mass_items_never_get_a_per_kg_or_per_piece_price(self):
        self.ingest("retail", retail_csv([("雞蛋", "42")]), "2025-12")
        mapping = {"雞蛋": {"item_raw": "雞蛋", "commodity_family": "livestock", "canonical_id": None, "variant": None, "cut": None, "grade": None, "mass_basis": False, "evidence": "test"}}
        document = self.analyse(mapping)
        egg = self.item(document, "雞蛋")
        self.assertEqual((egg["latest_price_raw"], egg["latest_price_twd_per_kg"], egg["months"][0]["price_twd_per_kg"]), (42.0, None, None))
        self.assertEqual((egg["commodity_family"], egg["mapping_status"]), ("livestock", "reviewed"))
        egg["months"][0]["price_twd_per_kg"] = 70.0
        with self.assertRaises(TaipeiMonthlyError):
            validate_monthly_analysis(document)

    def test_specs_and_cuts_stay_separate_series(self):
        for offset, period in enumerate(("2025-10", "2025-11", "2025-12")):
            self.ingest("retail", retail_csv([("豬肉(里肌)", 120 + offset), ("豬肉(五花)", 150 + offset), ("白蝦", 300), ("草蝦", 420)]), period)
        document = self.analyse()
        self.assertEqual(sorted(item["item_raw"] for item in document["retail_items"]), ["白蝦", "草蝦", "豬肉(五花)", "豬肉(里肌)"])
        self.assertEqual(self.item(document, "豬肉(里肌)")["median_price_raw"], 121.0)
        self.assertEqual(self.item(document, "豬肉(五花)")["median_price_raw"], 151.0)
        self.assertTrue(all(item["commodity_family"] == "unknown" and item["comparison_key"] == "exact_raw_item" for item in document["retail_items"]))

    def test_schema_drift_and_unknown_tokens_fail_closed(self):
        drifted = (
            ("retail", "日期,種類,市場,品名,平均_元/公斤\n2020-01-01,水果,臺北,香蕉,30\n".encode("utf-8")),
            ("retail", (RETAIL_HEADER.strip() + ",備註\n1,臺北市,63000,香蕉,30,x\n").encode("utf-8")),
            ("retail", RETAIL_HEADER.encode("utf-8") + "1,新北市,65000,香蕉,30\n".encode("utf-8")),
            ("retail", retail_csv([("香蕉", "N/A")])),
            ("retail", retail_csv([("香蕉", "30"), ("香蕉", "31")])),
            ("retail", retail_csv([("香蕉", "-30")])),
            ("retail", RETAIL_HEADER.encode("big5")),
            ("supply", supply_csv([("牛", "100", "200")])),
            ("supply", "類別,交易量(公噸),平均價格(元/公斤)\n雞,1,2\n".encode("utf-8")),
        )
        for source, raw in drifted:
            with self.assertRaises(TaipeiMonthlyError):
                self.ingest(source, raw, "2025-12")
        self.assertFalse(self.data.exists())
        # Full-width parentheses and a BOM are encoding variants of the same header, not drift.
        contract, rows = parse_snapshot("retail", "﻿序號,項目,平均（元/台斤）\n1,香蕉,30\n".encode("utf-8"))
        self.assertEqual((contract, rows[0]["price_raw"]), ("retail-3col", 30.0))

    def test_blank_zero_and_missing_month_stay_distinct(self):
        self.ingest("retail", retail_csv([("香蕉", "30"), ("芒果", "80")]), "2025-10")
        self.ingest("retail", retail_csv([("香蕉", "-"), ("芒果", "0")]), "2025-11")
        self.ingest("retail", retail_csv([("芒果", "82")]), "2025-12")
        document = self.analyse()
        banana, mango = self.item(document, "香蕉"), self.item(document, "芒果")
        self.assertEqual([month["price_raw_status"] for month in banana["months"]], ["valid", "missing"])
        self.assertEqual([month["price_raw_status"] for month in mango["months"]], ["valid", "zero_reported", "valid"])
        self.assertEqual((banana["valid_month_count"], banana["in_latest_period"]), (1, False))
        self.assertEqual((mango["valid_month_count"], mango["mom_pct"]), (2, None))
        rows = list(csv.DictReader(io.StringIO(monthly_csv_documents(document)["monthly-retail.csv"])))
        statuses = {(row["item_raw"], row["observation_period"]): (row["value_status"], row["price_raw"], row["price_twd_per_kg"]) for row in rows}
        self.assertEqual(statuses[("香蕉", "2025-11")], ("missing", "", ""))
        self.assertEqual(statuses[("芒果", "2025-11")], ("zero_reported", "0.0", "0.0"))
        self.assertNotIn(("香蕉", "2025-12"), statuses)

    def test_ingest_is_idempotent_and_revisions_keep_lineage(self):
        first = retail_csv([("香蕉", "30")])
        self.assertEqual(self.ingest("retail", first, "2025-12")["status"], "added")
        path = snapshot_path(self.data, "retail", "2025-12")
        before = path.read_bytes()
        self.assertEqual(self.ingest("retail", first, "2025-12", retrieved_at="2026-02-01T00:00:00Z")["status"], "unchanged")
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(self.ingest("retail", retail_csv([("香蕉", "31")]), "2025-12", retrieved_at="2026-02-01T00:00:00Z")["status"], "revised")
        document = self.analyse()
        period = document["sources"][0]["periods"][0]
        self.assertEqual((period["revision"], period["revision_count"]), (2, 2))
        self.assertEqual(self.item(document, "香蕉")["latest_price_raw"], 31.0)
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([revision["revision"] for revision in stored["revisions"]], [1, 2])
        self.assertNotEqual(stored["revisions"][0]["raw_hash"], stored["revisions"][1]["raw_hash"])

    def test_provisional_contracts_reject_live_before_persistence(self):
        cases = (
            ("retail", retail_csv([("香蕉", "30")])),
            ("supply", supply_csv([("雞", "1000", "60")])),
        )
        for source, raw in cases:
            with self.subTest(source=source):
                with self.assertRaisesRegex(TaipeiMonthlyError, "registry contract is not verified authoritative"):
                    self.ingest(source, raw, "2025-12", source_status="live")
                self.assertFalse(snapshot_path(self.data, source, "2025-12").exists())

    def test_rejected_live_revision_does_not_overwrite_existing_snapshot(self):
        cases = (
            ("retail", retail_csv([("香蕉", "30")]), retail_csv([("香蕉", "31")])),
            ("supply", supply_csv([("雞", "1000", "60")]), supply_csv([("雞", "1100", "58")])),
        )
        for source, original, changed in cases:
            with self.subTest(source=source):
                self.ingest(source, original, "2025-12")
                path = snapshot_path(self.data, source, "2025-12")
                before = path.read_bytes()
                for candidate in (original, changed):
                    with self.subTest(source=source, identical=candidate == original):
                        with self.assertRaisesRegex(TaipeiMonthlyError, "registry contract is not verified authoritative"):
                            self.ingest(source, candidate, "2025-12", retrieved_at="2026-02-01T00:00:00Z", source_status="live")
                        self.assertEqual(path.read_bytes(), before)

    def test_retained_live_revision_requires_trusted_and_stored_verification(self):
        cases = (
            ("retail", retail_csv([("香蕉", "30")])),
            ("supply", supply_csv([("雞", "1000", "60")])),
        )
        for source, raw in cases:
            with self.subTest(source=source):
                self.ingest(source, raw, "2025-12")
                path = snapshot_path(self.data, source, "2025-12")
                stored = json.loads(path.read_text(encoding="utf-8"))
                revision = stored["revisions"][0]
                revision["source_status"] = "live"
                revision["contract_status"] = VERIFIED_AUTHORITATIVE_CONTRACT_STATUS
                with self.assertRaisesRegex(TaipeiMonthlyError, "registry contract is not verified authoritative"):
                    validate_snapshot_document(stored, source, "2025-12")

                revision["contract_status"] = SOURCES[source]["contract_status"]
                with mock.patch.dict(SOURCES[source], {"contract_status": VERIFIED_AUTHORITATIVE_CONTRACT_STATUS}):
                    with self.assertRaisesRegex(TaipeiMonthlyError, "stored contract is not verified authoritative"):
                        validate_snapshot_document(stored, source, "2025-12")
                    revision["contract_status"] = VERIFIED_AUTHORITATIVE_CONTRACT_STATUS
                    self.assertIs(validate_snapshot_document(stored, source, "2025-12"), stored)

    def test_fixture_bom_ingestion_remains_valid(self):
        cases = (
            ("retail", retail_csv([("香蕉", "30")])),
            ("supply", supply_csv([("雞", "1000", "60")])),
        )
        for source, raw in cases:
            with self.subTest(source=source):
                self.ingest(source, b"\xef\xbb\xbf" + raw, "2025-12")
                path = snapshot_path(self.data, source, "2025-12")
                stored = json.loads(path.read_text(encoding="utf-8"))
                self.assertIs(validate_snapshot_document(stored, source, "2025-12"), stored)
                self.assertFalse(stored["revisions"][0]["raw_text"].startswith("\ufeff"))

    def test_revisions_known_after_the_requested_date_are_ignored(self):
        self.ingest("retail", retail_csv([("香蕉", "30")]), "2025-12", retrieved_at="2026-01-10T00:00:00Z")
        self.ingest("retail", retail_csv([("香蕉", "35")]), "2025-12", retrieved_at="2026-09-01T00:00:00Z")
        self.ingest("retail", retail_csv([("香蕉", "36")]), "2026-08", retrieved_at="2026-09-10T00:00:00Z")
        document = self.analyse()
        self.assertEqual(self.item(document, "香蕉")["latest_price_raw"], 30.0)
        self.assertEqual([row["period"] for row in document["sources"][0]["periods"]], ["2025-12"])

    def test_period_must_agree_with_the_resource_name(self):
        with self.assertRaises(TaipeiMonthlyError):
            self.ingest("retail", retail_csv([("香蕉", "30")]), "2025-11", name="114年12月份行情")
        self.assertEqual(self.ingest("retail", retail_csv([("香蕉", "30")]), "2025-11", name="manual upload")["status"], "added")
        self.assertEqual(self.analyse()["sources"][0]["periods"][0]["period_evidence"], "operator")

    def test_descriptive_statistics_are_exact(self):
        for offset in range(13):
            period = "%04d-%02d" % (2024 + (11 + offset) // 12, (11 + offset) % 12 + 1)
            self.ingest("retail", retail_csv([("香蕉", 100 + offset)]), period)
        banana = self.item(self.analyse(), "香蕉")
        self.assertEqual((banana["valid_month_count"], banana["latest_valid_period"]), (13, "2025-12"))
        self.assertEqual((banana["median_price_raw"], banana["q1_price_raw"], banana["q3_price_raw"]), (106.0, 103.0, 109.0))
        self.assertEqual((banana["mom_pct"], banana["yoy_pct"]), (round(1 / 111 * 100, 6), 12.0))
        self.assertEqual((banana["latest_vs_history"], banana["advice"]), ("above_q3", {"status": "historical_reference", "basis": "latest_published_month"}))

    def test_short_history_is_insufficient_not_a_recommendation(self):
        self.ingest("retail", retail_csv([("香蕉", "30")]), "2025-11")
        self.ingest("retail", retail_csv([("香蕉", "20")]), "2025-12")
        banana = self.item(self.analyse(), "香蕉")
        self.assertEqual((banana["stats_status"], banana["median_price_raw"], banana["latest_vs_history"]), ("insufficient", None, None))
        self.assertEqual(banana["advice"]["status"], "insufficient")

    def test_supply_keeps_categories_and_reports_volume_price_trend(self):
        self.ingest("supply", supply_csv([("雞", "1000", "60"), ("魚", "500", "150")]), "2025-11")
        self.ingest("supply", supply_csv([("雞", "1100", "58"), ("魚", "500", "150")]), "2025-12")
        document = self.analyse()
        categories = {row["category"]: row for row in document["supply_categories"]}
        self.assertEqual(list(categories), ["雞", "鴨", "魚", "蔬菜", "水果"])
        self.assertEqual(categories["雞"]["trend"], {"volume": "up", "price": "down"})
        self.assertEqual(categories["魚"]["trend"], {"volume": "flat", "price": "flat"})
        self.assertIsNone(categories["鴨"]["trend"])
        self.assertEqual(categories["鴨"]["months"], [])
        self.assertEqual(document["retail_items"], [])

    def test_nothing_ingested_publishes_no_numbers(self):
        document = self.analyse()
        self.assertEqual([source["status"] for source in document["sources"]], ["not_ingested", "not_ingested"])
        self.assertEqual((document["retail_items"], document["supply_categories"]), ([], []))
        self.assertIs(document["national_fallback"], False)

    def test_monthly_analysis_ignores_daily_wholesale_rows(self):
        self.ingest("retail", retail_csv([("香蕉", "30")]), "2025-12")
        baseline = self.analyse()
        market = self.data / "market/daily/2025/12/2025-12-01.json"
        market.parent.mkdir(parents=True)
        market.write_text(json.dumps([{"canonical_id": "banana", "avg_price_twd_per_kg": 999, "volume_kg": 1, "market_code": "104"}]), encoding="utf-8")
        self.assertEqual(self.analyse(), baseline)

    def test_failed_document_and_validator_reject_boundary_violations(self):
        failed = failed_monthly_analysis("2026-08-25", PUBLICATION, "TaipeiMonthlyError: drift")
        self.assertEqual((failed["analysis_status"], failed["retail_items"], failed["sources"]), ("failed", [], []))
        self.assertEqual(monthly_csv_documents(failed)["monthly-retail.csv"].count("\n"), 1)
        self.ingest("retail", retail_csv([("香蕉", "30")]), "2025-12")
        document = self.analyse()
        tampering = (
            lambda value: value.update(national_fallback=True),
            lambda value: value.update(buy_score="evaluated"),
            lambda value: value["retail_items"][0]["advice"].update(status="cheapest_today"),
            lambda value: value["retail_items"][0]["months"][0].update(price_twd_per_kg=30.0),
            lambda value: value["retail_items"][0].update(commodity_family="fruit"),
            lambda value: value.update(failure_reason="stale"),
            lambda value: value.update(extra=True),
        )
        for tamper in tampering:
            changed = copy.deepcopy(document)
            tamper(changed)
            with self.assertRaises(TaipeiMonthlyError):
                validate_monthly_analysis(changed)
        failed["retail_items"] = document["retail_items"]
        with self.assertRaises(TaipeiMonthlyError):
            validate_monthly_analysis(failed)

    def test_fixture_rebuild_is_deterministic(self):
        fixture = json.loads((ROOT / "config/taipei-monthly.fixture.json").read_text(encoding="utf-8"))
        for source, period, name, text in fixture_snapshots(fixture):
            self.ingest(source, text.encode("utf-8"), period, name=name)
        first, second = self.analyse(), self.analyse()
        encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(encode(first), encode(second))
        self.assertEqual(monthly_csv_documents(first), monthly_csv_documents(second))
        self.assertEqual(len(first["retail_items"]), len(fixture["retail"]["items"]))
        self.assertEqual({source["status"] for source in first["sources"]}, {"fixture"})

    def test_reviewed_mapping_registry_is_strict(self):
        self.assertEqual(load_retail_mapping(ROOT), {})
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            (root / "config").mkdir()
            entry = {"item_raw": "雞蛋", "commodity_family": "livestock", "canonical_id": None, "variant": None, "cut": None, "grade": None, "mass_basis": False, "evidence": "reviewed"}
            for broken in ({**entry, "commodity_family": "dairy"}, {**entry, "evidence": " "}, {**entry, "cut": ""}, {**entry, "mass_basis": "no"}):
                (root / "config/taipei-retail-items.json").write_text(json.dumps({"schema_version": "1.0", "review_policy": "x", "items": [broken]}), encoding="utf-8")
                with self.assertRaises(TaipeiMonthlyError):
                    load_retail_mapping(root)
            (root / "config/taipei-retail-items.json").write_text(json.dumps({"schema_version": "1.0", "review_policy": "x", "items": [entry, entry]}), encoding="utf-8")
            with self.assertRaises(TaipeiMonthlyError):
                load_retail_mapping(root)

    def test_schema_documents_the_validated_contract(self):
        schema = json.loads((ROOT / "schema/taipei-monthly.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["required"]), FIELDS)


if __name__ == "__main__":
    unittest.main()
