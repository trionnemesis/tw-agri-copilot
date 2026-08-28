import unittest

from tpw.traceability import TRACEABILITY_WARNING, filter_traceability, normalize_registry


class TraceabilityTest(unittest.TestCase):
    def test_filter_nullable_fields_data_minimization_and_non_join_boundary(self):
        items = [{"canonical_id": "banana", "display_name": "香蕉", "aliases": []}]
        raw = [
            {
                "Tracecode": "DEMO-1",
                "Producer": "示範組織",
                "ProductName": "香蕉",
                "Place": "屏東縣內埔鄉詳細地段",
                "FarmerName": "不應保存",
                "StoreInfo": "不應保存",
                "PackDate": None,
                "ValidDate": "invalid",
            },
            {"Tracecode": "IGNORE", "ProductName": "未知"},
        ]
        rows = filter_traceability(raw, items)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["place"], "屏東縣")
        self.assertNotIn("farmer_name", rows[0])
        self.assertNotIn("store_info", rows[0])
        self.assertIsNone(rows[0]["valid_date"])
        self.assertEqual(rows[0]["certification_status"], "unknown")
        self.assertEqual(rows[0]["semantic_warning"], TRACEABILITY_WARNING)
        self.assertNotIn("market_code", rows[0])

    def test_active_expired_missing_duplicate_and_unknown_are_profiled(self):
        items = [{"canonical_id": "banana", "display_name": "香蕉", "aliases": []}]
        active = {"Tracecode": "A", "ProductName": "香蕉", "Producer": "組織", "OrgID": "1", "Place": "屏東縣內埔鄉", "ValidDate": "2026/12/31"}
        expired = {"Tracecode": "B", "ProductName": "香蕉", "Producer": "組織", "OrgID": "1", "Place": "屏東縣內埔鄉", "ValidDate": "2026/01/01"}
        rows, profile = normalize_registry(
            [active, dict(active), expired, {"Tracecode": "", "ProductName": "香蕉"}, {"Tracecode": "C", "ProductName": "未知"}],
            items,
            "2026-08-25",
            "fixture",
            source_status="fixture",
        )
        self.assertEqual([row["certification_status"] for row in rows], ["active", "expired"])
        self.assertEqual(profile["active_record_count"], 1)
        self.assertEqual(profile["expired_record_count"], 1)
        self.assertEqual(profile["duplicate_count"], 1)
        self.assertEqual(profile["missing_tracecode_count"], 1)
        self.assertEqual(profile["unmapped_record_count"], 1)

    def test_conflicting_duplicate_tracecode_fails_closed(self):
        items = [{"canonical_id": "banana", "display_name": "香蕉", "aliases": []}]
        rows = [
            {"Tracecode": "A", "ProductName": "香蕉", "Producer": "甲"},
            {"Tracecode": "A", "ProductName": "香蕉", "Producer": "乙"},
        ]
        with self.assertRaisesRegex(ValueError, "conflicting tracecode"):
            normalize_registry(rows, items, "2026-08-25", "fixture", source_status="fixture")
