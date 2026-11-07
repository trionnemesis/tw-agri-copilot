import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.integration.test_build import IGNORED


REPO = pathlib.Path(__file__).parents[2]


class LatestMarketBuildTest(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = pathlib.Path(workspace.name) / "repo"
        shutil.copytree(REPO, self.root, ignore=IGNORED, symlinks=True)
        self.command("seed-prototype", "--as-of", "2026-08-25")
        original = json.loads((self.root / "data/market/daily/2026/08/2026-08-25.json").read_text())
        # Seeded rows are only test inputs, never used to overwrite the real repo.
        self.new_rows = [dict(row, transaction_date="2026-08-26") for row in original]
        self.set_snapshot([row for row in self.new_rows if row["canonical_id"] != "mango"], "incomplete", 19)

    def command(self, *args, check=True):
        result = subprocess.run([sys.executable, "-m", "tpw", *args], cwd=self.root,
                                capture_output=True, text=True,
                                env={**os.environ, "PYTHONPATH": str(REPO / "src")})
        if check and result.returncode:
            self.fail(result.stdout + result.stderr)
        return result

    def set_snapshot(self, rows, status, count):
        (self.root / "data/market/daily/2026/08/2026-08-26.json").write_text(json.dumps(rows))
        (self.root / "data/source-meta/2026-08-26.json").write_text(json.dumps({"status": "fixture"}))
        publication = {"schema_version": "1.0", "requested_date": "2026-08-26",
                       "status": status, "source_status": "fixture", "feed_status": "available",
                       "expected_watchlist_count": 20, "covered_watchlist_count": count,
                       "observed_record_count": len(rows)}
        (self.root / "data/market-status/current.json").write_text(json.dumps(publication))

    def test_partial_snapshot_and_historical_scores_are_separate(self):
        self.command("build", "--as-of", "2026-08-25")
        self.command("validate-data", "--as-of", "2026-08-25")
        self.command("verify-site", "--as-of", "2026-08-25")
        current = json.loads((self.root / "site/data/current.json").read_text())
        latest = json.loads((self.root / "site/data/latest-market.json").read_text())
        self.assertEqual(current["as_of_date"], "2026-08-25")
        self.assertEqual(latest["as_of_date"], "2026-08-26")
        self.assertEqual(latest["valid_watchlist_count"], 19)
        self.assertEqual(len(latest["items"]), 20)
        mango = next(row for row in latest["items"] if row["canonical_id"] == "mango")
        self.assertEqual(mango["observation_status"], "missing")
        self.assertIsNone(mango["price_twd_per_kg"])
        index = (self.root / "site/index.html").read_text()
        self.assertIn("有效行情 19／20 項", index)
        self.assertIn("缺資料（原因未確認）", index)
        self.assertIn("2026-08-25 價格漲跌", index)
        self.assertNotIn("class='recommendation-card", index)
        self.assertTrue(any(row["eligible"] for row in current["scores"]))
        for path in [self.root / "site/index.html", *list((self.root / "site/produce").glob("*.html")), *list((self.root / "site/trends").glob("*.html"))]:
            text = path.read_text()
            for misleading in ("今日推薦採買", "今日變便宜", "今天變貴", ">今日<", "AI 今日採買情報", "今日交易量", ">最新價<"):
                self.assertNotIn(misleading, text, str(path))
            if path.parent.name == "produce":
                self.assertNotIn("class='verdict positive'", text)
                self.assertIn("2026-08-25", text)
        subprocess.run([sys.executable, "-m", "tpw.presentation"], cwd=self.root, check=True,
                       capture_output=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")})
        self.command("verify-site", "--as-of", "2026-08-25")
        before = (self.root / "site/data/latest-market.json").read_bytes()
        self.command("build", "--as-of", "2026-08-25")
        self.assertEqual(before, (self.root / "site/data/latest-market.json").read_bytes())

    def test_tampering_and_missing_artifact_fail_validation(self):
        self.command("build", "--as-of", "2026-08-25")
        path = self.root / "site/data/latest-market.json"
        latest = json.loads(path.read_text())
        latest["items"][0]["price_twd_per_kg"] += 1
        path.write_text(json.dumps(latest))
        self.assertIn("latest market HTML does not match", self.command("verify-site", check=False).stderr)
        self.assertIn("latest market does not match stored observations", self.command("validate-data", "--as-of", "2026-08-25", check=False).stderr)
        path.unlink()
        self.assertIn("latest market payload is missing", self.command("verify-site", check=False).stderr)

    def test_partial_then_complete_then_unavailable_rebuilds_context(self):
        self.command("build", "--as-of", "2026-08-25")
        self.set_snapshot(self.new_rows, "complete", 20)
        self.command("build", "--as-of", "2026-08-26")
        self.command("validate-data", "--as-of", "2026-08-26")
        latest = json.loads((self.root / "site/data/latest-market.json").read_text())
        self.assertEqual(latest["valid_watchlist_count"], 20)
        self.assertEqual(latest["complete_reference_date"], "2026-08-26")
        self.assertIn("class='recommendation-card", (self.root / "site/index.html").read_text())
        # Delete any unrelated checked-in rows for this fixture's failure day.
        (self.root / "data/market/daily/2026/08/2026-08-27.json").unlink(missing_ok=True)
        self.command("record-market-status", "--requested-date", "2026-08-27", "--status", "source_unavailable")
        self.command("build", "--as-of", "2026-08-26")
        self.command("validate-data", "--as-of", "2026-08-26")
        latest = json.loads((self.root / "site/data/latest-market.json").read_text())
        self.assertEqual(latest["requested_date"], "2026-08-27")
        self.assertEqual(latest["as_of_date"], "2026-08-26")
        self.assertNotIn("class='recommendation-card", (self.root / "site/index.html").read_text())

    def test_production_partial_snapshot_does_not_change_complete_scores(self):
        # These are deliberately synthetic, live-shaped inputs inside a temp repo.
        # Marked fixture rows remain excluded by production-mode analysis.
        for path in (self.root / "data/market/daily").rglob("*.json"):
            rows = json.loads(path.read_text())
            for row in rows:
                row["fetched_at"] = row["transaction_date"] + "T12:00:00Z"
            path.write_text(json.dumps(rows))
        (self.root / "data/source-meta/2026-08-25.json").write_text(json.dumps({"status": "success"}))
        status_path = self.root / "data/market-status/current.json"
        status = json.loads(status_path.read_text())
        status.update(requested_date="2026-08-25", status="complete", source_status="success", covered_watchlist_count=20)
        status_path.write_text(json.dumps(status))
        self.command("build", "--as-of", "2026-08-25")
        scores = json.loads((self.root / "site/data/current.json").read_text())["scores"]
        status.update(requested_date="2026-08-26", status="incomplete", covered_watchlist_count=19)
        status_path.write_text(json.dumps(status))
        self.command("build", "--as-of", "2026-08-25")
        self.command("validate-data", "--as-of", "2026-08-25")
        latest = json.loads((self.root / "site/data/latest-market.json").read_text())
        self.assertEqual(latest["source_status"], "observed")
        self.assertEqual(latest["as_of_date"], "2026-08-26")
        self.assertEqual(latest["valid_watchlist_count"], 19)
        self.assertEqual(scores, json.loads((self.root / "site/data/current.json").read_text())["scores"])
