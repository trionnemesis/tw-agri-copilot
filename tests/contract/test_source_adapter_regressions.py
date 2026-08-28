import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from tpw.cli import ingest_sources
from tpw.source_adapter import MOA_MARKET_8066_ADAPTER, SourceSpec, TRANSACTION_SEMANTICS
from tests.contract.test_source_adapter import ROOT, ValidationFixtureAdapter, fixture_record


class SemanticFixtureAdapter(ValidationFixtureAdapter):
    def __init__(self, records, dataset_semantics, source_id="fixture_semantics"):
        super().__init__(
            records,
            source_role="authoritative_final",
            precedence=100,
            source_id=source_id,
        )
        self.spec = SourceSpec(
            source_id=source_id,
            source_url="https://example.invalid/fixture-transactions",
            source_role="authoritative_final",
            dataset_semantics=dataset_semantics,
            precedence=100,
            adapter_version="fixture-adapter-v1",
            source_schema_version="fixture-transaction-v1",
        )


class SourceAdapterRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.moa_raw = json.loads(
            (ROOT / "tests/fixtures/market_success.json").read_text()
        )[0]

    def moa_batch(self):
        return MOA_MARKET_8066_ADAPTER.batch(
            [self.moa_raw],
            "2026-08-25",
            "2026-08-25",
            "fixture",
        )

    def isolated_root(self, raw):
        isolated = pathlib.Path(raw)
        (isolated / "config").mkdir()
        (isolated / "data").mkdir()
        shutil.copy2(ROOT / "config/produce.yml", isolated / "config/produce.yml")
        shutil.copy2(
            ROOT / "config/market-calendar.json",
            isolated / "config/market-calendar.json",
        )
        shutil.copytree(
            ROOT / "data/market-calendar", isolated / "data/market-calendar"
        )
        return isolated

    def test_lower_precedence_later_run_cannot_replace_stored_winner(self):
        lower = ValidationFixtureAdapter(
            [fixture_record(price=999)],
            source_role="authoritative_final",
            precedence=10,
            source_id="fixture_lower_precedence",
        )
        lower_batch = lower.fetch("2026-08-25", "2026-08-25")
        with tempfile.TemporaryDirectory() as raw:
            isolated = self.isolated_root(raw)
            with mock.patch("tpw.cli.ROOT", isolated):
                self.assertEqual(
                    ingest_sources(
                        [(MOA_MARKET_8066_ADAPTER, self.moa_batch())],
                        "2026-08-25",
                        "2026-08-25",
                    ),
                    1,
                )
            path = isolated / "data/market/daily/2026/08/2026-08-25.json"
            legacy = json.loads(path.read_text())
            for row in legacy:
                row.pop("dataset_semantics", None)
                row.pop("source_role", None)
                row.pop("source_precedence", None)
            path.write_text(json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            before = path.read_bytes()
            with mock.patch("tpw.cli.ROOT", isolated):
                with self.assertRaisesRegex(ValueError, "lower-precedence"):
                    ingest_sources(
                        [(lower, lower_batch)],
                        "2026-08-25",
                        "2026-08-25",
                    )
            self.assertEqual(before, path.read_bytes())
            stored = json.loads(path.read_text())
            self.assertEqual(stored[0]["source_id"], "moa_market_8066")

    def test_equal_precedence_disjoint_authoritative_sources_are_allowed(self):
        second_record = fixture_record(price=31)
        second_record["market_code"] = "109"
        second_record["market_name"] = "台北一"
        second = ValidationFixtureAdapter(
            [second_record],
            source_role="authoritative_final",
            precedence=100,
            source_id="fixture_authoritative",
        )
        second_batch = second.fetch("2026-08-25", "2026-08-25")
        with tempfile.TemporaryDirectory() as raw:
            isolated = self.isolated_root(raw)
            with mock.patch("tpw.cli.ROOT", isolated):
                count = ingest_sources(
                    [
                        (MOA_MARKET_8066_ADAPTER, self.moa_batch()),
                        (second, second_batch),
                    ],
                    "2026-08-25",
                    "2026-08-25",
                )
            self.assertEqual(count, 2)
            stored = json.loads(
                (
                    isolated
                    / "data/market/daily/2026/08/2026-08-25.json"
                ).read_text()
            )
            self.assertEqual(len(stored), 2)
            self.assertEqual({row["market_code"] for row in stored}, {"104", "109"})

    def test_dataset_semantics_remain_distinct_after_persistence(self):
        alternate_semantics = TRANSACTION_SEMANTICS + "_adjusted"
        second = SemanticFixtureAdapter(
            [fixture_record(price=31)],
            dataset_semantics=alternate_semantics,
        )
        second_batch = second.fetch("2026-08-25", "2026-08-25")
        with tempfile.TemporaryDirectory() as raw:
            isolated = self.isolated_root(raw)
            with mock.patch("tpw.cli.ROOT", isolated):
                count = ingest_sources(
                    [
                        (MOA_MARKET_8066_ADAPTER, self.moa_batch()),
                        (second, second_batch),
                    ],
                    "2026-08-25",
                    "2026-08-25",
                )
            self.assertEqual(count, 2)
            stored = json.loads(
                (
                    isolated
                    / "data/market/daily/2026/08/2026-08-25.json"
                ).read_text()
            )
            self.assertEqual(len(stored), 2)
            self.assertEqual(
                {row["dataset_semantics"] for row in stored},
                {TRANSACTION_SEMANTICS, alternate_semantics},
            )


if __name__ == "__main__":
    unittest.main()
