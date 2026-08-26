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
