"""Transaction-source contract and economic-observation resolution policy.

The contract keeps source evidence outside the normalized market record.  Only
records selected by :func:`resolve_observations` may enter the existing
analytics pipeline, so adding an endpoint cannot silently double-count the same
market/crop/day transaction.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .market import URL as MOA_MARKET_URL
from .market import fetch as fetch_moa_market
from .model import normalize


SOURCE_ROLES = frozenset(
    {"authoritative_final", "provisional", "validation", "contextual"}
)
AGGREGATE_SOURCE_ROLE = "authoritative_final"
RESOLUTION_POLICY_VERSION = "economic-observation-v1"
TRANSACTION_SEMANTICS = "wholesale_market_daily_transaction"
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def raw_content_hash(records: Sequence[Mapping[str, Any]]) -> str:
    """Match the historical 8066 metadata hash while centralizing ownership."""

    payload = json.dumps(
        list(records), ensure_ascii=False, sort_keys=True
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_url: str
    source_role: str
    dataset_semantics: str
    precedence: int
    adapter_version: str
    source_schema_version: str

    def __post_init__(self) -> None:
        for field in (
            "source_id",
            "source_url",
            "source_role",
            "dataset_semantics",
            "adapter_version",
            "source_schema_version",
        ):
            object.__setattr__(
                self, field, _required_text(getattr(self, field), field)
            )
        source_id = self.source_id
        if not _ID.fullmatch(source_id):
            raise ValueError("source_id must use lowercase identifier characters")
        if self.source_role not in SOURCE_ROLES:
            raise ValueError("invalid source_role")
        if not isinstance(self.precedence, int) or isinstance(self.precedence, bool):
            raise ValueError("precedence must be an integer")
        if self.precedence < 0:
            raise ValueError("precedence must be nonnegative")


@dataclass(frozen=True)
class RawBatch:
    source_id: str
    requested_start: str
    requested_end: str
    retrieved_at: str
    records: tuple[Mapping[str, Any], ...]
    content_hash: str
    status: str
    http_status: int

    @classmethod
    def from_records(
        cls,
        spec: SourceSpec,
        records: Sequence[Mapping[str, Any]],
        requested_start: str,
        requested_end: str,
        retrieved_at: str,
        status: str = "success",
        http_status: int = 200,
    ) -> "RawBatch":
        start = dt.date.fromisoformat(requested_start)
        end = dt.date.fromisoformat(requested_end)
        if start > end:
            raise ValueError("requested_start must not follow requested_end")
        raw_records = list(records)
        if any(not isinstance(record, Mapping) for record in raw_records):
            raise ValueError("raw batch records must be objects")
        copied = tuple(dict(record) for record in raw_records)
        if not isinstance(http_status, int) or isinstance(http_status, bool):
            raise ValueError("http_status must be an integer")
        if not 100 <= http_status <= 599:
            raise ValueError("http_status must be between 100 and 599")
        return cls(
            source_id=spec.source_id,
            requested_start=start.isoformat(),
            requested_end=end.isoformat(),
            retrieved_at=_required_text(retrieved_at, "retrieved_at"),
            records=copied,
            content_hash=raw_content_hash(copied),
            status=_required_text(status, "status"),
            http_status=http_status,
        )


@dataclass(frozen=True)
class NormalizedObservation:
    observation_id: str
    run_id: str
    record: Mapping[str, Any]
    source_id: str
    source_url: str
    source_role: str
    dataset_semantics: str
    precedence: int
    adapter_version: str
    source_schema_version: str
    retrieved_at: str
    content_hash: str
    sequence: int
    eligible_for_aggregate: bool = False
    supersedes_source_record_id: str | None = None

    @property
    def source_record_id(self) -> str:
        return str(self.record["row_hash"])

    @property
    def observation_identity(self) -> tuple[str, str, str, str]:
        return (
            str(self.record["transaction_date"]),
            str(self.record["market_code"]),
            str(self.record["crop_code"]),
            self.dataset_semantics,
        )


@dataclass(frozen=True)
class Resolution:
    observations: tuple[NormalizedObservation, ...]
    policy_version: str = RESOLUTION_POLICY_VERSION

    @property
    def eligible_records(self) -> list[dict[str, Any]]:
        return [
            dict(observation.record)
            for observation in self.observations
            if observation.eligible_for_aggregate
        ]


@runtime_checkable
class SourceAdapter(Protocol):
    spec: SourceSpec

    def fetch(
        self,
        start: str,
        end: str,
        opener: Any | None = None,
    ) -> RawBatch:
        """Fetch a bounded source batch without persisting it."""

    def normalize(
        self,
        batch: RawBatch,
        mapping: Mapping[str, Mapping[str, Any]],
    ) -> list[NormalizedObservation]:
        """Normalize a batch while retaining its source evidence."""


def _run_id(spec: SourceSpec, batch: RawBatch) -> str:
    return _sha256(
        {
            "source_id": spec.source_id,
            "requested_start": batch.requested_start,
            "requested_end": batch.requested_end,
            "content_hash": batch.content_hash,
            "adapter_version": spec.adapter_version,
            "source_schema_version": spec.source_schema_version,
        }
    )


def observations_from_records(
    spec: SourceSpec,
    batch: RawBatch,
    records: Sequence[Mapping[str, Any]],
) -> list[NormalizedObservation]:
    """Attach uniform lineage to adapter-normalized transaction records."""

    if batch.source_id != spec.source_id:
        raise ValueError("raw batch source_id does not match adapter")
    if len(records) != len(batch.records):
        raise ValueError("adapter must account for every raw transaction record")
    run_id = _run_id(spec, batch)
    start = dt.date.fromisoformat(batch.requested_start)
    end = dt.date.fromisoformat(batch.requested_end)
    observations: list[NormalizedObservation] = []
    for sequence, raw_record in enumerate(records):
        record = dict(raw_record)
        required = ("transaction_date", "market_code", "crop_code", "row_hash")
        missing = [field for field in required if field not in record]
        if missing:
            raise ValueError("normalized record missing fields: " + ", ".join(missing))
        if record.get("source_id") != spec.source_id:
            raise ValueError("normalized record source_id does not match adapter")
        transaction_date = dt.date.fromisoformat(str(record["transaction_date"]))
        if not start <= transaction_date <= end:
            raise ValueError("upstream record outside requested date range")
        observation_id = _sha256(
            {
                "run_id": run_id,
                "source_record_id": record["row_hash"],
                "sequence": sequence,
            }
        )
        observations.append(
            NormalizedObservation(
                observation_id=observation_id,
                run_id=run_id,
                record=record,
                source_id=spec.source_id,
                source_url=spec.source_url,
                source_role=spec.source_role,
                dataset_semantics=spec.dataset_semantics,
                precedence=spec.precedence,
                adapter_version=spec.adapter_version,
                source_schema_version=spec.source_schema_version,
                retrieved_at=batch.retrieved_at,
                content_hash=batch.content_hash,
                sequence=sequence,
            )
        )
    return observations


def resolve_observations(
    observations: Sequence[NormalizedObservation],
) -> Resolution:
    """Select at most one authoritative record for each economic observation.

    Higher precedence wins across authoritative sources.  Equal-precedence
    authoritative sources are an unsafe ambiguity and fail closed.  Repeated
    records from one source retain the historical correction behavior: the last
    record in the supplied batch wins.  Every non-final role remains evidence
    only, even when no authoritative record is present.
    """

    indexed = list(enumerate(observations))
    groups: dict[tuple[str, str, str, str], list[tuple[int, NormalizedObservation]]] = {}
    for index, observation in indexed:
        if observation.source_role not in SOURCE_ROLES:
            raise ValueError("invalid source_role")
        groups.setdefault(observation.observation_identity, []).append(
            (index, observation)
        )
    output: list[NormalizedObservation | None] = [None] * len(indexed)
    for identity, group in groups.items():
        authoritative = [
            item for item in group if item[1].source_role == AGGREGATE_SOURCE_ROLE
        ]
        winner: tuple[int, NormalizedObservation] | None = None
        if authoritative:
            top_precedence = max(item[1].precedence for item in authoritative)
            top = [
                item
                for item in authoritative
                if item[1].precedence == top_precedence
            ]
            top_sources = {item[1].source_id for item in top}
            if len(top_sources) != 1:
                rendered = "|".join(identity)
                raise ValueError(
                    "ambiguous authoritative sources for observation " + rendered
                )
            winner = max(top, key=lambda item: item[0])
        for index, observation in group:
            output[index] = replace(
                observation,
                eligible_for_aggregate=winner is not None and index == winner[0],
            )
        if winner is not None:
            previous = [
                item
                for item in group
                if item[0] != winner[0]
                and (
                    item[1].source_role == "provisional"
                    or item[1].source_id == winner[1].source_id
                )
                and item[1].source_record_id != winner[1].source_record_id
            ]
            if previous:
                selected = output[winner[0]]
                assert selected is not None
                output[winner[0]] = replace(
                    selected,
                    supersedes_source_record_id=max(
                        previous, key=lambda item: item[0]
                    )[1].source_record_id,
                )
    if any(observation is None for observation in output):
        raise AssertionError("observation resolution was incomplete")
    return Resolution(tuple(observation for observation in output if observation))


def _identity_document(
    identity: tuple[str, str, str, str]
) -> dict[str, str]:
    transaction_date, market_code, crop_code, dataset_semantics = identity
    return {
        "transaction_date": transaction_date,
        "market_code": market_code,
        "crop_code": crop_code,
        "dataset_semantics": dataset_semantics,
    }


def source_run_document(
    source_batches: Sequence[tuple[SourceAdapter, RawBatch]],
    resolution: Resolution,
    requested_start: str,
    requested_end: str,
) -> dict[str, Any]:
    """Build compact run evidence plus only non-trivial resolution decisions."""

    run_counts: dict[str, dict[str, int]] = {}
    for observation in resolution.observations:
        counts = run_counts.setdefault(
            observation.run_id, {"normalized": 0, "eligible": 0}
        )
        counts["normalized"] += 1
        counts["eligible"] += int(observation.eligible_for_aggregate)
    runs = []
    run_ids = set()
    for adapter, batch in source_batches:
        if batch.source_id != adapter.spec.source_id:
            raise ValueError("raw batch source_id does not match adapter")
        run_id = _run_id(adapter.spec, batch)
        if run_id in run_ids:
            raise ValueError("duplicate source run")
        run_ids.add(run_id)
        counts = run_counts.get(run_id, {"normalized": 0, "eligible": 0})
        runs.append(
            {
                "run_id": run_id,
                "source_id": adapter.spec.source_id,
                "source_url": adapter.spec.source_url,
                "source_role": adapter.spec.source_role,
                "dataset_semantics": adapter.spec.dataset_semantics,
                "precedence": adapter.spec.precedence,
                "adapter_version": adapter.spec.adapter_version,
                "source_schema_version": adapter.spec.source_schema_version,
                "retrieved_at": batch.retrieved_at,
                "content_hash": batch.content_hash,
                "status": batch.status,
                "http_status": batch.http_status,
                "raw_record_count": len(batch.records),
                "normalized_record_count": counts["normalized"],
                "eligible_for_aggregate_count": counts["eligible"],
                "suppressed_observation_count": counts["normalized"]
                - counts["eligible"],
            }
        )
    groups: dict[
        tuple[str, str, str, str], list[NormalizedObservation]
    ] = {}
    for observation in resolution.observations:
        groups.setdefault(observation.observation_identity, []).append(observation)
    decisions = []
    for identity, group in sorted(groups.items()):
        selected = next(
            (
                observation
                for observation in group
                if observation.eligible_for_aggregate
            ),
            None,
        )
        if len(group) == 1 and selected is not None:
            continue
        decisions.append(
            {
                "observation_identity": _identity_document(identity),
                "selected_observation_id": (
                    selected.observation_id if selected else None
                ),
                "candidates": [
                    {
                        "observation_id": observation.observation_id,
                        "source_record_id": observation.source_record_id,
                        "source_id": observation.source_id,
                        "source_role": observation.source_role,
                        "precedence": observation.precedence,
                        "eligible_for_aggregate": observation.eligible_for_aggregate,
                        "supersedes_source_record_id": observation.supersedes_source_record_id,
                    }
                    for observation in group
                ],
            }
        )
    document = {
        "schema_version": "1.0",
        "policy_version": resolution.policy_version,
        "requested_start": dt.date.fromisoformat(requested_start).isoformat(),
        "requested_end": dt.date.fromisoformat(requested_end).isoformat(),
        "runs": sorted(runs, key=lambda run: (run["source_id"], run["run_id"])),
        "resolution_summary": {
            "observation_count": len(resolution.observations),
            "eligible_for_aggregate_count": sum(
                observation.eligible_for_aggregate
                for observation in resolution.observations
            ),
            "suppressed_observation_count": sum(
                not observation.eligible_for_aggregate
                for observation in resolution.observations
            ),
            "decision_count": len(decisions),
        },
        "decisions": decisions,
    }
    return validate_source_run_document(document)


def validate_source_run_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Runtime validation mirroring schema/source-run.schema.json."""

    if not isinstance(document, Mapping):
        raise ValueError("source run document must be an object")
    required = {
        "schema_version",
        "policy_version",
        "requested_start",
        "requested_end",
        "runs",
        "resolution_summary",
        "decisions",
    }
    if set(document) != required:
        raise ValueError("source run document fields do not match schema")
    if document["schema_version"] != "1.0":
        raise ValueError("unsupported source run schema_version")
    if document["policy_version"] != RESOLUTION_POLICY_VERSION:
        raise ValueError("unsupported source resolution policy")
    start = dt.date.fromisoformat(str(document["requested_start"]))
    end = dt.date.fromisoformat(str(document["requested_end"]))
    if start > end:
        raise ValueError("source run requested range is invalid")
    runs = document["runs"]
    decisions = document["decisions"]
    summary = document["resolution_summary"]
    if not isinstance(runs, list) or not runs:
        raise ValueError("source run document requires at least one run")
    if not isinstance(decisions, list) or not isinstance(summary, Mapping):
        raise ValueError("invalid source resolution document")
    summary_fields = {
        "observation_count",
        "eligible_for_aggregate_count",
        "suppressed_observation_count",
        "decision_count",
    }
    if set(summary) != summary_fields or any(
        not isinstance(summary.get(field), int)
        or isinstance(summary.get(field), bool)
        or summary[field] < 0
        for field in summary_fields
    ):
        raise ValueError("invalid source resolution summary")
    run_fields = {
        "run_id",
        "source_id",
        "source_url",
        "source_role",
        "dataset_semantics",
        "precedence",
        "adapter_version",
        "source_schema_version",
        "retrieved_at",
        "content_hash",
        "status",
        "http_status",
        "raw_record_count",
        "normalized_record_count",
        "eligible_for_aggregate_count",
        "suppressed_observation_count",
    }
    seen_run_ids = set()
    run_source_ids = set()
    for run in runs:
        if not isinstance(run, Mapping) or set(run) != run_fields:
            raise ValueError("source run fields do not match schema")
        if not _HASH.fullmatch(str(run["run_id"])) or run["run_id"] in seen_run_ids:
            raise ValueError("invalid or duplicate source run_id")
        seen_run_ids.add(run["run_id"])
        if not _ID.fullmatch(str(run["source_id"])):
            raise ValueError("invalid source run source_id")
        run_source_ids.add(run["source_id"])
        if run.get("source_role") not in SOURCE_ROLES:
            raise ValueError("invalid source run role")
        for field in (
            "source_url",
            "dataset_semantics",
            "adapter_version",
            "source_schema_version",
            "retrieved_at",
            "status",
        ):
            _required_text(run.get(field), field)
        if not _HASH.fullmatch(str(run["content_hash"])):
            raise ValueError("invalid source run content_hash")
        if (
            not isinstance(run["precedence"], int)
            or isinstance(run["precedence"], bool)
            or run["precedence"] < 0
        ):
            raise ValueError("invalid source run precedence")
        if (
            not isinstance(run["http_status"], int)
            or isinstance(run["http_status"], bool)
            or not 100 <= run["http_status"] <= 599
        ):
            raise ValueError("invalid source run http_status")
        for field in (
            "raw_record_count",
            "normalized_record_count",
            "eligible_for_aggregate_count",
            "suppressed_observation_count",
        ):
            if (
                not isinstance(run.get(field), int)
                or isinstance(run.get(field), bool)
                or run[field] < 0
            ):
                raise ValueError("invalid source run count")
        if run["normalized_record_count"] != run["raw_record_count"]:
            raise ValueError("source adapter did not account for every raw record")
        if (
            run["eligible_for_aggregate_count"]
            + run["suppressed_observation_count"]
            != run["normalized_record_count"]
        ):
            raise ValueError("source run counts do not reconcile")
        if (
            run["source_role"] != AGGREGATE_SOURCE_ROLE
            and run["eligible_for_aggregate_count"]
        ):
            raise ValueError("non-final source cannot be aggregate eligible")
    expected_summary = {
        "observation_count": sum(run["normalized_record_count"] for run in runs),
        "eligible_for_aggregate_count": sum(
            run["eligible_for_aggregate_count"] for run in runs
        ),
        "suppressed_observation_count": sum(
            run["suppressed_observation_count"] for run in runs
        ),
        "decision_count": len(decisions),
    }
    if dict(summary) != expected_summary:
        raise ValueError("source resolution summary does not reconcile")
    decision_fields = {
        "observation_identity",
        "selected_observation_id",
        "candidates",
    }
    identity_fields = {
        "transaction_date",
        "market_code",
        "crop_code",
        "dataset_semantics",
    }
    candidate_fields = {
        "observation_id",
        "source_record_id",
        "source_id",
        "source_role",
        "precedence",
        "eligible_for_aggregate",
        "supersedes_source_record_id",
    }
    seen_identities = set()
    seen_observation_ids = set()
    for decision in decisions:
        if not isinstance(decision, Mapping) or set(decision) != decision_fields:
            raise ValueError("source resolution decision fields do not match schema")
        identity = decision["observation_identity"]
        if not isinstance(identity, Mapping) or set(identity) != identity_fields:
            raise ValueError("invalid economic observation identity")
        identity_key = (
            dt.date.fromisoformat(str(identity["transaction_date"])).isoformat(),
            _required_text(identity["market_code"], "market_code"),
            _required_text(identity["crop_code"], "crop_code"),
            _required_text(identity["dataset_semantics"], "dataset_semantics"),
        )
        if identity_key in seen_identities:
            raise ValueError("duplicate economic observation decision")
        seen_identities.add(identity_key)
        candidates = decision.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("source resolution decision requires candidates")
        for candidate in candidates:
            if not isinstance(candidate, Mapping) or set(candidate) != candidate_fields:
                raise ValueError("source resolution candidate fields do not match schema")
            for field in ("observation_id", "source_record_id"):
                if not _HASH.fullmatch(str(candidate[field])):
                    raise ValueError("invalid source resolution candidate hash")
            if candidate["observation_id"] in seen_observation_ids:
                raise ValueError("duplicate source observation_id")
            seen_observation_ids.add(candidate["observation_id"])
            if candidate["source_id"] not in run_source_ids:
                raise ValueError("source resolution candidate has no source run")
            if candidate["source_role"] not in SOURCE_ROLES:
                raise ValueError("invalid source resolution candidate role")
            if (
                not isinstance(candidate["precedence"], int)
                or isinstance(candidate["precedence"], bool)
                or candidate["precedence"] < 0
            ):
                raise ValueError("invalid source resolution candidate precedence")
            if not isinstance(candidate["eligible_for_aggregate"], bool):
                raise ValueError("invalid source resolution eligibility")
            supersedes = candidate["supersedes_source_record_id"]
            if supersedes is not None and not _HASH.fullmatch(str(supersedes)):
                raise ValueError("invalid supersedes_source_record_id")
            if (
                candidate["eligible_for_aggregate"]
                and candidate["source_role"] != AGGREGATE_SOURCE_ROLE
            ):
                raise ValueError("non-final candidate cannot be aggregate eligible")
        eligible = [
            candidate
            for candidate in candidates
            if candidate.get("eligible_for_aggregate") is True
        ]
        if len(eligible) > 1:
            raise ValueError("economic observation has multiple eligible records")
        selected = decision.get("selected_observation_id")
        if selected is not None and not _HASH.fullmatch(str(selected)):
            raise ValueError("invalid selected_observation_id")
        if (eligible[0]["observation_id"] if eligible else None) != selected:
            raise ValueError("selected observation does not match eligibility")
    return dict(document)


class MoaMarket8066Adapter:
    spec = SourceSpec(
        source_id="moa_market_8066",
        source_url=MOA_MARKET_URL,
        source_role="authoritative_final",
        dataset_semantics=TRANSACTION_SEMANTICS,
        precedence=100,
        adapter_version="1.0",
        source_schema_version="moa-8066-v1",
    )

    @staticmethod
    def _roc(iso_date: str) -> str:
        value = dt.date.fromisoformat(iso_date)
        return "%03d.%02d.%02d" % (value.year - 1911, value.month, value.day)

    def batch(
        self,
        records: Sequence[Mapping[str, Any]],
        start: str,
        end: str,
        retrieved_at: str,
        status: str | None = None,
        http_status: int = 200,
    ) -> RawBatch:
        return RawBatch.from_records(
            self.spec,
            records,
            start,
            end,
            retrieved_at,
            status=status or ("fixture" if retrieved_at == "fixture" else "success"),
            http_status=http_status,
        )

    def fetch(
        self,
        start: str,
        end: str,
        opener: Any | None = None,
    ) -> RawBatch:
        kwargs = {"opener": opener} if opener is not None else {}
        records = fetch_moa_market(self._roc(start), self._roc(end), **kwargs)
        return self.batch(
            records,
            start,
            end,
            dt.datetime.now(dt.UTC).isoformat(),
            status="success",
        )

    def normalize(
        self,
        batch: RawBatch,
        mapping: Mapping[str, Mapping[str, Any]],
    ) -> list[NormalizedObservation]:
        records = [
            normalize(
                record,
                mapping,
                fetched_at=batch.retrieved_at,
                source_id=self.spec.source_id,
            )
            for record in batch.records
        ]
        return observations_from_records(self.spec, batch, records)


MOA_MARKET_8066_ADAPTER = MoaMarket8066Adapter()
