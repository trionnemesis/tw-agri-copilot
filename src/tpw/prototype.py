import datetime as dt


MARKETS = (
    ("104", "台北二", 0.98, 0.7),
    ("109", "台北一", 1.02, 0.3),
)


def generate_market_rows(items, fixture, as_of_date):
    end = dt.date.fromisoformat(as_of_date)
    days = int(fixture.get("days", 35))
    profiles = {item["canonical_id"]: item for item in fixture["items"]}
    rows = []
    for item in sorted(items, key=lambda value: value["canonical_id"]):
        profile = profiles[item["canonical_id"]]
        crop_code = item["market_crop_codes"][0]
        for days_ago in range(days - 1, -1, -1):
            date = end - dt.timedelta(days=days_ago)
            reference_price = profile["current_price"] * (
                1 + profile["history_slope"] * days_ago
            )
            daily_volume = profile["daily_volume"] * (
                profile.get("today_volume_multiplier", 1)
                if days_ago == 0
                else 1
            )
            for market_code, market_name, price_factor, volume_share in MARKETS:
                average = round(reference_price * price_factor, 2)
                rows.append(
                    {
                        "交易日期": "%03d.%02d.%02d"
                        % (date.year - 1911, date.month, date.day),
                        "種類代碼": "N05" if item["category"] == "fruit" else "N04",
                        "作物代號": crop_code,
                        "作物名稱": item["display_name"],
                        "市場代號": market_code,
                        "市場名稱": market_name,
                        "上價": round(average * 1.08, 2),
                        "中價": average,
                        "下價": round(average * 0.92, 2),
                        "平均價": average,
                        "交易量": round(daily_volume * volume_share, 2),
                    }
                )
    return rows
