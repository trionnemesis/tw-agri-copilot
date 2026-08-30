import json
import pathlib
import tempfile
import unittest

from tpw.presentation import materialize_daily_snapshot, refresh_archive


class DailySnapshotHistoryTest(unittest.TestCase):
    def test_requested_date_materializes_without_moving_market_as_of_date(self):
        with tempfile.TemporaryDirectory() as raw:
            site = pathlib.Path(raw)
            (site / "data").mkdir(parents=True)
            market_page = site / "daily/2026/08/2026-08-27.html"
            market_page.parent.mkdir(parents=True)
            market_html = (
                "<html><head><title>每日行情 2026-08-27</title></head><body>"
                "<main><section class='section'><h1>每日行情 2026-08-27</h1>"
                "<p class='disclaimer'>批發市場平均行情</p></section>"
                "<table><tr><td>NT$ 20.00/kg</td></tr></table></main></body></html>"
            )
            market_page.write_text(market_html, encoding="utf-8")
            archive = site / "archive/index.html"
            archive.parent.mkdir(parents=True)
            archive.write_text(
                "<html><body><ul class='archive-list'>"
                "<li><a href='../daily/2026/08/2026-08-27.html'>2026-08-27</a></li>"
                "</ul></body></html>",
                encoding="utf-8",
            )
            current = {
                "as_of_date": "2026-08-27",
                "publication_status": {
                    "schema_version": "1.0",
                    "requested_date": "2026-08-30",
                    "resolved_date": "2026-08-27",
                    "status": "pending",
                    "source_status": "success",
                    "expected_watchlist_count": 20,
                    "covered_watchlist_count": 0,
                    "observed_record_count": 10,
                },
            }
            current_path = site / "data/current.json"
            current_text = json.dumps(current, ensure_ascii=False, sort_keys=True)
            current_path.write_text(current_text, encoding="utf-8")

            self.assertEqual(materialize_daily_snapshot(site), 2)
            self.assertEqual(refresh_archive(site), 1)

            snapshot_page = site / "daily/2026/08/2026-08-30.html"
            self.assertTrue(snapshot_page.exists())
            rendered = snapshot_page.read_text(encoding="utf-8")
            self.assertIn("每日快照 2026-08-30", rendered)
            self.assertIn("本次資料檢查：2026-08-30", rendered)
            self.assertIn("最近完整交易日：2026-08-27", rendered)
            self.assertIn("data-publication-status='pending'", rendered)
            self.assertIn("NT$ 20.00/kg", rendered)
            self.assertNotIn("每日行情 2026-08-30", rendered)
            self.assertEqual(market_page.read_text(encoding="utf-8"), market_html)
            self.assertEqual(current_path.read_text(encoding="utf-8"), current_text)

            payload = json.loads(
                (site / "data/snapshots/2026/08/2026-08-30.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(payload["snapshot_date"], "2026-08-30")
            self.assertEqual(payload["market_as_of_date"], "2026-08-27")
            self.assertEqual(payload["publication_status"]["status"], "pending")

            archive_html = archive.read_text(encoding="utf-8")
            self.assertLess(
                archive_html.index("2026-08-30"), archive_html.index("2026-08-27")
            )
            self.assertEqual(materialize_daily_snapshot(site), 0)
            self.assertEqual(refresh_archive(site), 0)

    def test_complete_date_only_adds_machine_readable_snapshot(self):
        with tempfile.TemporaryDirectory() as raw:
            site = pathlib.Path(raw)
            (site / "data").mkdir(parents=True)
            page = site / "daily/2026/08/2026-08-30.html"
            page.parent.mkdir(parents=True)
            page.write_text("complete market page", encoding="utf-8")
            (site / "data/current.json").write_text(
                json.dumps(
                    {
                        "as_of_date": "2026-08-30",
                        "publication_status": {
                            "requested_date": "2026-08-30",
                            "resolved_date": "2026-08-30",
                            "status": "complete",
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(materialize_daily_snapshot(site), 1)
            self.assertEqual(page.read_text(encoding="utf-8"), "complete market page")

    def test_mismatched_resolved_date_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            site = pathlib.Path(raw)
            (site / "data").mkdir(parents=True)
            (site / "data/current.json").write_text(
                json.dumps(
                    {
                        "as_of_date": "2026-08-27",
                        "publication_status": {
                            "requested_date": "2026-08-30",
                            "resolved_date": "2026-08-28",
                            "status": "pending",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "resolved_date"):
                materialize_daily_snapshot(site)


if __name__ == "__main__":
    unittest.main()
