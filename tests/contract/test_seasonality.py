import urllib.error
import unittest

from tpw.market import UpstreamUnavailable
from tpw.seasonality import fetch_category, parse_page


class Response:
    def __init__(self, body, content_type="text/html; charset=UTF-8", status=200):
        self._body = body.encode() if isinstance(body, str) else body
        self.headers = {"Content-Type": content_type}
        self.status = status

    def read(self):
        return self._body


def result_page(
    name="香蕉",
    category="水果",
    month="8月",
    next_href="#",
    current_page=1,
    advertised_pages=(1,),
    include_next=True,
):
    page_links = "".join(
        f'<li class="{"active" if page == current_page else ""}"><a href="#" title="第{page}頁">{page}</a></li>'
        for page in advertised_pages
    )
    next_link = f'<li><a title="下一頁" href="{next_href}">下一頁</a></li>' if include_next else ""
    return f"""<!doctype html><html><body>
    <table class="table table-a-products">
      <tr><th>種類</th><th>農產品</th></tr>
      <tr>
        <td data-th="種類">{category}</td><td data-th="農產品">{name}</td>
        <td data-th="品種名稱">北蕉</td><td data-th="縣市">屏東縣</td>
        <td data-th="行政區">高樹鄉</td><td data-th="盛產月份">{month}</td>
      </tr>
    </table>
    <ul class="pagination">{page_links}{next_link}</ul>
    </body></html>"""


class SeasonalityContractTest(unittest.TestCase):
    def test_fetches_sequential_pages_with_explicit_category_and_month(self):
        pages = {
            1: result_page(
                next_href="index.php?code=list&amp;ids=1103&amp;mod_code=search&amp;type=1&amp;period=8&amp;page=2",
                advertised_pages=(1, 2),
            ),
            2: result_page(name="鳳梨", current_page=2, advertised_pages=(1, 2)),
        }
        urls = []

        def opener(url, **_kwargs):
            page = 2 if "page=2" in url else 1
            return Response(pages[page])

        rows = fetch_category("fruit", "2026-08", opener=opener, urls=urls)
        self.assertEqual([row["display_name"] for row in rows], ["香蕉", "鳳梨"])
        self.assertEqual(len(urls), 2)
        self.assertIn("type=1", urls[0])
        self.assertIn("period=8", urls[0])

    def test_schema_category_and_month_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "official result table"):
            parse_page("<html><body>changed</body></html>", "fruit", "2026-08")
        with self.assertRaisesRegex(ValueError, "category"):
            parse_page(result_page(category="蔬菜"), "fruit", "2026-08")
        with self.assertRaisesRegex(ValueError, "month"):
            parse_page(result_page(month="7月"), "fruit", "2026-08")

    def test_duplicate_page_is_rejected(self):
        first = result_page(
            next_href="index.php?code=list&amp;ids=1103&amp;mod_code=search&amp;type=1&amp;period=8&amp;page=2",
            advertised_pages=(1, 2),
        )

        def opener(url, **_kwargs):
            return Response(result_page(current_page=2, advertised_pages=(1, 2)) if "page=2" in url else first)

        with self.assertRaisesRegex(ValueError, "duplicate seasonality"):
            fetch_category("fruit", "2026-08", opener=opener)

    def test_missing_next_control_rejects_a_truncated_catalog(self):
        body = result_page(advertised_pages=(1, 2), include_next=False)
        with self.assertRaisesRegex(ValueError, "next-page control"):
            parse_page(body, "fruit", "2026-08")

    def test_disabled_next_control_rejects_an_advertised_later_page(self):
        body = result_page(advertised_pages=(1, 2), next_href="#")
        with self.assertRaisesRegex(ValueError, "terminates before an advertised page"):
            parse_page(body, "fruit", "2026-08")

    def test_transient_transport_failure_retries_then_succeeds(self):
        calls = []

        def opener(*_args, **_kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.URLError("temporary")
            return Response(result_page())

        sleeps = []
        rows = fetch_category(
            "fruit",
            "2026-08",
            opener=opener,
            attempts=3,
            backoff_seconds=0.25,
            sleeper=sleeps.append,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(sleeps, [0.25, 0.5])

    def test_non_html_exhaustion_is_typed_transient_failure(self):
        with self.assertRaises(UpstreamUnavailable):
            fetch_category(
                "fruit",
                "2026-08",
                opener=lambda *_args, **_kwargs: Response("service unavailable", "text/plain"),
                attempts=1,
            )
