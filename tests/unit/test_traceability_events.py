import unittest

from tpw.traceability_events import EVENT_WARNING, normalize_market_events


ITEMS = [
    {
        "canonical_id": "banana",
        "display_name": "香蕉",
        "market_crop_codes": ["A1"],
    }
]


def event(**changes):
    row = {
        "交易日期": "20260825",
        "作物代號": "A1",
        "作物名稱": "香蕉",
        "市場代號": "104",
        "市場名稱": "台北二",
        "交易金額_元": "1,250",
        "交易量_公斤": "42.5",
        "溯源代號": "X",
    }
    row.update(changes)
    return row


class TraceabilityMarketEventTest(unittest.TestCase):
    def test_exact_mapping_preserves_event_and_excludes_decision_inputs(self):
        rows, profile = normalize_market_events(
            [event()], ITEMS, "2026-08-25", "2026-08-25T21:00:00Z"
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["canonical_id"], "banana")
        self.assertEqual(row["transaction_date"], "2026-08-25")
        self.assertEqual(row["transaction_amount_twd"], 1250)
        self.assertEqual(row["transaction_volume_kg"], 42.5)
        self.assertEqual(row["traceability_class_code"], "X")
        self.assertNotIn("tracecode", row)
        self.assertIs(row["eligible_for_market_aggregate"], False)
        self.assertIs(row["affects_buy_score"], False)
        self.assertEqual(row["semantic_warning"], EVENT_WARNING)
        self.assertIs(profile["eligible_for_market_aggregate"], False)
        self.assertIs(profile["affects_buy_score"], False)

    def test_exact_duplicate_is_deduplicated_and_unknown_is_counted(self):
        rows, profile = normalize_market_events(
            [event(), event(), event(**{"作物代號": "ZZ", "作物名稱": "未知"})],
            ITEMS,
            "2026-08-25",
            "fixture",
            source_status="fixture",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(profile["duplicate_count"], 1)
        self.assertEqual(profile["unmapped_record_count"], 1)

    def test_out_of_range_date_and_bad_numeric_values_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            normalize_market_events(
                [event(**{"交易日期": "20260824"})], ITEMS, "2026-08-25", "fixture"
            )
        for value in ("", "bad", "-1"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "amount"):
                normalize_market_events(
                    [event(**{"交易金額_元": value})], ITEMS, "2026-08-25", "fixture"
                )
