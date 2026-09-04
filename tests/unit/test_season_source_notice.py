import json
import pathlib
import unittest

from tpw.categories import validate_category_registry
from tpw.render import _season_source_notice


ROOT = pathlib.Path(__file__).parents[2]
AFA_URL = "https://www.afa.gov.tw/cht/index.php?code=list&ids=1103"
AFA_URL_ESCAPED = "https://www.afa.gov.tw/cht/index.php?code=list&amp;ids=1103"

# A test-only official_season_registry category, matching the one used in
# tests/unit/test_season_extensions.py and tests/integration/test_build.py's scenario (b) --
# never committed to config/produce-categories.json itself.
TEST_FISHERY_CATEGORY = {
    "id": "test_fishery",
    "label": "測試漁產",
    "season_semantics": "official_season_registry",
    "season_source": {
        "source_id": "test_fishery_source",
        "source_url": "https://example.test/season",
        "allowed_hosts": ["example.test"],
    },
    "market_watchlist": False,
    "buy_score_eligible": False,
    "icon_fallback_symbol": "produce-test_fishery-fallback",
    "note": "測試用",
}


def _registry_with_test_fishery():
    payload = json.loads((ROOT / "config/produce-categories.json").read_text(encoding="utf-8"))
    payload = {**payload, "categories": payload["categories"] + [TEST_FISHERY_CATEGORY]}
    return validate_category_registry(payload, "sha256:" + "0" * 64)


class SeasonSourceNoticeTest(unittest.TestCase):
    def test_single_status_catalog_renders_the_original_unlabelled_notice(self):
        # Issue #44 Part B / Finding A: a homogeneous catalog (today's live publication, and
        # every watchlist call site) must render byte-identically to the pre-Part-B single notice.
        registry = _registry_with_test_fishery()
        rows = [
            {"category": "fruit", "source_status": "live", "source_url": AFA_URL},
            {"category": "vegetable", "source_status": "live", "source_url": AFA_URL},
        ]
        rendered = _season_source_notice(rows, registry)
        self.assertEqual(
            rendered,
            "<p class='note' data-season-source='live'>"
            "清單已由農糧署『農產品產地產期查詢』抓取並完成欄位與分頁驗證。"
            f" <a href='{AFA_URL_ESCAPED}'>查看官方來源</a></p>",
        )
        self.assertNotIn("data-season-source-categories", rendered)

    def test_single_group_case_needs_no_registry_argument(self):
        # The single-group fast path never calls category_label, so it must not require a
        # registry from callers that have none (mirrors resolve_produce_icon's own default).
        rows = [{"category": "fruit", "source_status": "stale", "source_url": AFA_URL}]
        rendered = _season_source_notice(rows)
        self.assertEqual(
            rendered,
            "<p class='note warn' data-season-source='stale'>"
            "本次官方查詢暫時無法取得，清單沿用同月份最近一次通過驗證的資料。"
            f" <a href='{AFA_URL_ESCAPED}'>查看官方來源</a></p>",
        )

    def test_empty_rows_renders_the_fallback_notice(self):
        self.assertEqual(
            _season_source_notice([]),
            "<p class='note warn' data-season-source='fallback'>"
            "目前使用專案內建產季參考資料；未涵蓋品項不會直接判定為非當季。</p>",
        )

    def test_heterogeneous_catalog_emits_one_notice_per_status_group_in_registry_order(self):
        registry = _registry_with_test_fishery()
        rows = [
            {"category": "test_fishery", "source_status": "stale", "source_url": "https://example.test/season"},
            {"category": "vegetable", "source_status": "live", "source_url": AFA_URL},
            {"category": "fruit", "source_status": "live", "source_url": AFA_URL},
        ]
        rendered = _season_source_notice(rows, registry)
        self.assertEqual(rendered.count("<p class="), 2)
        live_index = rendered.index("data-season-source='live'")
        stale_index = rendered.index("data-season-source='stale'")
        self.assertLess(live_index, stale_index, "AFA (fruit, registry rank 0) must sort before test_fishery")
        self.assertIn("data-season-source-categories='fruit,vegetable'", rendered)
        self.assertIn("data-season-source-categories='test_fishery'", rendered)
        self.assertIn("水果、蔬菜：清單已由農糧署", rendered)
        self.assertIn("測試漁產：本次官方查詢暫時無法取得", rendered)
        self.assertIn(f"<a href='{AFA_URL_ESCAPED}'>查看官方來源</a>", rendered)
        self.assertIn("<a href='https://example.test/season'>查看官方來源</a>", rendered)

    def test_group_order_is_independent_of_row_order(self):
        registry = _registry_with_test_fishery()
        forward = [
            {"category": "fruit", "source_status": "live", "source_url": AFA_URL},
            {"category": "test_fishery", "source_status": "stale", "source_url": "https://example.test/season"},
        ]
        backward = list(reversed(forward))
        self.assertEqual(_season_source_notice(forward, registry), _season_source_notice(backward, registry))

    def test_unknown_category_only_matters_once_more_than_one_group_exists(self):
        # A single-group catalog never looks up a category label, so a row missing a category
        # cannot break the common case; this documents that boundary rather than asserting a
        # crash, since real catalog rows are always contract-validated before reaching render.py.
        rows = [{"source_status": "live", "source_url": AFA_URL}]
        rendered = _season_source_notice(rows)
        self.assertIn("data-season-source='live'", rendered)


if __name__ == "__main__":
    unittest.main()
