# Taiwan Produce Watch｜台灣蔬果行情觀察

[![Fixture CI](https://github.com/trionnemesis/tw-agri-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/trionnemesis/tw-agri-copilot/actions/workflows/ci.yml)
[![Deploy Pages](https://github.com/trionnemesis/tw-agri-copilot/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/trionnemesis/tw-agri-copilot/actions/workflows/deploy-pages.yml)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![Status](https://img.shields.io/badge/status-prototype-f59e0b)

> 把每日批發市場行情、當季脈絡與可解釋 Buy Score，整理成一個可重建、可追溯的靜態採買情報原型。

**[開啟 GitHub Pages](https://trionnemesis.github.io/tw-agri-copilot/)** · [快速開始](#快速開始) · [功能](#原型功能) · [資料流程](#資料流程) · [信任邊界](#資料信任邊界) · [驗證](VERIFICATION.md)

## Why

「今天吃什麼」不該只靠一個價格數字。Taiwan Produce Watch 將 20 項台灣常見蔬果的市場資料轉成前一交易日、7／30／90 日趨勢、coverage、產季與 deterministic Buy Score；AI 層只負責解釋，不能改寫分數或 verdict。

本專案目前是 **side-project prototype**。行情、官方市場日曆與產季各自保存來源狀態；臺北一／臺北二使用已驗證的臺北農產年度休市日曆，產季則可抓取農糧署完整月份清單。暫時性故障才沿用 last-known-good 或 manual fallback。產銷履歷與 advice 仍使用 minimized fixture／deterministic fallback，因此它不是完整的即時官方服務。

> **價格邊界：批發市場平均行情，非實際零售通路售價。**

## 原型功能

| Slice | 已完成的原型能力 | 關鍵邊界 |
|---|---|---|
| PR 1 · Foundation | 精確 watchlist mapping、ROC 日期、correction-safe upsert、交易量加權日價、歷史保留 | live 120-day pull 尚未作 release 驗證 |
| PR 2 · Analytics | 前一有效交易日、7／30／90D、coverage、20 個品項頁、日／週／月／季頁與 SVG chart fallback | coverage 不足時不產生正向判定 |
| PR 3 · Recommendation | manual seasonality adapter、Buy Score、首頁推薦卡、price movers | 產季／市場數／7D／30D／品質是 hard gates |
| PR 4 · Advice | provider-neutral input、strict zh-Hant schema、guardrails、deterministic fallback | AI 只能解釋既有 evidence，不能改數字或 verdict |
| PR 5 · Traceability | watchlist filtering、nullable fields、粗粒度縣市、品項與履歷頁 | 履歷不加入 Buy Score，也不代表本日成交來源 |
| Issue #8 · Live seasonality | 農糧署 HTML adapter、完整分頁、月份 catalog、LKG／fallback、完整當季清單 | 只做明確名稱 mapping；不做 fuzzy matching |
| Issue #19 · Produce icons | 專案自有 SVG sprite、39 個現有顯示名稱的 exact registry、分類 fallback、列印與 responsive 樣式 | 圖示是裝飾性提示；文字名稱仍是唯一語意來源 |
| Issue #3 · Official calendar | 臺北農產 115 年休市日曆、臺北一／臺北二 market registry、calendar／feed 分離與 discrepancy 狀態 | 日曆不加入行情 aggregate 或 Buy Score；未知年度不宣稱官方休市 |

首頁核心內容與當季圖示不依賴 JavaScript；JS 只提供當季搜尋／篩選、URL 狀態同步與列印。桌機／平板／手機採 3／2／1 欄 responsive cards。

## 資料流程

```mermaid
flowchart LR
  M[Market 8066 or fixture] --> N[Validate + normalize]
  M --> P[Feed status]
  C[TAPMC official calendar fixture] --> P
  N --> U[Correction-safe upsert]
  U --> A[Weighted daily aggregate]
  A --> S[Previous day + 7/30/90D series]
  F[Official seasonality or LKG/fallback] --> B[Deterministic Buy Score]
  F --> H
  S --> B
  B --> D[Advice provider contract]
  D --> H[Static HTML + JSON + Markdown]
  P --> H
  T[Traceability records] --> X[Watchlist filter + minimization]
  X --> H
  X -. no score join .-> B
```

Build 只從已保存的 normalized history 重算，不從生成後的 HTML 或 aggregate history 反推資料。`data/`、`site/`、`reports/` 以 staging + rollback promotion 一次更新。

首頁會分開顯示「今日資料檢查」與「最近完整交易日」。`calendar.schedule_status` 與 `feed_status` 分開保存：預期開市但 feed 空白時不會誤標休市，日曆與交易資料衝突時會顯示 `calendar_feed_discrepancy`。網站會保留最近完整交易日，不把舊日期冒充成今日行情；相同證據也會寫入 `site/data/current.json` 的 `publication_status`。

## 快速開始

需求：Python 3.11+；prototype build 不需額外套件或 API key。

```bash
git clone https://github.com/trionnemesis/tw-agri-copilot.git
cd tw-agri-copilot

PYTHONPATH=src python3 -m tpw validate-config
PYTHONPATH=src python3 -m tpw validate-market-calendar --year 2026
PYTHONPATH=src python3 -m tpw seed-prototype --as-of 2026-08-25
PYTHONPATH=src python3 -m tpw build --as-of 2026-08-25
PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-25
PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-25

python3 -m http.server 8000 --directory site
```

開啟 `http://localhost:8000/`。第二次執行相同 seed/build 會產生相同內容 hash。

一般 build 不需要額外套件。只有受控更新官方 PDF fixture 時，才需先執行 `python3 -m pip install -e '.[calendar]'`，再執行 `PYTHONPATH=src python3 -m tpw refresh-market-calendar --year 2026`；文件 hash、格式、日期總數或 parser contract 不符時不會覆寫 last-known-good fixture。

## CLI

| Command | 用途 |
|---|---|
| `validate-config` | 驗證 10 水果 + 10 蔬菜 mapping |
| `validate-market-calendar --year YEAR` | 驗證 normalized calendar、365／366 日完整性、market registry 與來源 hash |
| `refresh-market-calendar --year YEAR` | 受控下載及解析已核准的臺北農產年度 PDF；hash／格式漂移時 fail closed |
| `validate-agent-run PATH [PATH ...]` | 驗證 proposed Agent Run JSON 契約；不執行分析或發布 |
| `seed-prototype --as-of DATE` | 建立 35 日、2 市場、20 品項的 deterministic fixture history |
| `fetch-market --start DATE --end DATE` | 呼叫 market adapter 並保存 normalized watchlist data |
| `fetch-seasonality --month YYYY-MM` | 抓取並驗證農糧署水果／蔬菜完整分頁；暫時性故障使用 LKG／fallback |
| `refresh-seasonality --month YYYY-MM [--force]` | 依月份 cache policy 重用或更新產季；`--force` 只略過同月 live reuse，不略過來源與 LKG 驗證 |
| `fetch-traceability --month YYYY-MM` | 保存 watchlist-only minimized fixture records |
| `backfill --days N --end DATE` | 以最多 4 日的 bounded windows 抓取市場資料 |
| `build --as-of DATE` | 從 retained normalized history 重建所有衍生資料與網站 |
| `validate-data --as-of DATE` | 驗證 normalized 與 PR2–PR5 衍生資料樹 |
| `verify-site --as-of DATE` | 檢查 routes、links、SVG sprite／fragment、disclaimers、secrets、size 與 prototype gates |

## 公開頁面

| Route | 內容 |
|---|---|
| [`/`](https://trionnemesis.github.io/tw-agri-copilot/) | 推薦、advice、產季、movers、trends、履歷與來源 |
| `/produce/<canonical-id>.html` | 20 個品項的價格、coverage、score、趨勢與相關履歷 |
| `/trends/daily.html` | 前一有效交易日比較 |
| `/trends/weekly.html` | 7 日 rolling view |
| `/trends/monthly.html` | 30 日 rolling view |
| `/trends/quarterly.html` | 90 日 rolling view |
| `/season/current.html` | 本月完整盛產清單、專案自有蔬果圖示、搜尋／分類篩選、產地數與行情／履歷狀態 |
| `/traceability/index.html` | watchlist 相關履歷索引與 non-join 警示 |
| `/daily/YYYY/MM/YYYY-MM-DD.html` | 每日靜態快照 |
| `/archive/index.html` | retained history |
| `/methodology.html` | 算法、coverage、fallback 與限制 |

## 資料信任邊界

- Market prototype fixture 是可重現測試資料，不是 live Dataset 8066 snapshot。
- Market calendar 是獨立 `calendar` source：目前只涵蓋臺北一 `109`、臺北二 `104`。115 年 fixture 對應官方 PDF 的 80 個休市日／285 個交易日，保存 document URL、calendar／parser version、retrieved time 與 SHA-256；不以空 feed 或固定週一規則取代 fixture。
- `expected_open | scheduled_closed | exceptional_open | unknown` 與 `available | empty | delayed | failed | not_checked` 分開判定；只有具 fixture lineage 的結果可標示「官方公告休市」。
- Seasonality 優先使用農糧署官方月份清單，逐頁驗證分類、月份與欄位；transient failure 才使用 `stale`／`fallback`，schema drift 直接失敗。
- Watchlist 與官方產季名稱只允許 `config/produce.yml` 的明確對照；`unknown` 不等於非當季。
- 當季圖示只依 `(category, display_name)` exact registry 選取；`representative` 代表同類代表圖，未知名稱只使用水果／蔬菜分類 fallback，不做 fuzzy matching。SVG paths 為本專案新作並隨站點發布，不在 runtime 讀取第三方資產、CDN 或 data URI。
- 當季圖示標記為裝飾性 `aria-hidden`；可存取名稱與搜尋文字一律沿用已轉義的蔬果文字名稱。
- Advice 預設為 `deterministic_fallback`，provider 只接收已驗證 metrics、score 與 reason codes。
- Traceability 只保留 watchlist 所需欄位，移除 farmer/store details，place 降為縣市。
- **此為同品項的公開產銷履歷紀錄，非本日市場成交來源證明。**
- 不提交上游全量 dump、credentials、`.env`、private keys 或 base64 圖片。

## Repository anatomy

```text
config/                 watchlist、market registry、calendar 文件契約、score、fixture 與 fallback 設定
src/tpw/                adapters、normalization、analytics、score、advice、render、CLI 與圖示 registry
src/tpw/assets/         專案自有 SVG sprite 原始資產
data/                   normalized history、月份產季 catalog、Agent Run 寫入區與可重建的衍生 JSON
data/market-status/     最近一次市場日檢查與休市／延遲狀態
data/market-calendar/   已驗證的官方年度 normalized calendar fixture
schema/                 Agent Run 與 market calendar JSON Schema
site/                   GitHub Pages 靜態成品
reports/                每日 Markdown 快照
tests/                  unit、contract、integration tests
.github/workflows/      fixture CI、daily update、Pages deploy
SPEC.md                 完整產品／資料契約
VERIFICATION.md         本地與遠端 acceptance evidence
```

## 狀態

- Prototype fixture：可重建、可測試、可部署。
- Live market adapter：已實作 bounded fetch path；本版未進行 live 120-day release 驗證。
- Official market calendar：臺北一／臺北二 115 年 fixture 已實作；calendar／feed 分離、特殊週一開市、非週一休市、未知年度與 discrepancy 均有離線測試。
- External AI provider：未啟用；固定走 deterministic fallback。
- Seasonality：官方 HTML adapter 已實作並保存月份 catalog；同月份 live snapshot 可重用，Actions 手動執行可要求安全強制更新，失敗狀態明確標示。
- Produce icons：完整當季頁以 exact registry 選取本地 sprite symbol，未知品項安全降級為分類 fallback；不改變公開 JSON、搜尋或資料判定。
- Traceability：目前仍為明確標示的 minimized fixture；live adapter 尚未實作。

視覺語言來自使用者提供的分析型 HTML（navy gradient、paper cards、status badges、responsive grids）；README 資訊架構參考 [AgentSec README.zh-TW](https://github.com/trionnemesis/AgentSec/blob/main/README.zh-TW.md)，但內容與資料邊界皆針對本專案重寫。
