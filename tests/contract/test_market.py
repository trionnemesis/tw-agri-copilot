import urllib.error
import unittest

from tpw.market import UpstreamUnavailable, fetch


class Response:
    def __init__(self, body, content_type="application/json", status=200):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self.status = status

    def read(self):
        return self._body


class MarketContractTest(unittest.TestCase):
    def test_html_and_empty_fail_before_promotion(self):
        for body, content_type in [
            (b"<html>x</html>", "text/html"),
            (b"", "application/json"),
        ]:
            with self.assertRaises(ValueError):
                fetch(
                    "115.08.25",
                    "115.08.25",
                    opener=lambda *_a, **_k: Response(body, content_type),
                    attempts=1,
                )

    def test_duplicate_page_fails(self):
        body = (
            '[{"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉",'
            '"市場代號":"1","市場名稱":"X","平均價":1,"交易量":1}]'
        ).encode()
        with self.assertRaises(ValueError):
            fetch(
                "115.08.25",
                "115.08.25",
                top=1,
                max_pages=2,
                opener=lambda *_a, **_k: Response(body),
            )

    def test_malformed_status_and_url_pagination(self):
        good = (
            '[{"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉",'
            '"市場代號":"1","市場名稱":"X","平均價":1,"交易量":1}]'
        ).encode()
        urls = []
        self.assertEqual(
            len(
                fetch(
                    "115.08.25",
                    "115.08.25",
                    top=2,
                    opener=lambda *_a, **_k: Response(good),
                    urls=urls,
                )
            ),
            1,
        )
        self.assertIn("%24skip=0", urls[0])
        with self.assertRaises(ValueError):
            fetch(
                "115.08.25",
                "115.08.25",
                opener=lambda *_a, **_k: Response(b"{bad"),
            )

    def test_transient_transport_error_retries_then_succeeds(self):
        good = (
            '[{"交易日期":"115.08.25","作物代號":"A1","作物名稱":"香蕉",'
            '"市場代號":"1","市場名稱":"X","平均價":1,"交易量":1}]'
        ).encode()
        calls = []

        def opener(*_args, **_kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.URLError("temporary upstream failure")
            return Response(good)

        sleeps = []
        rows = fetch(
            "115.08.25",
            "115.08.25",
            opener=opener,
            attempts=3,
            backoff_seconds=0.25,
            sleeper=sleeps.append,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.25, 0.5])

    def test_retryable_http_status_exhaustion_is_typed_transient_failure(self):
        sleeps = []
        with self.assertRaisesRegex(
            UpstreamUnavailable,
            "upstream unavailable after 3 attempts",
        ):
            fetch(
                "115.08.25",
                "115.08.25",
                opener=lambda *_a, **_k: Response(
                    b"service unavailable",
                    content_type="text/plain",
                    status=503,
                ),
                attempts=3,
                backoff_seconds=0.1,
                sleeper=sleeps.append,
            )
        self.assertEqual(sleeps, [0.1, 0.2])

    def test_non_retryable_http_status_fails_immediately(self):
        calls = []

        def opener(*_args, **_kwargs):
            calls.append(1)
            return Response(b"bad request", content_type="text/plain", status=400)

        with self.assertRaisesRegex(ValueError, "upstream HTTP status 400"):
            fetch(
                "115.08.25",
                "115.08.25",
                opener=opener,
                attempts=3,
                sleeper=lambda _seconds: None,
            )
        self.assertEqual(len(calls), 1)
