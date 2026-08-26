import json
import pathlib
import tempfile
import unittest

from tpw.schedule import latest_complete_date


class ScheduleDateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "config/produce.yml").write_text(
            json.dumps(
                {
                    "items": [
                        {"canonical_id": "banana"},
                        {"canonical_id": "papaya"},
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_day(self, day, canonical_ids):
        path = self.root / "data/market/daily" / day[:4] / day[5:7] / f"{day}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [
                    {"canonical_id": canonical_id, "transaction_date": day}
                    for canonical_id in canonical_ids
                ]
            ),
            encoding="utf-8",
        )

    def test_falls_back_to_latest_complete_date(self):
        self.write_day("2026-08-26", ["banana", "papaya"])
        self.write_day("2026-08-27", ["banana"])
        self.assertEqual(
            latest_complete_date(self.root, "2026-08-27"),
            "2026-08-26",
        )

    def test_does_not_use_future_complete_date(self):
        self.write_day("2026-08-26", ["banana", "papaya"])
        self.write_day("2026-08-28", ["banana", "papaya"])
        self.assertEqual(
            latest_complete_date(self.root, "2026-08-27"),
            "2026-08-26",
        )

    def test_fails_when_no_complete_date_exists(self):
        self.write_day("2026-08-26", ["banana"])
        with self.assertRaisesRegex(ValueError, "no complete configured watchlist date"):
            latest_complete_date(self.root, "2026-08-27")
