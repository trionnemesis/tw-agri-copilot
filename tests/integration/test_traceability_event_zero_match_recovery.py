import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from tpw.cli import refresh_traceability_events
from tpw.traceability_event_recovery import preserve_same_date_h44_as_stale


ROOT = pathlib.Path(__file__).parents[2]


def mapped_rows(date="20260830"):
    return [
        {
            "交易日期": date,
            "作物代號": "A1",
            "作物名稱": "香蕉",
            "市場代號": "104",
            "市場名稱": "公開市場",
            "交易金額_元": "2000",
            "交易量_公斤": "100",
            "溯源代號": "X",
        }
    ]


class TraceabilityEventZeroMatchRecoveryIntegrationTest(unittest.TestCase):
    def isolated_root(self):
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        (root / "config").mkdir()
        shutil.copy2(ROOT / "config/produce.yml", root / "config/produce.yml")
        shutil.copy2(
            ROOT / "config/traceability-events.fixture.json",
            root / "config/traceability-events.fixture.json",
        )
        return temporary, root

    def test_same_date_live_snapshot_is_downgraded_to_stale(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            live = refresh_traceability_events(
                "2026-08-30",
                fetcher=lambda _date: (mapped_rows(), "sha256:" + "1" * 64),
                retrieved_at="2026-08-30T10:00:00Z",
            )
            self.assertEqual(live["source_status"], "live")

            result = preserve_same_date_h44_as_stale(
                "2026-08-30", attempted_at="2026-08-30T15:00:00Z"
            )
            self.assertEqual(result["source_status"], "stale")
            self.assertEqual(result["last_attempt_at"], "2026-08-30T15:00:00Z")
            self.assertEqual(result["last_attempt_reason"], "no_explicitly_mapped_records")

            base = root / "data/traceability/market-events"
            rows = json.loads((base / "current.json").read_text())
            profile = json.loads((base / "source-profile.json").read_text())
            daily_profile = json.loads(
                (base / "profiles/2026/08/2026-08-30.json").read_text()
            )
            self.assertTrue(rows)
            self.assertTrue(all(row["source_status"] == "stale" for row in rows))
            self.assertEqual(profile["source_status"], "stale")
            self.assertEqual(daily_profile["source_status"], "stale")
            self.assertEqual(profile["last_attempt_reason"], "no_explicitly_mapped_records")

    def test_different_date_does_not_relabel_prior_live_snapshot_without_archive(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            refresh_traceability_events(
                "2026-08-30",
                fetcher=lambda _date: (mapped_rows(), "sha256:" + "2" * 64),
                retrieved_at="2026-08-30T10:00:00Z",
            )
            base = root / "data/traceability/market-events"
            before = (
                (base / "current.json").read_bytes(),
                (base / "source-profile.json").read_bytes(),
            )

            result = preserve_same_date_h44_as_stale(
                "2026-08-31", attempted_at="2026-08-31T15:00:00Z"
            )
            self.assertEqual(result["source_status"], "unavailable")
            self.assertEqual(result["preserved_status"], "live")
            self.assertEqual(
                before,
                (
                    (base / "current.json").read_bytes(),
                    (base / "source-profile.json").read_bytes(),
                ),
            )

    def test_historical_exact_date_archive_is_downgraded_even_when_current_is_newer(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            refresh_traceability_events(
                "2026-08-30",
                fetcher=lambda _date: (mapped_rows("20260830"), "sha256:" + "3" * 64),
                retrieved_at="2026-08-30T10:00:00Z",
            )
            refresh_traceability_events(
                "2026-08-31",
                fetcher=lambda _date: (mapped_rows("20260831"), "sha256:" + "4" * 64),
                retrieved_at="2026-08-31T10:00:00Z",
            )
            base = root / "data/traceability/market-events"
            newer_profile_path = base / "profiles/2026/08/2026-08-31.json"
            self.assertEqual(
                json.loads((base / "source-profile.json").read_text())["requested_date"],
                "2026-08-31",
            )

            result = preserve_same_date_h44_as_stale(
                "2026-08-30", attempted_at="2026-09-01T01:00:00Z"
            )
            archived_profile = json.loads(
                (base / "profiles/2026/08/2026-08-30.json").read_text()
            )
            newer_profile = json.loads(newer_profile_path.read_text())
            self.assertEqual(result["source_status"], "stale")
            self.assertEqual(result["requested_date"], "2026-08-30")
            self.assertEqual(archived_profile["source_status"], "stale")
            self.assertEqual(
                archived_profile["last_attempt_reason"],
                "no_explicitly_mapped_records",
            )
            self.assertEqual(newer_profile["source_status"], "live")
            self.assertEqual(newer_profile["requested_date"], "2026-08-31")


if __name__ == "__main__":
    unittest.main()
