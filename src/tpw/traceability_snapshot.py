import argparse
import datetime as dt
import json
import pathlib

from .traceability import normalize_registry, validate_registry_snapshot


ROOT = pathlib.Path.cwd()


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _fixture_snapshot(root, as_of_date):
    items = json.loads((root / "config/produce.yml").read_text(encoding="utf-8"))["items"]
    fixture = json.loads((root / "config/traceability.fixture.json").read_text(encoding="utf-8"))
    records = fixture.get("items", fixture.get("records", []))
    return normalize_registry(
        records,
        items,
        as_of_date,
        as_of_date + "T00:00:00Z",
        source_status="fixture",
        allow_canonical_hint=True,
    )


def ensure_traceability_snapshot(as_of_date, root=ROOT):
    as_of_date = dt.date.fromisoformat(as_of_date).isoformat()
    base = root / "data/traceability"
    rows_path = base / "daily" / as_of_date[:4] / as_of_date[5:7] / (as_of_date + ".json")
    profile_path = base / "profiles" / as_of_date[:4] / as_of_date[5:7] / (as_of_date + ".json")

    if rows_path.exists() and profile_path.exists():
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        validate_registry_snapshot(rows, profile)
        if profile.get("as_of_date") != as_of_date:
            raise ValueError("date-scoped traceability profile does not match requested date")
        return profile

    current_rows = base / "current.json"
    current_profile = base / "source-profile.json"
    if current_rows.exists() and current_profile.exists():
        rows = json.loads(current_rows.read_text(encoding="utf-8"))
        profile = json.loads(current_profile.read_text(encoding="utf-8"))
        validate_registry_snapshot(rows, profile)
        if profile.get("as_of_date") != as_of_date:
            rows, profile = _fixture_snapshot(root, as_of_date)
    else:
        rows, profile = _fixture_snapshot(root, as_of_date)

    validate_registry_snapshot(rows, profile)
    _write_json(rows_path, rows)
    _write_json(profile_path, profile)
    return profile


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    profile = ensure_traceability_snapshot(args.as_of)
    print(
        "traceability exact-date context:",
        profile["as_of_date"],
        profile["source_status"],
        profile["published_record_count"],
    )


if __name__ == "__main__":
    main()
