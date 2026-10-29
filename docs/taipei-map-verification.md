# WO-51-MAP-01 驗證紀錄（2026-10-29）

基準：`f5e20443edb3687d7d0d3872c544132926c39381`。實作 head、遠端 CI、合併與部署 SHA 由 PR／Issue #51 的交付留言記錄，避免在 commit 內自我引用 head。

## 實作及來源邊界

- 四張 work order 由 GPT-6.1 Terra（high effort）執行，另有獨立 Terra review；主代理協調、驗證並處理 PR／部署。
- 新增獨立 `/taipei/map.html`，以市場＋原始作物代碼計算價量與 7/30/90D，保留 calendar/observation 狀態與空值。
- 地理證據見 [map-geography-evidence.md](map-geography-evidence.md)，行情來源稽核見 [map-data-audit.md](map-data-audit.md)。官方區界 ZIP 與 CSV 已實際下載；沒有重新向 MOA 抓取歷史行情。
- 十二行政區已核對原始 `.prj`、EPSG:3826、原始幾何與 display transform。104 點位通過原始中山區 polygon containment。109 的 531／533 地址差異尚未解除，因此**僅 1/2 營運點位可畫；不是完整雙點地圖驗收**。
- publication 保留 requested=2026-10-29、as_of=2026-10-21、source_unavailable；不宣稱今日行情。
- 新 map observed 資格：90 日窗 2,368 列納入、1,247 fixture 與119 provenance_unknown 排除，兩市場各43個有效日期；全歷史fixture總計1,327列。各數字屬此固定快照。
- 舊全臺／Taipei 統計口徑與資料不改；另有 PR #56 的全站歷史 fixture 修正，不納入本次地圖 PR。

## 本機驗證

Python 3.11.17；Node 24；Playwright 1.62.1。瀏覽器因下載鏡像檔案不完整，使用環境既有 Chromium 153 executablePath 的臨時 config；不修改 repo harness。GitHub runner 使用 repo 原始 Playwright 設定再驗。

- 完整 Python suite：338 tests passed（unit／contract／integration）。
- 依 `.github/workflows/ci.yml` 次序：compile、config、market-calendar、agent-run、committed-publication verify/validate、seed、source-run、suite publication signature guard、fixture-mode rebuild、traceability、validate/verify、重建兩次雜湊一致、900MB size gates、secret-pattern scan，全部通過。
- 完整 observed browser：63 passed／1 skipped。略過的是 desktop 的 touch-only case；mobile counterpart 有執行。
- 新 map browser：18 passed，涵蓋 desktop/mobile、no-JS、200% zoom、marker keyboard anchor、URL/history、shared scales、90D stats、404／invalid payload／late-response、same-origin requests。
- 實際 Draft202012 JSON Schema validator（jsonschema 4.26.0，僅 QA 環境，不新增專案依賴）驗證發布 map JSON 與 geography sidecar，0 errors。
- 離線 wheel 打包確認 SVG／JS／CSS 都存在。
- base/candidate 同用 Python3.11、2026-10-21 快照及 presentation 正規化重建。所有既有 `data/**`、`reports/**` 及舊 JSON/CSV 逐 byte 相同；既有 HTML 唯一變更為 `site/taipei/index.html` 新增地圖入口。

### 驗收對應

| 契約 | 主要證據 |
|---|---|
| MAP-01/02/03 | independent acceptance：非臺北極值不變、104變動不影響109、SB1/SB2不混比 |
| MAP-04/05 | 175元/kg加權fixture、重排／去重 deterministic、同key異值及偽用同hash拒絕 |
| MAP-06/07 | observed排fixture、fixture需明確mode與metadata、來源timestamp可不同、source-runs-only支持 |
| MAP-08/09/10 | UI日期失敗提示、比較同asof、不同日不湊齊、zero/missing/closed/conflict分離 |
| MAP-11/12 | 12區實檔／CRS／原始polygon驗證；109不畫假營運點（精確點位仍待查） |
| MAP-13/14 | 共用色量尺與radius數值、URL/history、invalid hydration、404、race測試 |
| MAP-15/16 | desktop/mobile/no-JS/200%zoom、同站請求、SVG allowlist、相對路徑驗證 |
| MAP-17/18 | 壞SVG／sidecar合法failed scope、strict config拒絕、CSV/hash篡改拒絕、雙重重建及既有browser回歸 |

截圖：[桌機](evidence/taipei-map/desktop.png)／[390px手機](evidence/taipei-map/mobile.png)。本機截圖已檢查中文標籤、版面與資料狀態；未執行 Safari/WebKit 或實體手機測試。

### 未壓縮大小

- `src/tpw/assets/taipei-districts.svg`：57,408 bytes。
- `site/taipei/map.html`：88,966 bytes。
- `site/data/taipei/map-ui.json`：483,027 bytes。
- `site/data/taipei/map.json`：1,283,940 bytes。
- 專屬 JS＋CSS：15,333 bytes。

上述五項均由 verify-site 設硬性預算 gate。正式 observed、fixture、地理來源核對、本機 browser、merged、Pages deployed、線上核對為不同狀態；遠端及上線結果以交付留言的 run/commit 證據為準。
