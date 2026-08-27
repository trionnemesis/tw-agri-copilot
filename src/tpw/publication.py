"""Market-day publication status used by the static site and workflow."""

import datetime as dt
import json
import pathlib


MARKET_STATES = {
    "complete",
    "market_closed",
    "incomplete",
    "pending",
    "source_unavailable",
}


def _date(value, field):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def validate_market_status(status):
    if not isinstance(status, dict):
        raise ValueError("market status must be an object")
    required = {
        "schema_version",
        "requested_date",
        "status",
        "source_status",
        "expected_watchlist_count",
        "covered_watchlist_count",
        "observed_record_count",
    }
    missing = sorted(required - status.keys())
    if missing:
        raise ValueError("market status missing fields: " + ", ".join(missing))
    if status["schema_version"] != "1.0":
        raise ValueError("market status schema_version must be 1.0")
    requested = _date(status["requested_date"], "requested_date")
    if status["status"] not in MARKET_STATES:
        raise ValueError("invalid market status")
    if not isinstance(status["source_status"], str) or not status["source_status"]:
        raise ValueError("source_status must be a non-empty string")
    for field in (
        "expected_watchlist_count",
        "covered_watchlist_count",
        "observed_record_count",
    ):
        if not isinstance(status[field], int) or status[field] < 0:
            raise ValueError(field + " must be a nonnegative integer")
    if status["covered_watchlist_count"] > status["expected_watchlist_count"]:
        raise ValueError("covered watchlist count exceeds expected count")
    resolved_value = status.get("resolved_date")
    if resolved_value is not None:
        resolved = _date(resolved_value, "resolved_date")
        if resolved > requested:
            raise ValueError("resolved_date cannot be after requested_date")
    return status


def classify_market_status(
    observed_rows,
    stored_rows,
    requested_date,
    expected_ids,
    source_status,
):
    requested = _date(requested_date, "requested_date").isoformat()
    expected = set(expected_ids)
    observed = [
        row for row in observed_rows if row.get("transaction_date") == requested
    ]
    covered = {
        row.get("canonical_id")
        for row in stored_rows
        if row.get("transaction_date") == requested and row.get("canonical_id")
    }
    closed = bool(observed) and all(
        str(row.get("crop_code", "")).strip().lower() == "rest"
        and str(row.get("crop_name_raw", "")).strip() == "休市"
        for row in observed
    )
    if expected and covered == expected:
        state = "complete"
    elif closed:
        state = "market_closed"
    elif observed:
        state = "incomplete"
    else:
        state = "pending"
    return validate_market_status(
        {
            "schema_version": "1.0",
            "requested_date": requested,
            "status": state,
            "source_status": source_status,
            "expected_watchlist_count": len(expected),
            "covered_watchlist_count": len(covered & expected),
            "observed_record_count": len(observed),
        }
    )


def source_unavailable_status(requested_date, expected_count):
    requested = _date(requested_date, "requested_date").isoformat()
    return validate_market_status(
        {
            "schema_version": "1.0",
            "requested_date": requested,
            "status": "source_unavailable",
            "source_status": "unavailable",
            "expected_watchlist_count": expected_count,
            "covered_watchlist_count": 0,
            "observed_record_count": 0,
        }
    )


def load_resolved_market_status(data_root, resolved_date, source_status, expected_count):
    data_root = pathlib.Path(data_root)
    resolved = _date(resolved_date, "resolved_date")
    path = data_root / "market-status/current.json"
    if path.exists():
        status = validate_market_status(
            json.loads(path.read_text(encoding="utf-8"))
        ).copy()
        requested = _date(status["requested_date"], "requested_date")
        if requested >= resolved:
            if status["status"] == "complete" and requested != resolved:
                raise ValueError("complete market status must resolve to its requested date")
            status["resolved_date"] = resolved.isoformat()
            return validate_market_status(status)
    return validate_market_status(
        {
            "schema_version": "1.0",
            "requested_date": resolved.isoformat(),
            "resolved_date": resolved.isoformat(),
            "status": "complete",
            "source_status": source_status,
            "expected_watchlist_count": expected_count,
            "covered_watchlist_count": expected_count,
            "observed_record_count": 0,
        }
    )
