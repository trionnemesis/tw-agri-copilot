import hashlib
import json
import pathlib
import tempfile
import unittest
import urllib.error

from tpw.market_calendar import (
    CalendarContractError,
    CalendarUnavailable,
    refresh_market_calendar,
)


ROOT = pathlib.Path(__file__).parents[2]
PDF_BODY = b"%PDF-1.7\ncontrolled fixture"


class Response:
    def __init__(self, body=PDF_BODY, content_type="application/pdf", status=200):
        self.body = body
        self.headers = {"Content-Type": content_type}
        self.status = status

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class MarketCalendarContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / "config").mkdir()
        config = json.loads((ROOT / "config/market-calendar.json").read_text())
        document = config["sources"][0]["documents"][0]
        document["expected_content_hash"] = "sha256:" + hashlib.sha256(PDF_BODY).hexdigest()
        (self.root / "config/market-calendar.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        self.text = (ROOT / "tests/fixtures/tapmc-market-calendar-2026.txt").read_text()

    def tearDown(self):
        self.temp.cleanup()

    def refresh(self, **kwargs):
        return refresh_market_calendar(
            self.root,
            2026,
            opener=kwargs.pop("opener", lambda *_a, **_k: Response()),
            text_extractor=kwargs.pop("text_extractor", lambda _body: self.text),
            retrieved_at=kwargs.pop("retrieved_at", "2026-08-28T14:06:32Z"),
            **kwargs,
        )

    def test_controlled_refresh_is_atomic_and_idempotent(self):
        payload = self.refresh()
        path = self.root / "data/market-calendar/tapmc/2026.json"
        before = path.read_bytes()
        self.assertEqual(payload["closed_day_count"], 80)
        repeated = self.refresh(retrieved_at="2026-08-29T00:00:00Z")
        self.assertEqual(repeated["retrieved_at"], "2026-08-28T14:06:32Z")
        self.assertEqual(path.read_bytes(), before)

    def test_download_and_contract_failures_preserve_last_known_good(self):
        self.refresh()
        path = self.root / "data/market-calendar/tapmc/2026.json"
        before = path.read_bytes()
        cases = [
            (
                "download failure",
                {"opener": lambda *_a, **_k: (_ for _ in ()).throw(urllib.error.URLError("offline"))},
                CalendarUnavailable,
            ),
            (
                "HTML replacement",
                {"opener": lambda *_a, **_k: Response(b"<html>x</html>", "text/html")},
                CalendarContractError,
            ),
            (
                "empty response",
                {"opener": lambda *_a, **_k: Response(b"")},
                CalendarContractError,
            ),
            (
                "unapproved hash",
                {"opener": lambda *_a, **_k: Response(PDF_BODY + b"changed")},
                CalendarContractError,
            ),
            (
                "parser failure",
                {"text_extractor": lambda _body: "changed layout"},
                CalendarContractError,
            ),
        ]
        for label, arguments, error in cases:
            with self.subTest(label=label), self.assertRaises(error):
                self.refresh(**arguments)
            self.assertEqual(path.read_bytes(), before)
