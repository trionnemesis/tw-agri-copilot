import json
import urllib.error
import unittest

from tpw.market import UpstreamUnavailable
from tpw.traceability_events import REQUIRED_EVENT_FIELDS, fetch_market_events


class Response:
    def __init__(self, body, content_type="application/json", status=200):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self.status = status

    def read(self):
        return self._body


def official_event(crop_code="A1", traceability_code="X"):
    row = {field: "" for field in REQUIRED_EVENT_FIELDS}
    row.update(
        {
            "交易日期": "20260825",
            "作物代號": crop_code,
            "作物名稱": "香蕉",
            "市場代號": "104",
            "市場名稱": "台北二",
            "交易金額_元": "2000",
            "交易量_公斤": "100",
            "溯源代號": traceability_code,
        }
    )
    return row


class TraceabilityMarketEventContractTest(unittest.TestCase):
    def test_bounded_date_pagination_and_content_hash(self):
        pages = [
            json.dumps([official_event("A1"), official_event("B2")], ensure_ascii=False).encode(),
            json.dumps([official_event("811")], ensure_ascii=False).encode(),
        ]
        urls = []

        def opener(url, **_kwargs):
            return Response(pages[1] if "%24skip=2" in url else pages[0])

        rows, content_hash = fetch_market_events(
            "2026-08-25", top=2, max_pages=2, opener=opener, urls=urls
        )
        self.assertEqual(len(rows), 3)
        self.assertIn("StartDate=20260825", urls[0])
        self.assertIn("EndDate=20260825", urls[0])
        self.assertIn("%24top=2", urls[0])
        self.assertTrue(content_hash.startswith("sha256:"))

    def test_empty_html_and_non_json_are_typed_unavailable(self):
        cases = [(b"", "application/json"), (b"<html>x</html>", "text/html"), (b"[]", "text/plain")]
        for body, content_type in cases:
            with self.subTest(content_type=content_type), self.assertRaises(UpstreamUnavailable):
                fetch_market_events(
                    "2026-08-25",
                    top=2,
                    max_pages=1,
                    attempts=1,
                    opener=lambda *_a, **_k: Response(body, content_type),
                )

    def test_schema_drift_and_malformed_json_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "schema drift"):
            fetch_market_events(
                "2026-08-25",
                top=2,
                max_pages=1,
                opener=lambda *_a, **_k: Response('[{"交易日期":"20260825"}]'.encode()),
            )
        with self.assertRaisesRegex(ValueError, "malformed JSON"):
            fetch_market_events(
                "2026-08-25",
                top=2,
                max_pages=1,
                opener=lambda *_a, **_k: Response(b"{bad"),
            )

    def test_retryable_transport_failure_retries(self):
        calls = []

        def opener(*_args, **_kwargs):
            calls.append(1)
            if len(calls) < 2:
                raise urllib.error.URLError("temporary")
            return Response(json.dumps([official_event()], ensure_ascii=False).encode())

        sleeps = []
        rows, _hash = fetch_market_events(
            "2026-08-25",
            top=2,
            opener=opener,
            attempts=2,
            backoff_seconds=0.25,
            sleeper=sleeps.append,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(sleeps, [0.25])
