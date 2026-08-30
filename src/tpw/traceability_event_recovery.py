import argparse
import datetime as dt
import json

from .cli import _load_current_traceability_events, _persist_traceability_event_snapshot
from .traceability_events import validate_market_event_snapshot


ZERO_MAPPED_REASON = "no_explicitly_mapped_records"


def preserve_same_date_h44_as_stale(requested_date, attempted_at=None):
    requested_date = dt.date.fromisoformat(requested_date).isoformat()
    attempted_at = attempted_at or (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    current = _load_current_traceability_events()
    if current is None or current[1].get("requested_date") != requested_date:
        preserved_status = current[1].get("source_status", "none") if current else "none"
        return {
            "source_status": "unavailable",
            "preserved_status": preserved_status,
            "requested_date": requested_date,
            "last_attempt_at": attempted_at,
            "last_attempt_reason": ZERO_MAPPED_REASON,
        }

    rows, profile = current
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
    _persist_traceability_event_snapshot(stale_rows, stale_profile)
    return stale_profile


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    result = preserve_same_date_h44_as_stale(args.as_of)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
