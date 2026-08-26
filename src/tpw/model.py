import datetime as dt, hashlib, json, math

REQUIRED = ("交易日期", "作物代號", "作物名稱", "市場代號", "市場名稱", "平均價", "交易量")

def iso_date(value):
    value = str(value).strip()
    if "." in value:
        y, m, d = value.split(".")
        y = int(y) + 1911 if len(y) == 3 else int(y)
        return dt.date(y, int(m), int(d)).isoformat()
    return dt.date.fromisoformat(value[:10]).isoformat()

def number(value):
    n = float(value)
    if not math.isfinite(n) or n < 0: raise ValueError("numeric field must be finite and nonnegative")
    return n

def canonical_map(items):
    result = {}; ids=set()
    for item in items:
        if item.get("category") not in ("fruit","vegetable"): raise ValueError("invalid category")
        if item["canonical_id"] in ids: raise ValueError("duplicate canonical_id")
        ids.add(item["canonical_id"])
        if item.get("enabled"):
            for code in item["market_crop_codes"]:
                if code in result: raise ValueError("duplicate crop code")
                result[code]=item
    return result

def normalize(raw, mapping, fetched_at="fixture"):
    missing = [f for f in REQUIRED if f not in raw]
    if missing: raise ValueError("missing required fields: " + ", ".join(missing))
    item = mapping.get(str(raw["作物代號"]))
    base = {"schema_version":"1.0", "transaction_date":iso_date(raw["交易日期"]), "category_code":raw.get("種類代碼"), "crop_code":str(raw["作物代號"]), "crop_name_raw":str(raw["作物名稱"]), "canonical_id":item["canonical_id"] if item else None, "display_name":item["display_name"] if item else str(raw["作物名稱"]), "category":item["category"] if item else "unknown", "market_code":str(raw["市場代號"]), "market_name":str(raw["市場名稱"]), "high_price_twd_per_kg":number(raw.get("上價", 0)), "mid_price_twd_per_kg":number(raw.get("中價", 0)), "low_price_twd_per_kg":number(raw.get("下價", 0)), "avg_price_twd_per_kg":number(raw["平均價"]), "volume_kg":number(raw["交易量"]), "source_id":"moa_market_8066"}
    base["row_hash"] = "sha256:" + hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    base["fetched_at"] = fetched_at
    return base

def upsert(rows):
    keyed = {}
    for row in rows:
        key = (row["transaction_date"], row["crop_code"], row["market_code"])
        previous = keyed.get(key)
        if previous is None or previous.get("row_hash") != row.get("row_hash"):
            keyed[key] = row
    return [keyed[k] for k in sorted(keyed)]
