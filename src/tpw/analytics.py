import statistics
def aggregate(rows):
    groups = {}
    for r in rows:
        if not r["canonical_id"]: continue
        groups.setdefault((r["transaction_date"],r["canonical_id"]), []).append(r)
    out=[]
    for (date, item), group in sorted(groups.items()):
        valid=[r for r in group if r["avg_price_twd_per_kg"]>0 and r["volume_kg"]>0]
        prices=[r["avg_price_twd_per_kg"] for r in valid]; volume=sum(r["volume_kg"] for r in valid)
        out.append({"transaction_date":date,"canonical_id":item,"weighted_avg_price_twd_per_kg":sum(r["avg_price_twd_per_kg"]*r["volume_kg"] for r in valid)/volume if volume else None,"total_volume_kg":volume,"market_count":len({r["market_code"] for r in valid}),"market_median_price_twd_per_kg":statistics.median(prices) if prices else None,"min_market_price_twd_per_kg":min(prices) if prices else None,"max_market_price_twd_per_kg":max(prices) if prices else None,"valid_row_count":len(valid),"excluded_row_count":len(group)-len(valid),"quality_warnings":[] if len(valid)==len(group) else ["zero-price-or-volume-excluded"]})
    return out
