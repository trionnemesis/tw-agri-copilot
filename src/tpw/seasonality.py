import datetime as dt
import json


def build_seasonality(items, manual_config, month):
    parsed = dt.date.fromisoformat(month + "-01")
    configured = {entry["canonical_id"]: entry for entry in manual_config["items"]}
    unknown = set(configured) - {item["canonical_id"] for item in items}
    if unknown:
        raise ValueError("seasonality contains unknown canonical ids: " + ", ".join(sorted(unknown)))
    output = []
    for item in sorted(items, key=lambda value: value["display_name"]):
        entry = configured.get(item["canonical_id"])
        if entry is None:
            status = "unknown"
            counties = []
        else:
            months = {int(value) for value in entry["months"]}
            if any(value < 1 or value > 12 for value in months):
                raise ValueError("seasonality month must be 1..12")
            status = "in_season" if parsed.month in months else "out_of_season"
            counties = sorted(set(entry.get("counties", [])))
        output.append(
            {
                "schema_version": "1.0",
                "month": month,
                "canonical_id": item["canonical_id"],
                "display_name": item["display_name"],
                "category": item["category"],
                "seasonality_status": status,
                "counties": counties,
                "county_count": len(counties),
                "source_url": manual_config["source_url"],
                "source_status": "fallback",
                "verified_at": manual_config["verified_at"],
            }
        )
    return output


def load_manual(path, items, month):
    return build_seasonality(items, json.loads(path.read_text()), month)
