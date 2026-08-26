import datetime as dt


TRACEABILITY_WARNING = "此為同品項的公開產銷履歷紀錄，非本日市場成交來源證明。"


def _text(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _date(value):
    text = _text(value)
    if text is None:
        return None
    try:
        return dt.date.fromisoformat(text[:10].replace("/", "-")).isoformat()
    except ValueError:
        return None


def _coarse_place(value):
    text = _text(value)
    if text is None:
        return None
    for marker in ("縣", "市"):
        if marker in text:
            return text[: text.index(marker) + 1]
    return None


def filter_traceability(raw_rows, items, fetched_at="fixture"):
    by_id = {item["canonical_id"]: item for item in items}
    by_name = {}
    for item in items:
        for name in [item["display_name"], *item.get("aliases", [])]:
            by_name[name] = item["canonical_id"]
    output = []
    for raw in raw_rows:
        canonical_id = raw.get("canonical_id")
        if canonical_id not in by_id:
            canonical_id = by_name.get(_text(raw.get("ProductName")))
        if canonical_id is None:
            continue
        output.append(
            {
                "schema_version": "1.0",
                "tracecode": _text(raw.get("Tracecode")) or "",
                "producer": _text(raw.get("Producer")),
                "org_id": _text(raw.get("OrgID")),
                "product_name_raw": _text(raw.get("ProductName")) or by_id[canonical_id]["display_name"],
                "canonical_id": canonical_id,
                "place": _coarse_place(raw.get("Place")),
                "farmer_name": None,
                "pack_date": _date(raw.get("PackDate")),
                "certification_name": _text(raw.get("CertificationName")),
                "valid_date": _date(raw.get("ValidDate")),
                "store_info": None,
                "source_id": "moa_traceability_7556",
                "source_status": raw.get("source_status", "fixture"),
                "fetched_at": fetched_at,
                "semantic_warning": TRACEABILITY_WARNING,
            }
        )
    return sorted(output, key=lambda row: (row["canonical_id"], row["tracecode"]))
