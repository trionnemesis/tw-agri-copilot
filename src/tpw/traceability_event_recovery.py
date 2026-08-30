import argparse
import datetime as dt
import json
import pathlib
import shutil
import tempfile

from .cli import (
    _load_current_traceability_events,
    _persist_traceability_event_snapshot,
    _traceability_event_snapshot_paths,
    swap,
    write_json,
)
from .traceability_events import validate_market_event_snapshot


ZERO_MAPPED_REASON = "no_explicitly_mapped_records"


def _load_requested_h44_snapshot(requested_date):
    rows_path, profile_path = _traceability_event_snapshot_paths(requested_date)
    if rows_path.exists() and profile_path.exists():
        rows = json.loads(rows_path.read_text())
        profile = json.loads(profile_path.read_text())
        validate_market_event_snapshot(rows, profile)
        if profile.get("requested_date") != requested_date:
            raise ValueError(
                "date-scoped traceability market event profile does not match requested date"
            )
        return rows, profile

    current = _load_current_traceability_events()
    if current is not None and current[1].get("requested_date") == requested_date:
        return current
    return None


def _persist_requested_h44_archive(rows, profile):
    requested_date = profile["requested_date"]
    rows_path, profile_path = _traceability_event_snapshot_paths(requested_date)
    data_root = rows_path.parents[5]
    stage = pathlib.Path(
        tempfile.mkdtemp(prefix="tpw-traceability-events-archive-", dir=data_root.parent)
    )
    staged_data = stage / "data"
    try:
        if data_root.exists():
            shutil.copytree(data_root, staged_data)
        else:
            staged_data.mkdir()
        write_json(staged_data / rows_path.relative_to(data_root), rows)
        write_json(staged_data / profile_path.relative_to(data_root), profile)
        swap(staged_data, data_root)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def preserve_same_date_h44_as_stale(requested_date, attempted_at=None):
    requested_date = dt.date.fromisoformat(requested_date).isoformat()
    attempted_at = attempted_at or (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    snapshot = _load_requested_h44_snapshot(requested_date)
    if snapshot is None:
        current = _load_current_traceability_events()
        preserved_status = current[1].get("source_status", "none") if current else "none"
        return {
            "source_status": "unavailable",
            "preserved_status": preserved_status,
            "requested_date": requested_date,
            "last_attempt_at": attempted_at,
            "last_attempt_reason": ZERO_MAPPED_REASON,
        }

    rows, profile = snapshot
    if profile.get("source_status") not in ("live", "stale"):
        return {
            "source_status": "unavailable",
            "preserved_status": profile.get("source_status", "none"),
            "requested_date": requested_date,
            "last_attempt_at": attempted_at,
            "last_attempt_reason": ZERO_MAPPED_REASON,
        }

    stale_rows = [dict(row, source_status="stale") for row in rows]
    stale_profile = dict(
        profile,
        source_status="stale",
        last_attempt_at=attempted_at,
        last_attempt_reason=ZERO_MAPPED_REASON,
    )
    validate_market_event_snapshot(stale_rows, stale_profile)

    current = _load_current_traceability_events()
    if current is not None and current[1].get("requested_date") == requested_date:
        _persist_traceability_event_snapshot(stale_rows, stale_profile)
    else:
        _persist_requested_h44_archive(stale_rows, stale_profile)
    return stale_profile


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    result = preserve_same_date_h44_as_stale(args.as_of)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
