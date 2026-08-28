import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from tpw.cli import refresh_traceability_events, traceability_event_context
from tpw.market import UpstreamUnavailable


ROOT = pathlib.Path(__file__).parents[2]


def event_rows(count=5, date="20260825"):
    codes = ["A1", "B2", "811", "FC1", "LF1"]
    names = ["香蕉", "鳳梨", "紅龍果", "胡瓜", "蕹菜"]
    return [
        {
            "交易日期": date,
            "作物代號": codes[index],
            "作物名稱": names[index],
            "市場代號": f"10{index}",
            "市場名稱": f"公開市場 {index}",
            "交易金額_元": str(2000 + index),
            "交易量_公斤": str(100 + index),
            "溯源代號": "X",
        }
        for index in range(count)
    ]


class TraceabilityMarketEventRefreshIntegrationTest(unittest.TestCase):
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

    def test_same_date_transient_failure_uses_same_source_lkg(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            live = refresh_traceability_events(
                "2026-08-25",
                fetcher=lambda _date: (event_rows(), "sha256:" + "1" * 64),
                retrieved_at="2026-08-25T21:00:00Z",
            )
            self.assertEqual(live["source_status"], "live")
            current_path = root / "data/traceability/market-events/current.json"
            published = json.loads(current_path.read_text())
            self.assertTrue(all(row["eligible_for_market_aggregate"] is False for row in published))
            self.assertTrue(all(row["affects_buy_score"] is False for row in published))

            stale = refresh_traceability_events(
                "2026-08-25",
                fetcher=mock.Mock(side_effect=UpstreamUnavailable("temporary")),
                retrieved_at="2026-08-25T22:00:00Z",
            )
            self.assertEqual(stale["source_status"], "stale")
            self.assertEqual(stale["requested_date"], "2026-08-25")
            self.assertEqual(stale["last_attempt_at"], "2026-08-25T22:00:00Z")
            self.assertTrue(
                all(row["source_status"] == "stale" for row in json.loads(current_path.read_text()))
            )

    def test_different_date_failure_does_not_relabel_prior_events(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            refresh_traceability_events(
                "2026-08-25",
                fetcher=lambda _date: (event_rows(), "sha256:" + "2" * 64),
                retrieved_at="2026-08-25T21:00:00Z",
            )
            current_path = root / "data/traceability/market-events/current.json"
            profile_path = root / "data/traceability/market-events/source-profile.json"
            before = (current_path.read_bytes(), profile_path.read_bytes())
            result = refresh_traceability_events(
                "2026-08-26",
                fetcher=mock.Mock(side_effect=UpstreamUnavailable("temporary")),
                retrieved_at="2026-08-26T21:00:00Z",
            )
            self.assertEqual(result["source_status"], "unavailable")
            self.assertEqual(result["requested_date"], "2026-08-26")
            self.assertEqual(before, (current_path.read_bytes(), profile_path.read_bytes()))

    def test_historical_context_does_not_reuse_future_current_snapshot(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            refresh_traceability_events(
                "2026-08-28",
                fetcher=lambda _date: (event_rows(date="20260828"), "sha256:" + "3" * 64),
                retrieved_at="2026-08-28T21:00:00Z",
            )
            rows, profile = traceability_event_context("2026-08-25")
            self.assertEqual(profile["requested_date"], "2026-08-25")
            self.assertEqual(profile["source_status"], "fixture")
            self.assertTrue(rows)
            self.assertTrue(all(row["transaction_date"] == "2026-08-25" for row in rows))
            exact_rows = root / "data/traceability/market-events/daily/2026/08/2026-08-28.json"
            exact_profile = root / "data/traceability/market-events/profiles/2026/08/2026-08-28.json"
            self.assertTrue(exact_rows.exists())
            self.assertTrue(exact_profile.exists())

    def test_count_regression_and_schema_drift_preserve_lkg_bytes(self):
        temporary, root = self.isolated_root()
        with temporary, mock.patch("tpw.cli.ROOT", root):
            refresh_traceability_events(
                "2026-08-25",
                fetcher=lambda _date: (event_rows(), "sha256:" + "4" * 64),
                retrieved_at="2026-08-25T21:00:00Z",
            )
            current_path = root / "data/traceability/market-events/current.json"
            profile_path = root / "data/traceability/market-events/source-profile.json"
            before = (current_path.read_bytes(), profile_path.read_bytes())
            with self.assertRaisesRegex(ValueError, "80 percent"):
                refresh_traceability_events(
                    "2026-08-25",
                    fetcher=lambda _date: (event_rows(3), "sha256:" + "5" * 64),
                    retrieved_at="2026-08-25T22:00:00Z",
                )
            self.assertEqual(before, (current_path.read_bytes(), profile_path.read_bytes()))
            with self.assertRaisesRegex(ValueError, "object"):
                refresh_traceability_events(
                    "2026-08-25",
                    fetcher=lambda _date: (["schema drift"], "sha256:" + "6" * 64),
                    retrieved_at="2026-08-25T22:00:00Z",
                )
            self.assertEqual(before, (current_path.read_bytes(), profile_path.read_bytes()))
