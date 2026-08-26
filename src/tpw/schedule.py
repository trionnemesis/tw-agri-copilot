import argparse
import datetime as dt
import json
import pathlib


def configured_ids(root):
    payload = json.loads((root / "config/produce.yml").read_text(encoding="utf-8"))
    return {item["canonical_id"] for item in payload["items"]}


def latest_complete_date(root, on_or_before):
    target = dt.date.fromisoformat(on_or_before)
    expected = configured_ids(root)
    if not expected:
        raise ValueError("configured watchlist is empty")

    market_root = root / "data/market/daily"
    candidates = []
    if market_root.exists():
        for path in market_root.rglob("*.json"):
            try:
                day = dt.date.fromisoformat(path.stem)
            except ValueError:
                continue
            if day <= target:
                candidates.append((day, path))

    for day, path in sorted(candidates, key=lambda entry: entry[0], reverse=True):
        rows = json.loads(path.read_text(encoding="utf-8"))
        covered = {
            row.get("canonical_id")
            for row in rows
            if row.get("transaction_date") == day.isoformat()
            and row.get("canonical_id")
        }
        if covered == expected:
            return day.isoformat()

    raise ValueError(f"no complete configured watchlist date on or before {on_or_before}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--on-or-before", required=True)
    args = parser.parse_args(argv)
    print(latest_complete_date(pathlib.Path.cwd(), args.on_or_before))


if __name__ == "__main__":
    main()
