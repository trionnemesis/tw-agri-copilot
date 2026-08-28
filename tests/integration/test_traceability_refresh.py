import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from tpw.cli import refresh_traceability, traceability_context
from tpw.market import UpstreamUnavailable


ROOT = pathlib.Path(__file__).parents[2]


def registry_rows(count=5, valid_date="2026/12/31"):
    names = ["香蕉", "鳳梨", "胡瓜", "蕹菜", "紅龍果"]
    return [
        {
            "Tracecode": f"LIVE-{index}",
            "Producer": f"公開經營業者 {index}",
            "OrgID": f"ORG-{index}",
            "ProductName": names[index],
            "Place": "屏東縣內埔鄉精確地址",
            "FarmerName": "不得發布",
            "StoreInfo": "不得發布",
            "LandSecNO": "不得發布",
            "PackDate": "2026/08/25",
            "CertificationName": "公開驗證機構",
            "ValidDate": valid_date,
            "Log_UpdateTime": "2026/08/25",
        }
        for index in range(count)
    ]


class TraceabilityRefreshIntegrationTest(unittest.TestCase):
    def isolated_root(self):
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        (root / "config").mkdir()
        shutil.copy2(ROOT / "config/produce.yml", root / "config/produce.yml")
        shutil.copy2(ROOT / "config/traceability.fixture.json", root / "config/traceability.fixture.json")
        return temporary, root

    def test_live_refresh_then_transient_failure_uses_same_source_lkg(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            live = refresh_traceability(
                "2026-08-25",
                fetcher=lambda: (registry_rows(), "sha256:" + "1" * 64),
                retrieved_at="2026-08-25T01:00:00Z",
            )
            self.assertEqual(live["source_status"], "live")
            current_path = root / "data/traceability/current.json"
            published = json.loads(current_path.read_text())
            self.assertNotIn("FarmerName", current_path.read_text())
            self.assertNotIn("不得發布", current_path.read_text())
            self.assertTrue(all(row["place"] == "屏東縣" for row in published))

            stale = refresh_traceability(
                "2026-08-26",
                fetcher=mock.Mock(side_effect=UpstreamUnavailable("temporary")),
                retrieved_at="2026-08-26T01:00:00Z",
            )
            self.assertEqual(stale["source_status"], "stale")
            self.assertEqual(stale["as_of_date"], "2026-08-26")
            self.assertTrue(all(row["source_status"] == "stale" for row in json.loads(current_path.read_text())))

    def test_historical_context_does_not_reuse_future_current_snapshot(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            refresh_traceability(
                "2026-08-28",
                fetcher=lambda: (registry_rows(), "sha256:" + "5" * 64),
                retrieved_at="2026-08-28T01:00:00Z",
            )
            rows, profile = traceability_context("2026-08-25")
            self.assertEqual(profile["as_of_date"], "2026-08-25")
            self.assertEqual(profile["source_status"], "fixture")
            self.assertTrue(rows)
            self.assertTrue(all(row["source_status"] == "fixture" for row in rows))
            exact_rows = root / "data/traceability/daily/2026/08/2026-08-28.json"
            exact_profile = root / "data/traceability/profiles/2026/08/2026-08-28.json"
            self.assertTrue(exact_rows.exists())
            self.assertTrue(exact_profile.exists())

    def test_stale_lkg_reclassifies_validity_for_requested_date(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            live = refresh_traceability(
                "2026-08-25",
                fetcher=lambda: (registry_rows(valid_date="2026/08/25"), "sha256:" + "6" * 64),
                retrieved_at="2026-08-25T01:00:00Z",
            )
            self.assertEqual(live["active_record_count"], 5)
            stale = refresh_traceability(
                "2026-08-26",
                fetcher=mock.Mock(side_effect=UpstreamUnavailable("temporary")),
                retrieved_at="2026-08-26T01:00:00Z",
            )
            current = json.loads((root / "data/traceability/current.json").read_text())
            self.assertEqual(stale["as_of_date"], "2026-08-26")
            self.assertEqual(stale["active_record_count"], 0)
            self.assertEqual(stale["expired_record_count"], 5)
            self.assertEqual(stale["retrieved_at"], "2026-08-25T01:00:00Z")
            self.assertEqual(stale["last_attempt_at"], "2026-08-26T01:00:00Z")
            self.assertTrue(all(row["certification_status"] == "expired" for row in current))
            self.assertTrue(all(row["retrieved_at"] == "2026-08-25T01:00:00Z" for row in current))

    def test_count_regression_and_schema_drift_preserve_lkg_bytes(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            refresh_traceability(
                "2026-08-25",
                fetcher=lambda: (registry_rows(), "sha256:" + "2" * 64),
                retrieved_at="2026-08-25T01:00:00Z",
            )
            current_path = root / "data/traceability/current.json"
            profile_path = root / "data/traceability/source-profile.json"
            before = (current_path.read_bytes(), profile_path.read_bytes())
            with self.assertRaisesRegex(ValueError, "80 percent"):
                refresh_traceability(
                    "2026-08-26",
                    fetcher=lambda: (registry_rows(3), "sha256:" + "3" * 64),
                    retrieved_at="2026-08-26T01:00:00Z",
                )
            self.assertEqual(before, (current_path.read_bytes(), profile_path.read_bytes()))
            with self.assertRaisesRegex(ValueError, "object"):
                refresh_traceability(
                    "2026-08-26",
                    fetcher=lambda: (["schema drift"], "sha256:" + "4" * 64),
                    retrieved_at="2026-08-26T01:00:00Z",
                )
            self.assertEqual(before, (current_path.read_bytes(), profile_path.read_bytes()))
