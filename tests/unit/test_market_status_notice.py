import unittest

from tpw.render import _market_status_notice


class MarketStatusNoticeTest(unittest.TestCase):
    def test_incomplete_feed_preserves_scheduled_closed_market_context(self):
        status = {
            "status": "incomplete",
            "requested_date": "2026-08-31",
            "resolved_date": "2026-08-30",
            "calendar": {
                "schedule_status": "scheduled_closed",
                "reason": "一般週一休市",
                "calendar_version": "115-114.07.30-fruit-vegetable",
                "document_url": "https://www.tapmc.com.tw/example.pdf",
                "markets": [
                    {"market_code": "109", "market_name": "臺北一"},
                    {"market_code": "104", "market_name": "臺北二"},
                ],
            },
        }

        rendered = _market_status_notice(status)

        self.assertIn("data-market-status='incomplete'", rendered)
        self.assertIn("data-calendar-status='scheduled_closed'", rendered)
        self.assertIn("臺北一、臺北二同日為官方公告休市（一般週一休市）。", rendered)
        self.assertIn("https://www.tapmc.com.tw/example.pdf", rendered)


if __name__ == "__main__":
    unittest.main()
