import json
import urllib.error
import unittest

from tpw.market import UpstreamUnavailable
from tpw.traceability import REQUIRED_REGISTRY_FIELDS, fetch_registry


class Response:
    def __init__(self, body, content_type="application/json", status=200):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self.status = status

    def read(self):
        return self._body


def official_row(tracecode):
    row = {field: "" for field in REQUIRED_REGISTRY_FIELDS}
    row.update(
        {
            "Tracecode": tracecode,
            "Producer": "示範組織",
            "OrgID": "ORG-1",
            "ProductName": "香蕉",
            "Place": "屏東縣內埔鄉",
            "PackDate": "2026/08/25",
            "CertificationName": "示範驗證機構",
            "ValidDate": "2026/12/31",
            "Log_UpdateTime": "2026/08/25",
        }
    )
    return row


class TraceabilityRegistryContractTest(unittest.TestCase):
    def test_bounded_pagination_and_content_hash(self):
        pages = [
            json.dumps([official_row("A"), official_row("B")], ensure_ascii=False).encode(),
            json.dumps([official_row("C")], ensure_ascii=False).encode(),
        ]
        urls = []

        def opener(url, **_kwargs):
            return Response(pages[1] if "%24skip=2" in url else pages[0])

        rows, content_hash = fetch_registry(top=2, max_pages=2, opener=opener, urls=urls)
        self.assertEqual([row["Tracecode"] for row in rows], ["A", "B", "C"])
        self.assertEqual(len(urls), 2)
        self.assertIn("%24top=2", urls[0])
        self.assertTrue(content_hash.startswith("sha256:"))

    def test_empty_html_and_non_json_are_typed_unavailable(self):
        cases = [(b"", "application/json"), (b"<html>x</html>", "text/html"), (b"[]", "text/plain")]
        for body, content_type in cases:
            with self.subTest(content_type=content_type), self.assertRaises(UpstreamUnavailable):
                fetch_registry(top=2, max_pages=1, attempts=1, opener=lambda *_a, **_k: Response(body, content_type))

    def test_schema_drift_and_malformed_json_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "schema drift"):
            fetch_registry(top=2, max_pages=1, opener=lambda *_a, **_k: Response(b'[{"Tracecode":"A"}]'))
        with self.assertRaisesRegex(ValueError, "malformed JSON"):
            fetch_registry(top=2, max_pages=1, opener=lambda *_a, **_k: Response(b"{bad"))

    def test_retryable_transport_failure_retries(self):
        calls = []

        def opener(*_args, **_kwargs):
            calls.append(1)
            if len(calls) < 2:
                raise urllib.error.URLError("temporary")
            return Response(json.dumps([official_row("A")], ensure_ascii=False).encode())

        sleeps = []
        rows, _hash = fetch_registry(top=2, opener=opener, attempts=2, backoff_seconds=0.25, sleeper=sleeps.append)
        self.assertEqual(len(rows), 1)
        self.assertEqual(sleeps, [0.25])
