"""Publish observed prices independently of the complete-watchlist score baseline.

This descriptive snapshot never fills a missing crop from another date, infers a
market closure, or supplies inputs to Buy Score. Normalized 8066 observations are
aggregated with the existing nationwide weighting rules.
"""

import datetime as dt
import math

from .analytics import aggregate, market_rows_for_analysis


def build_latest_market(rows, configured, requested_date, complete_reference_date, *, include_fixtures=False):
    requested = dt.date.fromisoformat(requested_date)
    reference = dt.date.fromisoformat(complete_reference_date)
    if reference > requested:
        raise ValueError("latest market reference cannot be after requested date")
    expected = {item["canonical_id"] for item in configured}
    if not expected or len(expected) != len(configured):
        raise ValueError("latest market requires a unique configured watchlist")
    # Historical 8066 rows predate source_role/dataset_semantics. They retain the
    # known source ID; explicit contradictory roles/semantics are never accepted.
    eligible = [row for row in market_rows_for_analysis(rows, include_fixtures=include_fixtures)
                if row.get("source_id") == "moa_market_8066"
                and row.get("source_role", "authoritative_final") == "authoritative_final"
                and row.get("dataset_semantics", "wholesale_market_daily_transaction") == "wholesale_market_daily_transaction"
                and row.get("canonical_id") in expected
                and dt.date.fromisoformat(row["transaction_date"]) <= requested]
    latest = max((row["transaction_date"] for row in eligible), default=None)
    selected = [row for row in eligible if row["transaction_date"] == latest]
    aggregates = {row["canonical_id"]: row for row in aggregate(selected, include_fixtures=include_fixtures)}
    items = []
    for item in configured:
        observed = aggregates.get(item["canonical_id"])
        valid = observed is not None and observed["weighted_avg_price_twd_per_kg"] is not None
        items.append({
            "canonical_id": item["canonical_id"],
            "display_name": item["display_name"],
            "category": item["category"],
            "observation_status": "observed" if valid else "no_valid_trade" if observed else "missing",
            "price_twd_per_kg": observed["weighted_avg_price_twd_per_kg"] if valid else None,
            "volume_kg": observed["total_volume_kg"] if valid else None,
            "market_count": observed["market_count"] if valid else None,
            "quality_warnings": observed["quality_warnings"] if observed else [],
        })
    return validate_latest_market({
        "schema_version": "1.0",
        "requested_date": requested_date,
        "as_of_date": latest,
        "complete_reference_date": complete_reference_date,
        "source_id": "moa_market_8066",
        "source_status": "fixture" if include_fixtures else "observed",
        "affects_buy_score": False,
        "expected_watchlist_count": len(configured),
        "covered_watchlist_count": len(aggregates),
        "valid_watchlist_count": sum(item["observation_status"] == "observed" for item in items),
        "items": items,
    })


def validate_latest_market(payload):
    def require(condition, message):
        if not condition:
            raise ValueError("latest market " + message)

    require(isinstance(payload, dict), "must be an object")
    require(payload.get("schema_version") == "1.0", "schema version is invalid")
    requested = dt.date.fromisoformat(payload["requested_date"])
    reference = dt.date.fromisoformat(payload["complete_reference_date"])
    require(reference <= requested, "reference is after requested date")
    latest = payload["as_of_date"]
    require(latest is None or dt.date.fromisoformat(latest) <= requested, "date is after requested date")
    require(payload.get("source_id") == "moa_market_8066", "source is invalid")
    require(payload.get("source_status") in ("observed", "fixture"), "source status is invalid")
    require(payload.get("affects_buy_score") is False, "cannot affect Buy Score")
    items = payload["items"]
    require(isinstance(items, list) and bool(items), "watchlist is empty")
    require(len({item["canonical_id"] for item in items}) == len(items), "has duplicate crops")
    for item in items:
        require(item["observation_status"] in ("observed", "missing", "no_valid_trade"), "observation status is invalid")
        values = [item[key] for key in ("price_twd_per_kg", "volume_kg", "market_count")]
        if item["observation_status"] == "observed":
            require(latest is not None, "observed crop has no date")
            require(all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 for value in values), "observed values must be finite and positive")
            require(isinstance(item["market_count"], int), "market count must be an integer")
        else:
            require(all(value is None for value in values), "missing/invalid crop cannot contain prices or zero-filled volume")
        require(latest is not None or item["observation_status"] == "missing", "undated crop must be missing")
    counts = {
        "expected_watchlist_count": len(items),
        "covered_watchlist_count": sum(item["observation_status"] != "missing" for item in items),
        "valid_watchlist_count": sum(item["observation_status"] == "observed" for item in items),
    }
    for name, value in counts.items():
        require(type(payload.get(name)) is int and payload[name] == value, name + " is inconsistent")
    return payload
