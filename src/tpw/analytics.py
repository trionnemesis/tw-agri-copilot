import datetime as dt
import statistics


WINDOWS = {
    "7d": (7, 3),
    "30d": (30, 10),
    "90d": (90, 30),
}


def aggregate(rows):
    groups = {}
    for row in rows:
        if not row["canonical_id"]:
            continue
        groups.setdefault((row["transaction_date"], row["canonical_id"]), []).append(row)
    output = []
    for (date, item), group in sorted(groups.items()):
        valid = [
            row
            for row in group
            if row["avg_price_twd_per_kg"] > 0 and row["volume_kg"] > 0
        ]
        prices = [row["avg_price_twd_per_kg"] for row in valid]
        volume = sum(row["volume_kg"] for row in valid)
        output.append(
            {
                "transaction_date": date,
                "canonical_id": item,
                "weighted_avg_price_twd_per_kg": (
                    sum(
                        row["avg_price_twd_per_kg"] * row["volume_kg"]
                        for row in valid
                    )
                    / volume
                    if volume
                    else None
                ),
                "total_volume_kg": volume,
                "market_count": len({row["market_code"] for row in valid}),
                "market_median_price_twd_per_kg": (
                    statistics.median(prices) if prices else None
                ),
                "min_market_price_twd_per_kg": min(prices) if prices else None,
                "max_market_price_twd_per_kg": max(prices) if prices else None,
                "valid_row_count": len(valid),
                "excluded_row_count": len(group) - len(valid),
                "quality_warnings": (
                    []
                    if len(valid) == len(group)
                    else ["zero-price-or-volume-excluded"]
                ),
            }
        )
    return output


def change_pct(current, reference):
    if current is None or reference in (None, 0):
        return None
    return (current - reference) / reference * 100


def _round(value):
    return round(value, 6) if value is not None else None


def _window(rows, as_of, days, minimum_days):
    start = as_of - dt.timedelta(days=days - 1)
    selected = [
        row
        for row in rows
        if start <= dt.date.fromisoformat(row["transaction_date"]) <= as_of
        and row["weighted_avg_price_twd_per_kg"] is not None
        and row["total_volume_kg"] > 0
    ]
    total_volume = sum(row["total_volume_kg"] for row in selected)
    price = (
        sum(
            row["weighted_avg_price_twd_per_kg"] * row["total_volume_kg"]
            for row in selected
        )
        / total_volume
        if total_volume
        else None
    )
    coverage_days = len({row["transaction_date"] for row in selected})
    return {
        "price_twd_per_kg": _round(price),
        "total_volume_kg": _round(total_volume),
        "avg_daily_volume_kg": _round(
            total_volume / coverage_days if coverage_days else None
        ),
        "coverage_days": coverage_days,
        "minimum_days": minimum_days,
        "status": "valid" if coverage_days >= minimum_days else "insufficient",
    }


def _range_stats(rows, as_of, days, minimum_days):
    start = as_of - dt.timedelta(days=days - 1)
    selected = [
        row
        for row in rows
        if start <= dt.date.fromisoformat(row["transaction_date"]) <= as_of
        and row["weighted_avg_price_twd_per_kg"] is not None
        and row["total_volume_kg"] > 0
    ]
    observed_days = len({row["transaction_date"] for row in selected})
    if not selected:
        return {
            "observed_days": 0,
            "minimum_days": minimum_days,
            "min_price_twd_per_kg": None,
            "min_date": None,
            "max_price_twd_per_kg": None,
            "max_date": None,
            "status": "insufficient",
        }
    min_price = min(row["weighted_avg_price_twd_per_kg"] for row in selected)
    max_price = max(row["weighted_avg_price_twd_per_kg"] for row in selected)
    return {
        "observed_days": observed_days,
        "minimum_days": minimum_days,
        "min_price_twd_per_kg": _round(min_price),
        "min_date": min(
            row["transaction_date"]
            for row in selected
            if row["weighted_avg_price_twd_per_kg"] == min_price
        ),
        "max_price_twd_per_kg": _round(max_price),
        "max_date": min(
            row["transaction_date"]
            for row in selected
            if row["weighted_avg_price_twd_per_kg"] == max_price
        ),
        "status": "valid" if observed_days >= minimum_days else "insufficient",
    }


def build_series(daily_aggregates, as_of_date):
    as_of = dt.date.fromisoformat(as_of_date)
    groups = {}
    for row in daily_aggregates:
        if row.get("canonical_id"):
            groups.setdefault(row["canonical_id"], []).append(row)
    output = []
    for canonical_id, raw_rows in sorted(groups.items()):
        rows = sorted(
            (
                row
                for row in raw_rows
                if dt.date.fromisoformat(row["transaction_date"]) <= as_of
            ),
            key=lambda row: row["transaction_date"],
        )
        today = next(
            (row for row in reversed(rows) if row["transaction_date"] == as_of_date),
            None,
        )
        if today is None:
            continue
        previous = next(
            (
                row
                for row in reversed(rows)
                if row["transaction_date"] < as_of_date
                and row["weighted_avg_price_twd_per_kg"] is not None
                and row["total_volume_kg"] > 0
            ),
            None,
        )
        windows = {
            name: _window(rows, as_of, days, minimum)
            for name, (days, minimum) in WINDOWS.items()
        }
        range_stats = {
            name: _range_stats(rows, as_of, days, minimum)
            for name, (days, minimum) in WINDOWS.items()
        }
        today_price = today["weighted_avg_price_twd_per_kg"]
        today_volume = today["total_volume_kg"]
        for window in windows.values():
            window["today_change_pct"] = _round(
                change_pct(today_price, window["price_twd_per_kg"])
            )
            window["today_volume_change_pct"] = _round(
                change_pct(today_volume, window["avg_daily_volume_kg"])
            )
        seven_start = as_of - dt.timedelta(days=6)
        seven_prices = [
            row["weighted_avg_price_twd_per_kg"]
            for row in rows
            if seven_start <= dt.date.fromisoformat(row["transaction_date"]) <= as_of
            and row["weighted_avg_price_twd_per_kg"] is not None
        ]
        volatility = (
            statistics.pstdev(seven_prices) / statistics.mean(seven_prices)
            if len(seven_prices) >= 3 and statistics.mean(seven_prices)
            else None
        )
        output.append(
            {
                "canonical_id": canonical_id,
                "as_of_date": as_of_date,
                "today": {
                    "price_twd_per_kg": _round(today_price),
                    "volume_kg": _round(today_volume),
                    "market_count": today["market_count"],
                    "quality_warnings": today.get("quality_warnings", []),
                },
                "previous_trading_day": {
                    "date": previous["transaction_date"] if previous else None,
                    "price_twd_per_kg": (
                        _round(previous["weighted_avg_price_twd_per_kg"])
                        if previous
                        else None
                    ),
                    "change_pct": _round(
                        change_pct(
                            today_price,
                            previous["weighted_avg_price_twd_per_kg"]
                            if previous
                            else None,
                        )
                    ),
                    "status": "valid" if previous else "insufficient",
                },
                "windows": windows,
                "range_stats": range_stats,
                "volatility_7d_cv": _round(volatility),
                "volatility_7d_status": (
                    "valid" if len(seven_prices) >= 3 else "insufficient"
                ),
                "daily": [
                    {
                        "date": row["transaction_date"],
                        "price_twd_per_kg": _round(
                            row["weighted_avg_price_twd_per_kg"]
                        ),
                        "volume_kg": _round(row["total_volume_kg"]),
                    }
                    for row in rows[-120:]
                ],
            }
        )
    return output
