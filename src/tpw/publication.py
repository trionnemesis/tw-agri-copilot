"""Market-day publication status used by the static site and workflow."""

import datetime as dt
import json
import pathlib

from .market_calendar import validate_calendar_evaluation


MARKET_STATES = {
    "complete",
    "market_closed",
    "incomplete",
    "pending",
    "source_unavailable",
    "calendar_feed_discrepancy",
}

FEED_STATES = {"available", "empty", "delayed", "failed", "not_checked"}


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
    feed_status = status.get("feed_status")
    if feed_status is not None and feed_status not in FEED_STATES:
        raise ValueError("invalid feed_status")
    calendar_feed_status = status.get("calendar_feed_status")
    if calendar_feed_status is not None and calendar_feed_status not in FEED_STATES:
        raise ValueError("invalid calendar_feed_status")
    calendar = status.get("calendar")
    if calendar is not None:
        validate_calendar_evaluation(calendar, requested.isoformat())
    return status


def _inferred_feed_status(status):
    if status.get("feed_status") in FEED_STATES:
        return status["feed_status"]
    if status["status"] in ("complete", "incomplete", "calendar_feed_discrepancy"):
        return "available"
    if status["status"] == "source_unavailable":
        return "failed"
    return "empty"


def apply_market_calendar(status, calendar, calendar_feed_status=None):
    """Keep feed evidence separate and apply the calendar/feed decision matrix."""

    status = validate_market_status(status).copy()
    calendar = validate_calendar_evaluation(calendar, status["requested_date"])
    feed_status = _inferred_feed_status(status)
    if calendar_feed_status is None:
        calendar_feed_status = status.get("calendar_feed_status")
    if calendar_feed_status is None:
        if status["status"] == "market_closed":
            calendar_feed_status = "empty"
        elif status["status"] == "source_unavailable":
            calendar_feed_status = "failed"
        else:
            calendar_feed_status = "not_checked"
    if calendar_feed_status not in FEED_STATES:
        raise ValueError("invalid calendar_feed_status")
    state = status["status"]
    schedule_status = calendar["schedule_status"]
    if schedule_status == "scheduled_closed":
        if calendar_feed_status == "available":
            state = "calendar_feed_discrepancy"
        elif state in ("market_closed", "pending", "source_unavailable"):
            state = "market_closed"
    elif schedule_status in ("expected_open", "exceptional_open"):
        if feed_status == "failed":
            state = "source_unavailable"
        elif state == "market_closed" or feed_status in ("empty", "delayed", "not_checked"):
            state = "pending"
    status["status"] = state
    status["feed_status"] = feed_status
    status["calendar_feed_status"] = calendar_feed_status
    status["calendar"] = calendar
    return validate_market_status(status)


def classify_market_status(
    observed_rows,
    stored_rows,
    requested_date,
    expected_ids,
    source_status,
    calendar=None,
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
    feed_status = "empty" if closed or not observed else "available"
    if expected and covered == expected:
        state = "complete"
    elif closed:
        state = "market_closed"
    elif observed:
        state = "incomplete"
    else:
        state = "pending"
    calendar_feed_status = None
    if calendar is not None:
        calendar_market_codes = {
            market["market_code"] for market in calendar.get("markets", [])
        }
        calendar_rows = [
            row for row in observed if str(row.get("market_code")) in calendar_market_codes
        ]
        calendar_trade_rows = [
            row
            for row in calendar_rows
            if not (
                str(row.get("crop_code", "")).strip().lower() == "rest"
                and str(row.get("crop_name_raw", "")).strip() == "休市"
            )
        ]
        calendar_feed_status = "available" if calendar_trade_rows else "empty"
    status = validate_market_status(
        {
            "schema_version": "1.0",
            "requested_date": requested,
            "status": state,
            "source_status": source_status,
            "feed_status": feed_status,
            "expected_watchlist_count": len(expected),
            "covered_watchlist_count": len(covered & expected),
            "observed_record_count": len(observed),
        }
    )
    return apply_market_calendar(status, calendar, calendar_feed_status) if calendar else status


def source_unavailable_status(requested_date, expected_count, calendar=None):
    requested = _date(requested_date, "requested_date").isoformat()
    status = validate_market_status(
        {
            "schema_version": "1.0",
            "requested_date": requested,
            "status": "source_unavailable",
            "source_status": "unavailable",
            "feed_status": "failed",
            "expected_watchlist_count": expected_count,
            "covered_watchlist_count": 0,
            "observed_record_count": 0,
        }
    )
    return apply_market_calendar(status, calendar, "failed") if calendar else status


def load_resolved_market_status(
    data_root,
    resolved_date,
    source_status,
    expected_count,
    calendar=None,
):
    data_root = pathlib.Path(data_root)
    resolved = _date(resolved_date, "resolved_date")
    path = data_root / "market-status/current.json"
    if path.exists():
        status = validate_market_status(
            json.loads(path.read_text(encoding="utf-8"))
        ).copy()
        requested = _date(status["requested_date"], "requested_date")
        if requested >= resolved:
            if calendar is not None:
                status = apply_market_calendar(status, calendar)
            if status["status"] == "complete" and requested != resolved:
                raise ValueError("complete market status must resolve to its requested date")
            status["resolved_date"] = resolved.isoformat()
            return validate_market_status(status)
    status = validate_market_status(
        {
            "schema_version": "1.0",
            "requested_date": resolved.isoformat(),
            "resolved_date": resolved.isoformat(),
            "status": "complete",
            "source_status": source_status,
            "feed_status": "available",
            "expected_watchlist_count": expected_count,
            "covered_watchlist_count": expected_count,
            "observed_record_count": 0,
        }
    )
    return apply_market_calendar(status, calendar) if calendar else status
