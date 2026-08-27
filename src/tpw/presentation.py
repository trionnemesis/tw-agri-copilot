from pathlib import Path


# Presentation-only translations. Machine-readable JSON keeps the original
# status/mode codes so existing tests and consumers do not change contract.
PRESENTATION_VERSION = "2026-08-26.1"

REPLACEMENTS = (
    ("Taiwan Produce Watch 台灣蔬果行情原型", "Taiwan Produce Watch 台灣蔬果行情與當季採買資訊"),
    ("資料狀態：success", "行情資料：官方更新成功"),
    ("資料狀態：fixture", "行情資料：原型測試資料"),
    ("資料狀態：validated", "行情資料：已完成驗證"),
    ("DETERMINISTIC ADVICE", "RULE-BASED ADVICE"),
    ("項通過 gate", "項符合採買條件"),
    ("資料覆蓋率或品質 gate", "資料覆蓋率或品質門檻"),
    ("完整 eligibility gate", "完整資料門檻"),
    (" · prompt：", " · 規則版本："),
    (
        "目前使用 manual fallback 原型資料；沒有出現在資料中的品項會標記 unknown，不會直接判定非當季。",
        "目前產季與主要產地採內建參考資料；未涵蓋的品項會標示為「資料未涵蓋」，不直接判定為非當季。",
    ),
    (
        "fallback 資料僅供原型；unknown 不等於非當季。",
        "目前產季資料採內建參考資料；「資料未涵蓋」不等於非當季。",
    ),
    ("具 fallback 產季資訊；產地只作季節背景，不代表當日成交來源。", "具產季參考資訊；產地僅作季節背景，不代表當日市場成交來源。"),
    ("筆最小化 prototype fixture。", "筆履歷參考資料。"),
    (
        "此為同品項的公開產銷履歷紀錄，非本日市場成交來源證明。",
        "目前顯示的是同品項履歷參考資料，用於驗證溯源欄位與介面；不代表即時產銷履歷查詢結果，也不是本日市場成交來源證明。",
    ),
    ("machine-readable JSON 都保留在 repo 中。", "可機器讀取的 JSON 都保留在 GitHub repository 中，方便日後追蹤與回溯。"),
    (
        "推薦由 deterministic Buy Score 產生，AI 只能解釋，不能改變數值或 verdict。",
        "採買建議由固定規則的 Buy Score 產生；AI 僅負責解釋，不會修改分數或判定結果。",
    ),
    ("品質警示：", "資料邊界："),
    ("seasonality uses manual fallback", "產季資訊：內建參考資料"),
    ("seasonality uses stale last-known-good data", "產季資訊：同月份最近驗證資料"),
    ("traceability uses minimized fixture records", "產銷履歷：最小化原型資料"),
    ("advice uses deterministic fallback", "採買建議：規則分析模式"),
    ("market data is deterministic prototype fixture", "行情資料：原型測試資料"),
    ("主要產地（fallback）：", "主要產地（參考）："),
    ("manual fallback prototype", "產季與產地參考資訊"),
    (">manual_fallback<", ">內建參考資料<"),
    (">in_season<", ">當季<"),
    (">unknown<", ">資料未涵蓋<"),
    (">out_of_season<", ">非主要產季<"),
    (">valid<", ">資料完整<"),
    (">insufficient_coverage<", ">資料不足<"),
    ("依日曆 window 計算", "依日曆期間計算"),
    ("價格與 rolling windows", "價格與日／週／月／季區間"),
    ("deterministic component", "固定規則評分項目"),
    ("AI 不改變 score 或 verdict。", "AI 不會修改分數或判定結果。"),
    ("Market status：", "行情資料狀態："),
    (
        "fixture／fallback 僅供原型展示，不是即時官方快照。",
        "目前只有批發市場行情使用每日更新的官方來源；產季與產銷履歷仍採原型參考資料，不應解讀為即時官方查詢結果。",
    ),
    ("目前尚無完整 analytics evidence，因此使用 deterministic placeholder。", "目前尚無完整分析資料，因此暫不產生採買判定。"),
    ("Top recommendations", "今日優先項目"),
    ("Watch items", "觀察項目"),
    ("Data quality", "資料品質"),
    ("Sources and boundaries", "資料來源與邊界"),
    ("產季來源狀態與履歷資料邊界保存於公開 JSON", "產季清單會標示官方更新、最近驗證資料或內建參考資料；產銷履歷目前仍為原型參考資料"),
    ("Taiwan Produce Watch · side-project prototype", "Taiwan Produce Watch · 台灣蔬果公開資料觀察"),
)


def rewrite_text(text):
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    return text


def rewrite_tree(root):
    root = Path(root)
    if not root.exists():
        return 0
    changed = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".html", ".md"):
            continue
        before = path.read_text(encoding="utf-8")
        after = rewrite_text(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed += 1
    return changed


def main():
    changed = rewrite_tree("site") + rewrite_tree("reports")
    print(f"presentation {PRESENTATION_VERSION} normalized: {changed} files")


if __name__ == "__main__":
    main()
