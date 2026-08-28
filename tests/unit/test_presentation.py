import json
import pathlib
import tempfile
import unittest

from tpw.presentation import rewrite_text, rewrite_tree


class PresentationTest(unittest.TestCase):
    def test_rewrites_internal_terms_for_humans(self):
        raw = (
            "資料狀態：success · 品質警示：seasonality uses manual fallback、"
            "traceability uses minimized fixture records、advice uses deterministic fallback\n"
            "13 項具 fallback 產季資訊；產地只作季節背景，不代表當日成交來源。\n"
            "5 筆最小化 prototype fixture。此為同品項的公開產銷履歷紀錄，非本日市場成交來源證明。\n"
            "每日 HTML、Markdown 與 machine-readable JSON 都保留在 repo 中。\n"
            "推薦由 deterministic Buy Score 產生，AI 只能解釋，不能改變數值或 verdict。"
        )
        rendered = rewrite_text(raw)
        self.assertIn("行情資料：官方更新成功", rendered)
        self.assertIn("產季資訊：內建參考資料", rendered)
        self.assertIn("產銷履歷：最小化原型資料", rendered)
        self.assertIn("採買建議：規則分析模式", rendered)
        self.assertIn("13 項具產季參考資訊", rendered)
        self.assertIn("5 筆履歷參考資料", rendered)
        self.assertIn("可機器讀取的 JSON", rendered)
        self.assertIn("固定規則的 Buy Score", rendered)
        for internal in ("prototype fixture", "manual fallback", "machine-readable", "deterministic Buy Score", "verdict"):
            self.assertNotIn(internal, rendered)

    def test_rewrites_market_status_copy_without_changing_contract_codes(self):
        raw = (
            "<strong>2026-08-28 臺北一、臺北二官方公告休市</strong>"
            "<span>中元節後循例休市；日曆版本 115-114.07.30-fruit-vegetable。"
            "目前沿用最近完整交易日 2026-08-26，並非網站漏更新。</span>\n"
            "2026-08-29 日曆與行情來源不一致：官方日曆為休市，但 feed 出現交易資料；已保留兩方證據，"
            "最近完整交易日為 2026-08-28。\n"
            "官方日曆顯示臺北一、臺北二預期開市，但 feed 尚無可發布的完整交易行情；不可標示休市。\n"
            "農業部 feed 回報休市，但尚無此年度經驗證的官方日曆 fixture；"
            "系統已完成重試並保留 last-known-good；"
        )
        rendered = rewrite_text(raw)
        self.assertIn("中元節後循例休市。目前沿用最近完整交易日 2026-08-26", rendered)
        self.assertIn("官方休市日程與行情資料不一致", rendered)
        self.assertIn("官方休市日程顯示休市，但行情來源仍出現交易資料", rendered)
        self.assertIn("官方休市日程顯示臺北一、臺北二預期開市，但行情來源尚無可發布的完整交易行情", rendered)
        self.assertIn("目前沒有該年度已驗證的官方休市日程可供交叉確認", rendered)
        self.assertIn("保留最近一次通過驗證的資料", rendered)
        for internal in ("日曆版本", " feed ", "fixture", "last-known-good"):
            self.assertNotIn(internal, rendered)

    def test_rewrite_tree_does_not_touch_json_contracts(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            html = root / "index.html"
            data = root / "current.json"
            html.write_text("資料狀態：success", encoding="utf-8")
            data.write_text(json.dumps({"source_status": "success", "generation_mode": "deterministic_fallback"}), encoding="utf-8")
            self.assertEqual(rewrite_tree(root), 1)
            self.assertIn("行情資料：官方更新成功", html.read_text(encoding="utf-8"))
            contract = json.loads(data.read_text(encoding="utf-8"))
            self.assertEqual(contract["source_status"], "success")
            self.assertEqual(contract["generation_mode"], "deterministic_fallback")


if __name__ == "__main__":
    unittest.main()
