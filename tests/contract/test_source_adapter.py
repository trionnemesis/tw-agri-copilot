import json
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from tpw.analytics import aggregate
from tpw.cli import ingest_sources
from tpw.model import canonical_map, normalize
from tpw.source_adapter import (
    MOA_MARKET_8066_ADAPTER,
    TRANSACTION_SEMANTICS,
    RawBatch,
    SourceAdapter,
    SourceSpec,
    observations_from_records,
    resolve_observations,
    source_run_document,
    validate_source_run_document,
)


ROOT = pathlib.Path(__file__).parents[2]


class ValidationFixtureAdapter:
    """A deliberately different raw schema used only for contract proof."""

    def __init__(
        self,
        records,
        source_role="validation",
        precedence=10,
        source_id="fixture_validation",
    ):
        self.records = list(records)
        self.spec = SourceSpec(
            source_id=source_id,
            source_url="https://example.invalid/fixture-transactions",
            source_role=source_role,
            dataset_semantics=TRANSACTION_SEMANTICS,
            precedence=precedence,
            adapter_version="fixture-adapter-v1",
            source_schema_version="fixture-transaction-v1",
        )

    def fetch(self, start, end, opener=None):
        return RawBatch.from_records(
            self.spec,
            self.records,
            start,
            end,
            "fixture",
            status="fixture",
        )

    def normalize(self, batch, mapping):
        normalized = []
        for record in batch.records:
            normalized.append(
                normalize(
                    {
                        "交易日期": record["date"],
                        "種類代碼": record.get("category_code"),
                        "作物代號": record["crop_code"],
                        "作物名稱": record["crop_name"],
                        "市場代號": record["market_code"],
                        "市場名稱": record["market_name"],
                        "上價": record.get("high_price", 0),
                        "中價": record.get("mid_price", 0),
                        "下價": record.get("low_price", 0),
                        "平均價": record["average_price"],
                        "交易量": record["volume"],
                    },
                    mapping,
                    fetched_at=batch.retrieved_at,
                    source_id=self.spec.source_id,
                )
            )
        return observations_from_records(self.spec, batch, normalized)


def fixture_record(price=999, volume=999, crop_code="A1"):
    return {
        "date": "2026-08-25",
        "category_code": "N05",
        "crop_code": crop_code,
        "crop_name": "香蕉",
        "market_code": "104",
        "market_name": "台北二",
        "high_price": price + 1,
        "mid_price": price,
        "low_price": max(price - 1, 0),
        "average_price": price,
        "volume": volume,
    }


class SourceAdapterContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.configured = json.loads((ROOT / "config/produce.yml").read_text())["items"]
        cls.mapping = canonical_map(cls.configured)
        cls.moa_raw = json.loads(
            (ROOT / "tests/fixtures/market_success.json").read_text()
        )[0]

    def moa_batch(self, records=None):
        return MOA_MARKET_8066_ADAPTER.batch(
            records or [self.moa_raw],
            "2026-08-25",
            "2026-08-25",
            "fixture",
        )

    def test_moa_adapter_implements_contract_and_preserves_row_hash(self):
        self.assertIsInstance(MOA_MARKET_8066_ADAPTER, SourceAdapter)
        observations = MOA_MARKET_8066_ADAPTER.normalize(
            self.moa_batch(), self.mapping
        )
        self.assertEqual(len(observations), 1)
        self.assertEqual(
            observations[0].record["row_hash"],
            "sha256:0305b4f838876b9a7d08c6ed3af24fbd4e7304e7e858c20d2c1d28d9f09f0dc8",
        )
        self.assertEqual(observations[0].source_role, "authoritative_final")

    def test_source_spec_rejects_unknown_role_and_invalid_precedence(self):
        values = {
            "source_id": "fixture_source",
            "source_url": "https://example.invalid/source",
            "source_role": "validation",
            "dataset_semantics": TRANSACTION_SEMANTICS,
            "precedence": 1,
            "adapter_version": "1",
            "source_schema_version": "1",
        }
        with self.assertRaisesRegex(ValueError, "invalid source_role"):
            SourceSpec(**dict(values, source_role="other"))
        with self.assertRaisesRegex(ValueError, "precedence"):
            SourceSpec(**dict(values, precedence=-1))

    def test_second_schema_is_evidence_only_and_does_not_change_aggregate(self):
        validation = ValidationFixtureAdapter([fixture_record()])
        moa_batch = self.moa_batch()
        validation_batch = validation.fetch("2026-08-25", "2026-08-25")
        moa = MOA_MARKET_8066_ADAPTER.normalize(moa_batch, self.mapping)
        reference = aggregate([dict(moa[0].record)])
        resolution = resolve_observations(
            moa + validation.normalize(validation_batch, self.mapping)
        )
        self.assertEqual(aggregate(resolution.eligible_records), reference)
        eligible = [
            item for item in resolution.observations if item.eligible_for_aggregate
        ]
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].source_id, "moa_market_8066")
        evidence = source_run_document(
            [
                (MOA_MARKET_8066_ADAPTER, moa_batch),
                (validation, validation_batch),
            ],
            resolution,
            "2026-08-25",
            "2026-08-25",
        )
        self.assertEqual(evidence["resolution_summary"]["observation_count"], 2)
        self.assertEqual(
            evidence["resolution_summary"]["eligible_for_aggregate_count"], 1
        )
        self.assertEqual(len(evidence["decisions"]), 1)
        self.assertEqual(
            sum(
                candidate["eligible_for_aggregate"]
                for candidate in evidence["decisions"][0]["candidates"]
            ),
            1,
        )

    def test_provisional_and_contextual_roles_never_enter_aggregate(self):
        provisional = ValidationFixtureAdapter(
            [fixture_record(price=19)],
            source_role="provisional",
            source_id="fixture_provisional",
        )
        contextual = ValidationFixtureAdapter(
            [fixture_record(price=7, crop_code="B2")],
            source_role="contextual",
            source_id="fixture_contextual",
        )
        moa_batch = self.moa_batch()
        provisional_batch = provisional.fetch("2026-08-25", "2026-08-25")
        contextual_batch = contextual.fetch("2026-08-25", "2026-08-25")
        resolution = resolve_observations(
            MOA_MARKET_8066_ADAPTER.normalize(moa_batch, self.mapping)
            + provisional.normalize(provisional_batch, self.mapping)
            + contextual.normalize(contextual_batch, self.mapping)
        )
        eligible = [
            item for item in resolution.observations if item.eligible_for_aggregate
        ]
        self.assertEqual([item.source_role for item in eligible], ["authoritative_final"])
        winner = eligible[0]
        provisional_record = next(
            item
            for item in resolution.observations
            if item.source_role == "provisional"
        )
        self.assertEqual(
            winner.supersedes_source_record_id,
            provisional_record.source_record_id,
        )

    def test_equal_precedence_authoritative_sources_fail_closed(self):
        second = ValidationFixtureAdapter(
            [fixture_record()],
            source_role="authoritative_final",
            precedence=100,
            source_id="fixture_authoritative",
        )
        with self.assertRaisesRegex(ValueError, "ambiguous authoritative sources"):
            resolve_observations(
                MOA_MARKET_8066_ADAPTER.normalize(self.moa_batch(), self.mapping)
                + second.normalize(
                    second.fetch("2026-08-25", "2026-08-25"), self.mapping
                )
            )

    def test_explicit_precedence_selects_one_of_two_final_sources(self):
        second = ValidationFixtureAdapter(
            [fixture_record()],
            source_role="authoritative_final",
            precedence=10,
            source_id="fixture_lower_precedence",
        )
        resolution = resolve_observations(
            MOA_MARKET_8066_ADAPTER.normalize(self.moa_batch(), self.mapping)
            + second.normalize(
                second.fetch("2026-08-25", "2026-08-25"), self.mapping
            )
        )
        eligible = [
            item for item in resolution.observations if item.eligible_for_aggregate
        ]
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].source_id, "moa_market_8066")

    def test_same_source_correction_uses_last_record(self):
        corrected = dict(self.moa_raw, 平均價=21)
        batch = self.moa_batch([self.moa_raw, corrected])
        resolution = resolve_observations(
            MOA_MARKET_8066_ADAPTER.normalize(batch, self.mapping)
        )
        eligible = [
            item for item in resolution.observations if item.eligible_for_aggregate
        ]
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].record["avg_price_twd_per_kg"], 21)
        self.assertEqual(
            eligible[0].supersedes_source_record_id,
            resolution.observations[0].source_record_id,
        )

    def test_ingest_persists_one_record_and_machine_readable_evidence(self):
        validation = ValidationFixtureAdapter([fixture_record()])
        moa_batch = self.moa_batch()
        validation_batch = validation.fetch("2026-08-25", "2026-08-25")
        with tempfile.TemporaryDirectory() as raw:
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
            with mock.patch("tpw.cli.ROOT", isolated):
                count = ingest_sources(
                    [
                        (MOA_MARKET_8066_ADAPTER, moa_batch),
                        (validation, validation_batch),
                    ],
                    "2026-08-25",
                    "2026-08-25",
                )
            self.assertEqual(count, 1)
            stored = json.loads(
                (
                    isolated
                    / "data/market/daily/2026/08/2026-08-25.json"
                ).read_text()
            )
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["source_id"], "moa_market_8066")
            self.assertEqual(stored[0]["avg_price_twd_per_kg"], 20)
            evidence = json.loads(
                (isolated / "data/source-runs/2026-08-25.json").read_text()
            )
            validate_source_run_document(evidence)
            self.assertEqual(
                {run["source_role"] for run in evidence["runs"]},
                {"authoritative_final", "validation"},
            )
            self.assertEqual(
                evidence["resolution_summary"]["eligible_for_aggregate_count"],
                1,
            )
            meta = json.loads(
                (isolated / "data/source-meta/2026-08-25.json").read_text()
            )
            self.assertEqual(meta["source_role"], "authoritative_final")

    def test_adapter_schema_drift_fails_before_promotion(self):
        invalid = ValidationFixtureAdapter(
            [{key: value for key, value in fixture_record().items() if key != "volume"}]
        )
        moa_batch = self.moa_batch()
        invalid_batch = invalid.fetch("2026-08-25", "2026-08-25")
        with tempfile.TemporaryDirectory() as raw:
            isolated = pathlib.Path(raw)
            (isolated / "config").mkdir()
            (isolated / "data").mkdir()
            shutil.copy2(ROOT / "config/produce.yml", isolated / "config/produce.yml")
            sentinel = isolated / "data/sentinel"
            sentinel.write_text("last-known-good")
            with mock.patch("tpw.cli.ROOT", isolated):
                with self.assertRaises(KeyError):
                    ingest_sources(
                        [
                            (MOA_MARKET_8066_ADAPTER, moa_batch),
                            (invalid, invalid_batch),
                        ],
                        "2026-08-25",
                        "2026-08-25",
                    )
            self.assertEqual(sentinel.read_text(), "last-known-good")

    def test_runtime_validator_rejects_two_selected_candidates(self):
        validation = ValidationFixtureAdapter(
            [fixture_record()],
            source_role="authoritative_final",
            source_id="fixture_lower_precedence",
        )
        moa_batch = self.moa_batch()
        validation_batch = validation.fetch("2026-08-25", "2026-08-25")
        resolution = resolve_observations(
            MOA_MARKET_8066_ADAPTER.normalize(moa_batch, self.mapping)
            + validation.normalize(validation_batch, self.mapping)
        )
        evidence = source_run_document(
            [
                (MOA_MARKET_8066_ADAPTER, moa_batch),
                (validation, validation_batch),
            ],
            resolution,
            "2026-08-25",
            "2026-08-25",
        )
        evidence["decisions"][0]["candidates"][1][
            "eligible_for_aggregate"
        ] = True
        with self.assertRaisesRegex(ValueError, "multiple eligible"):
            validate_source_run_document(evidence)


if __name__ == "__main__":
    unittest.main()
