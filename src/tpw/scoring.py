VERDICT_LABELS = {
    "priority": "優先採買",
    "consider": "可以採買",
    "watch": "當季，價格一般",
    "hold": "當季但建議觀望",
    "insufficient": "資料不足，暫不判定",
    "not_ranked": "不列入本期當季推薦",
}


def _ratio_score(ratio):
    if ratio is None:
        return 0
    for ceiling, score in ((0.85, 25), (0.95, 20), (1.0, 15), (1.05, 10), (1.15, 5)):
        if ratio <= ceiling:
            return score
    return 0


def _volume_score(ratio):
    if ratio is None:
        return 0
    for floor, score in ((1.25, 15), (1.0, 12), (0.75, 8), (0.5, 4)):
        if ratio >= floor:
            return score
    return 0


def _volatility_penalty(value):
    if value is None or value <= 0.10:
        return 0
    if value <= 0.20:
        return -3
    if value <= 0.30:
        return -7
    return -10


def _pct(current, reference):
    if current is None or reference in (None, 0):
        return None
    return round((current - reference) / reference * 100, 6)


def score_item(series, seasonality):
    today = series["today"]
    windows = series["windows"]
    in_season = seasonality["seasonality_status"] == "in_season"
    market_valid = today["price_twd_per_kg"] is not None and today["volume_kg"] > 0
    coverage_valid = windows["7d"]["status"] == windows["30d"]["status"] == "valid"
    quality_valid = not today.get("quality_warnings")
    eligible = (
        in_season
        and market_valid
        and coverage_valid
        and today["market_count"] >= 2
        and quality_valid
    )
    current = today["price_twd_per_kg"]
    ratio_7d = current / windows["7d"]["price_twd_per_kg"] if windows["7d"]["price_twd_per_kg"] else None
    ratio_30d = current / windows["30d"]["price_twd_per_kg"] if windows["30d"]["price_twd_per_kg"] else None
    volume_ratio = today["volume_kg"] / windows["7d"]["avg_daily_volume_kg"] if windows["7d"]["avg_daily_volume_kg"] else None
    components = {
        "seasonality": 30 if in_season else 0,
        "price_vs_7d": _ratio_score(ratio_7d) if windows["7d"]["status"] == "valid" else 0,
        "price_vs_30d": _ratio_score(ratio_30d) if windows["30d"]["status"] == "valid" else 0,
        "volume_vs_7d": _volume_score(volume_ratio) if windows["7d"]["status"] == "valid" else 0,
        "data_quality": 5 if eligible else 0,
        "volatility_penalty": _volatility_penalty(series["volatility_7d_cv"]),
    }
    score = max(0, min(100, sum(components.values())))
    if not in_season:
        verdict = "not_ranked"
    elif not eligible:
        verdict = "insufficient"
    elif score >= 80:
        verdict = "priority"
    elif score >= 65:
        verdict = "consider"
    elif score >= 50:
        verdict = "watch"
    else:
        verdict = "hold"
    reasons = []
    if not coverage_valid:
        reasons.append("COVERAGE_INSUFFICIENT")
    if today["market_count"] < 2:
        reasons.append("MARKET_COUNT_INSUFFICIENT")
    if not quality_valid:
        reasons.append("DATA_QUALITY_WARNING")
    if in_season:
        reasons.append("IN_SEASON")
    if ratio_7d is not None and ratio_7d <= 1:
        reasons.append("PRICE_AT_OR_BELOW_7D")
    if ratio_30d is not None and ratio_30d <= 1:
        reasons.append("PRICE_AT_OR_BELOW_30D")
    if volume_ratio is not None and volume_ratio >= 1:
        reasons.append("VOLUME_HEALTHY")
    return {
        "canonical_id": series["canonical_id"],
        "as_of_date": series["as_of_date"],
        "score": score,
        "verdict": verdict,
        "verdict_label": VERDICT_LABELS[verdict],
        "eligible": eligible,
        "seasonality_status": seasonality["seasonality_status"],
        "today_price": current,
        "previous_trading_day_change_pct": series["previous_trading_day"]["change_pct"],
        "vs_7d_pct": _pct(current, windows["7d"]["price_twd_per_kg"]),
        "vs_30d_pct": _pct(current, windows["30d"]["price_twd_per_kg"]),
        "volume_vs_7d_pct": _pct(today["volume_kg"], windows["7d"]["avg_daily_volume_kg"]),
        "volatility_7d_cv": series["volatility_7d_cv"],
        "market_count": today["market_count"],
        "coverage": {
            "days_7d": windows["7d"]["coverage_days"],
            "days_30d": windows["30d"]["coverage_days"],
            "days_90d": windows["90d"]["coverage_days"],
        },
        "components": components,
        "reason_codes": reasons[:4],
    }


def score_all(series_rows, seasonality_rows):
    seasons = {row["canonical_id"]: row for row in seasonality_rows}
    scores = [score_item(row, seasons[row["canonical_id"]]) for row in series_rows]
    return sorted(scores, key=lambda row: (-row["eligible"], -row["score"], row["canonical_id"]))
