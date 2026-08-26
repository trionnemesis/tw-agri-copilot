import unittest

from tpw.traceability import TRACEABILITY_WARNING, filter_traceability


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
        self.assertIsNone(rows[0]["farmer_name"])
        self.assertIsNone(rows[0]["store_info"])
        self.assertIsNone(rows[0]["valid_date"])
        self.assertEqual(rows[0]["semantic_warning"], TRACEABILITY_WARNING)
        self.assertNotIn("market_code", rows[0])
