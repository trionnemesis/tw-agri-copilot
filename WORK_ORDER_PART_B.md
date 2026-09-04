---
work_order_id: TPW-WO-44B
title: Issue #44 Part B — 多類別產季語意契約與畜產／養殖水產 22 縣市矩陣映射
version: 1.0
prepared_at: 2026-09-04
status: Ready for supervisor
source_issue: https://github.com/trionnemesis/tw-agri-copilot/issues/44
source_spec: SPEC.md (SHA-256 2be4f623cf882eca7302d41702ecf53a23564e8f82753a7f82d404f617858ff6, 不得變動)
baseline: main @ a87a722 (v1.0.0), 168 tests OK, publication signature b28c66e1…
---

# Work Order — Issue #44 Part B

## 0. 角色與交付流程

| 角色 | 職責 | 不得 |
|---|---|---|
| Planner（本文件作者） | 定義範圍、契約、驗收門檻 | — |
| Supervisor | 讀完本文件與必讀輸入，切工作包，指派 implementer，做跨檔案確認（§11），跑完整本地驗證，依 §12 回報 | 不 `git commit`、不 push、不開 PR、不改 `SPEC.md` |
| Implementer（一或多個） | 在指定檔案範圍內實作與寫測試，回報命令與結果 | 同上；不擅自擴大檔案範圍；不刪弱測試 |
| Acceptance（獨立） | 對抗性審查、重跑全部門檻（§10）、確認 README／CHANGELOG／VERIFICATION 與實作一致 | 不修改實作以外的判定標準 |
| Orchestrator | 驗收 PASS 後才 commit／push／開 PR／等 CI 綠燈／squash merge 到 `main`，並在 issue 留言 | 驗收未 PASS 不得 merge |

工作分支：`claude/work-order-part-b-ik4o0t`（目前與 `main` 相同）。

---

## 1. 環境限制與證據等級（接手者必讀）

- 本次規劃環境的 egress proxy **封鎖所有 `*.gov.tw`**（`data.moa.gov.tw`、`data.gov.tw`、`www.afa.gov.tw`、`fae.moa.gov.tw`、`efish.fa.gov.tw`、`www.fa.gov.tw`、`ppg.naif.org.tw` 皆回 `CONNECT tunnel failed, response 403`；伺服器端 WebFetch 亦回 `EGRESS_BLOCKED`）。這是 Issue #44 第 0 節與第一則留言記錄的同一狀況，**第三次**發生。
- 因此本 work order **沒有任何 S 級（官方一手）證據**可支撐畜產／水產的產期或行情契約。§13 的來源表全為 A 級（官方網域 URL）或 B 級（搜尋摘要）。
- 結論：**任何需要 live discovery 才能設計的部分（新類別的 live season adapter、行情 adapter、單位、代號命名空間）一律排除在本 work order 之外**；本 work order 只交付能以 checked-in 契約、fixture-based 測試與 deterministic build 完整驗證的部分。
- Implementer 與 supervisor 不得嘗試以訓練知識補造任何畜產／水產的產期、縣市或行情數值（`SPEC.md §0`：未知資訊必須標示為未知，不得補造資料）。

---

## 2. Part B 在本 work order 的定義（第一性原理）

Issue #44 Part B 的問題是：**牲畜／養殖水產能不能像蔬果一樣被映射進「當季 × 22 縣市」矩陣？**

拆到底：矩陣之所以對蔬果成立，是因為農糧署（AFA）提供了一份官方的 (作物, 縣市, 行政區, 盛產月份) **生產登錄**（`SPEC.md §6.2`、BC-1）。畜產（毛豬、家禽、雞蛋）為舍飼全年生產（BC-2）；養殖水產為排程生產（BC-3）；兩者在官方資料中**目前找不到**對應的產期登錄（B-4 第 6–8 題，本次仍無法一手驗證，見 §13）。`SPEC.md §6.2.6` 規定：未出現在產期資料的狀態 **MUST 是 `unknown`**，不得解讀為非當季（BC-4）。

因此本 work order 對 B-4 第 9 題（替代語意）的決定是：

> **畜產與養殖水產以獨立的 `season_semantics = no_official_season_registry` 進入矩陣；矩陣中每一個 (類別 × 縣市) 格子的值都是明示的 `unknown`，並在頁面上說明「官方無產地產期登錄，本站不判定當季或非當季」。** 這不是空白，而是把「來源不具備該語意」這個事實本身映射進矩陣，完全符合 BC-2／BC-4／BC-7。

同時交付讓未來官方來源能「插進來」的機制：類別成為 config-driven registry（不再是 15 處硬編的 fruit/vegetable 二元），季節地圖 payload 支援每類別各自的 source status（解除 TC-3 的 single-status 硬牆），並提供受契約約束的 extension catalog slot。當 B-4 第 6–8 題有一天以 S 級證據確認存在官方登錄，只需：(1) 在 registry 把該類別的 `season_semantics` 改為 `official_season_registry` 並填入來源，(2) 新增 adapter 寫入 extension slot。兩步都是人工審查的 PR（HITL，BC-7）。

### 2.1 明確假設（Assumptions）

| ID | 假設 | 若不成立 |
|---|---|---|
| A-1 | Issue 作者的 Part B 目標可接受「以 `unknown` 明示映射 + 契約就位」作為本階段完成定義；live 資料留待有 egress 的環境 | Orchestrator 於 issue 留言中揭露；後續 PR 補 live adapter |
| A-2 | 類別命名：`livestock`（畜產：毛豬、家禽、雞蛋）、`aquaculture`（養殖水產）；捕撈漁業（BC-3）**不登錄**為類別，僅在 note 說明 | 改 registry 一個 entry 即可 |
| A-3 | BC-5 維持：`SPEC.md §9.2.1` 不改，新類別 `buy_score_eligible=false`，且新類別不進 `config/produce.yml` watchlist（沒有 8066 行情，`build` 也要求 aggregates 覆蓋全部 watchlist） | 需人工授權修 SPEC，另開 work order |
| A-4 | 季節地圖公開 JSON 可升 `schema_version 1.1`（欄位變動見 §6.3）；本專案為 prototype，沒有已知外部消費者 | 保留 1.0 相容層，另議 |
| A-5 | 套件版本 `tpw.__version__` 升為 `1.1.0`（MINOR：新增契約、payload 欄位變動、無資料語意改變） | — |

---

## 3. 必讀輸入（實作前全部讀完）

1. `SPEC.md` — §0、§1、§6.2、§7.2、§7.3、§9.2、§11.7、§12、§16、§17、§19；**不得編輯**。
2. Issue #44 全文與第一則留言（Part A 已完成；D-1／D-2／D-3 已修，`tests/` 現為 hermetic）。
3. `README.md`（資料信任邊界、Repository anatomy）、`CHANGELOG.md`、`VERIFICATION.md`（v1.0.0 段落的證據寫法）、`TASKS.md`、`PLAN.md`、`DISCOVERY.md`。
4. 程式：`src/tpw/{model,seasonality,season_map,produce_icons,render,cli,prototype,presentation,scoring}.py`、`src/tpw/assets/produce-icons.svg`。
5. 設定與 schema：`config/produce.yml`、`config/county-registry.json`、`config/official-produce-markets.json`、`config/seasonality.manual.json`、`schema/season-map.schema.json`。
6. 測試慣例：`tests/unit/test_season_map.py`、`tests/unit/test_produce_icons.py`、`tests/unit/test_seasonality.py`、`tests/integration/test_build.py`（per-test 暫存 repo 副本 + `mock.patch('tpw.cli.ROOT')` 慣用法）、`tests/browser/*.spec.mjs`。
7. Workflow：`.github/workflows/ci.yml`、`daily-update.yml`（「Build, normalize, and validate」與其後三個 gate 步驟，是 §8 WP-3 必須鏡射的順序）。

---

## 4. 範圍（In scope）— 交付物

| ID | 交付物 | 對應 |
|---|---|---|
| D-1 | `config/produce-categories.json` + `schema/produce-categories.schema.json`：類別 registry（§6.1） | TC-2、BC-2、BC-3、BC-5 |
| D-2 | `src/tpw/categories.py`：載入／嚴格驗證 registry、`category_label()`、`category()` 查詢；**未知類別一律 raise**（loud failure，取代 `render.py` 五處 `'水果' if … else '蔬菜'` 的靜默降級） | TC-2、B-2 render 衝擊 |
| D-3 | 15 處 category 硬閘改由 registry 驅動（§7 處置表） | TC-2 |
| D-4 | 季節地圖 payload `schema_version 1.1`：每類別各自 source status、`categories` 軸、`category_registry_hash`（§6.3）；`schema/season-map.schema.json` 同步 | TC-3 |
| D-5 | Extension catalog slot `data/seasonality/extensions/<YYYY-MM>.json` 的 loader／validator 與 `build`／`validate-data` 整合（§6.4）；**不 commit 任何 extension 檔** | BC-2、BC-4、BC-7 |
| D-6 | 圖示：`FALLBACK_ICON_REGISTRY` 與 `_SAFE_SYMBOL_ID` 改由 registry 驅動；sprite 新增 `produce-livestock-fallback`、`produce-aquaculture-fallback` 兩個專案自繪 symbol（§6.5） | D-1 既有原則 |
| D-7 | 頁面：當季頁、產季地圖頁、方法頁依 §6.6 呈現 `no_official_season_registry` 類別；首頁順序與內容不變（`SPEC.md §11.2`） | FR-003、NFR-004、NFR-010 |
| D-8 | 測試：unit／contract／integration／browser 依 §8 各 WP 列表；`tests/` 仍不得寫入 `data/`、`site/`、`reports/` | NFR-001、NFR-003 |
| D-9 | 文件：`README.md`、`CHANGELOG.md`（1.1.0）、`VERIFICATION.md`（新段落）、`TASKS.md`（T-301…）、`PLAN.md`（version 1.1.0 + 一段 scope 補述）、`DISCOVERY.md` 續篇（§13）；`tpw.__version__` → `1.1.0`；重建並提交 committed publication（§8 WP-3） | NFR-008 |

---

## 5. 排除（Out of scope）— 違反即為 blocker，停止並回報

- 不編輯或擴張 `SPEC.md`；SHA-256 必須維持 `2be4f623…`；`references/*.html` 維持 `bd2ddaeb…`。
- 不新增任何 live adapter（畜產／水產產期或行情）；不對 `*.gov.tw` 或任何外部來源發出請求；required tests 不得依賴 live API。
- 不把畜產／水產加入 `config/produce.yml` watchlist；不新增第二種 `dataset_semantics` 的行情資料；不處理 TC-1 單位、TC-4 代號命名空間、TC-5 `market_kind`／`MARKET_HOST_ALLOWLIST`（`official-produce-markets` 契約原封不動）。
- 不改 Buy Score、eligibility、verdict、scoring.yml（BC-5）。
- 不 commit 任何畜產／水產的產期、縣市、月份或行情數值——包括 fixture 或 manual fallback。測試需要多類別資料時，只能在測試自己的暫存 repo 副本中寫入**測試專用**的 registry 類別與 extension 檔（§8 WP-2）。
- 不做 fuzzy matching；不新增 runtime 外連資源、CDN、data URI。
- 不改 workflow 的 trigger／schedule／permissions；若 `ci.yml` 或 `daily-update.yml` 因新驗證需要新增步驟，必須先在 §12 回報中提出，由 orchestrator 決定。
- 不刪除、跳過、弱化既有測試；不放寬既有 fail-closed 條件；不在 repo 根目錄執行 `seed-prototype`（會覆寫 live `data/`）。
- 不建立 Git commit、push、PR，不變更 GitHub 設定，不部署 Pages。
- 不在任何寫入 repo 的檔案（程式、註解、文件、commit message）中出現 AI model 名稱或版本識別。

---

## 6. 資料契約

### 6.1 類別 registry — `config/produce-categories.json`

```json
{
  "schema_version": "1.0",
  "categories": [
    {"id": "fruit", "label": "水果", "season_semantics": "official_season_registry",
     "season_source": {"source_id": "afa_produce_season_1103",
                       "source_url": "https://www.afa.gov.tw/cht/index.php?code=list&ids=1103",
                       "allowed_hosts": ["www.afa.gov.tw"]},
     "market_watchlist": true, "buy_score_eligible": true,
     "icon_fallback_symbol": "produce-fruit-fallback",
     "note": "農糧署「農產品產地產期查詢」type=1；每月 catalog 由官方 HTML adapter 抓取。"},
    {"id": "vegetable", "label": "蔬菜", "season_semantics": "official_season_registry",
     "season_source": {"source_id": "afa_produce_season_1103",
                       "source_url": "https://www.afa.gov.tw/cht/index.php?code=list&ids=1103",
                       "allowed_hosts": ["www.afa.gov.tw"]},
     "market_watchlist": true, "buy_score_eligible": true,
     "icon_fallback_symbol": "produce-vegetable-fallback",
     "note": "農糧署「農產品產地產期查詢」type=2。"},
    {"id": "livestock", "label": "畜產", "season_semantics": "no_official_season_registry",
     "season_source": null, "market_watchlist": false, "buy_score_eligible": false,
     "icon_fallback_symbol": "produce-livestock-fallback",
     "note": "毛豬、家禽、雞蛋為舍飼全年生產，農業部目前沒有對應的產地產期登錄（Issue #44 BC-2）。本站依 SPEC §6.2.6 標示 unknown，不判定當季或非當季。"},
    {"id": "aquaculture", "label": "養殖水產", "season_semantics": "no_official_season_registry",
     "season_source": null, "market_watchlist": false, "buy_score_eligible": false,
     "icon_fallback_symbol": "produce-aquaculture-fallback",
     "note": "虱目魚、吳郭魚、石斑等養殖漁業為排程生產，目前沒有官方的（魚種 × 縣市 × 月份）產期登錄（Issue #44 BC-3）。捕撈漁業具真實汛期，但尚無第一手驗證的官方登錄，未登錄為類別。"}
  ]
}
```

驗證規則（`categories.py` 與 `schema/produce-categories.schema.json` 皆需表達）：

- `id` 唯一、符合 `^[a-z][a-z0-9_]*$`；`label` 非空、去頭尾空白後不變、唯一。
- `season_semantics ∈ {official_season_registry, no_official_season_registry}`；`season_source` 非 null **若且唯若** `official_season_registry`；`allowed_hosts` 非空且 `source_url` 為 https、host ∈ `allowed_hosts`。
- `buy_score_eligible=true` **只允許** `id ∈ {fruit, vegetable}`（`SPEC.md §9.2.1` 的釘住；換言之 BC-5 由 validator 強制）。
- `fruit` 與 `vegetable` 必須存在且為 `official_season_registry`、`market_watchlist=true`（`SPEC.md §7.2.5`、§11.7）。
- `icon_fallback_symbol` 符合 `^produce-<id>-fallback$`；sprite 必須含該 symbol。
- registry 順序即顯示順序（deterministic，不重新排序）。
- 拒絕重複 key、非標準 JSON 常數（沿用 `season_map._strict_object`／`_reject_constant` 慣例）。

### 6.2 `season_semantics` 的語意

| 值 | 意義 | 矩陣格子 |
|---|---|---|
| `official_season_registry` | 存在官方的 (品項 × 縣市 × 月份) 登錄，且有 adapter 寫入 catalog | 有登錄 → 列出；未登錄 → 該品項不出現（既有行為） |
| `no_official_season_registry` | 官方沒有該類別的產期登錄 | 每個縣市一律 `unknown`；頁面明示原因（§6.6） |

未來擴充（例如捕撈漁業的汛期）必須新增 registry entry + adapter，並在 PR 內附 S 級 discovery 證據；本 work order 不預留其他 enum 值。

### 6.3 季節地圖 payload `schema_version 1.1`

在 1.0 基礎上：

- 移除 `inputs.seasonality_source_status`，改為 `inputs.seasonality_sources`：物件，key 為 **catalog 中實際有 rows 的類別 id**，值為 `{"source_status": "live|stale|fallback"}`；不得為空。
- `inputs` 新增 `category_registry_hash`（`sha256:` + `config/produce-categories.json` 原始 bytes 的 hash）。
- 新增頂層 `categories`：陣列，依 registry 順序列出**全部**已登錄類別 `{"id","label","season_semantics","catalog_row_count"}`；`catalog_row_count` 為該類別在 catalog 中 (category, display_name) 的個數（catalog 層級，不是縣市層級），`no_official_season_registry` 類別必為 0。
- `counties[*].local_seasonal_produce[*]` 形狀不變；每列 `category` 必須已登錄，`source_status` 必須等於 `inputs.seasonality_sources[category].source_status`。
- 不變量：全部 rows 只能有**一個** `month`；**同一類別內**只能有一個 `source_status`（不同類別可不同 —— 這就是 TC-3 的解法）；`local_seasonal_produce` 仍依 `(category, display_name)` 排序且唯一；`additionalProperties: false` 維持。
- `schema/season-map.schema.json` 的 `category` enum 必須等於 registry 全部 id；新增 unit test 斷言兩者相等（schema 是靜態 JSON，registry 是唯一真相來源）。
- `verify_site` 與 `validate_data` 既有的「重建 payload 必須 byte-equal」檢查維持。

### 6.4 Extension catalog slot — `data/seasonality/extensions/<YYYY-MM>.json`

- 檔案**可不存在**（live 發布的常態）。存在時為 JSON list，每列欄位 = AFA catalog row 的全部欄位（`schema_version, month, canonical_id, display_name, source_display_names, category, counties, county_count, district_count, varieties, variety_count, source_url, source_status, fetched_at`）**加上** `source_id`。
- 驗證（fail closed，訊息需可診斷）：`category` 必須已登錄且 `season_semantics == official_season_registry`，且**不得**是 AFA 類別（`fruit`／`vegetable` 只能來自 AFA 路徑）；對 `no_official_season_registry` 類別的 rows 一律拒絕，錯誤訊息引用 `SPEC §6.2.6` 與 `Issue #44 BC-2`；`month` 等於請求月份；`source_status ∈ {live, stale, fallback}` 且同類別內單一；`source_id` 等於 registry 的 `season_source.source_id`；`source_url` https 且 host ∈ 該類別 `allowed_hosts`；`canonical_id` 必為 `null`（新類別不在 watchlist）；`display_name` 非空且 (category, display_name) 唯一；`counties` 為唯一非空字串 list 且 `county_count == len(counties)`。
- `build` 在 `seasonality_catalog()` 之後載入 extension rows，與 AFA catalog rows 合併後**沿用既有排序規則**（catalog list 以 `display_name` 排序；地圖以 `(category, display_name)`）；`site/data/current.json.season_catalog` 含 extension rows；`validate-data` 對存在的 extension 檔重跑 validator。
- `persist_seasonality`／`refresh_seasonality`／`seasonality_refresh_decision` 是 AFA 專屬，**不**讀 extension 檔。

### 6.5 圖示

- `produce_icons.CATEGORIES`、`FALLBACK_ICON_REGISTRY`、`_SAFE_SYMBOL_ID` 改由 registry 推導（regex 以 registry id 動態組成）。`PRODUCE_ICON_REGISTRY`（41 entries）維持不動。
- sprite 新增兩個 symbol：`produce-livestock-fallback`、`produce-aquaculture-fallback`；限制沿用 `validate_produce_icon_sprite`：`viewBox="0 0 24 24"`、`fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"`、只用允許的元素／屬性、無外部參照；sprite 總大小 ≤ 64 KiB；symbol 總數由 43 → 45。
- `cli._base_css` 新增 `.produce-icon--livestock`、`.produce-icon--aquaculture` 配色（沿用既有 token）。

### 6.6 頁面呈現（live 發布時的可見行為）

| 頁面 | 變更 | 不變 |
|---|---|---|
| `season/current.html` | 標題文案不變。分類篩選鈕：`全部／水果／蔬菜` 固定（`SPEC §11.7`），其他類別**只在 catalog 有該類別 rows 時**才出現；「共 N 項」摘要改為依 registry 順序列出有 rows 的類別數量。網格之後新增 `<section class='section' id='season-semantics' data-season-semantics>`，逐一列出 `no_official_season_registry` 類別的 `label`、`note`、`unknown` 標示與方法頁連結 | 卡片結構、搜尋、URL state、圖示契約 |
| `season/map.html` | intro 新增一則 `note warn`（`data-season-semantics-notice`）列出無官方登錄類別；每個縣市 section 的「本月當地盛產」在既有水果／蔬菜群組（或既有空狀態文字）之後加一行 `<p class='small' data-season-semantics-unknown>`：「畜產、養殖水產：無官方產地產期登錄，本站不判定當季或非當季（unknown）。」——這一行就是該縣市在矩陣中對這些類別的格子值；產期來源狀態行改為每類別列出 | 22 縣市 SVG、選單、URL／鍵盤／touch、既有空狀態文字 `農糧署本月產期資料未列出{縣市}的水果／蔬菜。`（browser test 依賴） |
| `methodology.html` | 新增「產季語意與類別」section：以 registry 產生表格（label、semantics、來源、note） | 其餘 |
| `index.html`、daily HTML／Markdown、trends、produce、traceability | **不變**（首頁區塊順序受 `SPEC §11.2` 固定；行情只有水果／蔬菜） | — |
| `assets/js/app.js` | `validCategories` 改由該 section 內 `[data-filter]` 的 `data-filter` 值推導，不再硬編 | 其餘行為 |
| `presentation.py` | 新增必要的內部代碼 → 人類文案對照（例如 `no_official_season_registry` → `無官方產期登錄`），JSON 契約不變 | — |

所有新文案為台灣繁體中文；所有來自 registry／catalog 的字串經 `_escape`。

---

## 7. 硬閘盤點與處置

| 位置（以函式為準，行號僅供定位） | 現況 | 處置 |
|---|---|---|
| `model.canonical_map` | `category not in ("fruit","vegetable")` raise | 改為：category 必須已登錄且 `market_watchlist=true`；訊息保留 `invalid category` 前綴 |
| `seasonality.CATEGORIES`（type=1/2） | AFA 專屬 | **保留**為 adapter-owned；`parse_page`／`fetch_category`／`build_catalog`／`map_catalog`／`seasonality_refresh_decision` 繼續只認 AFA 類別；加註解說明其為 AFA 契約而非全站類別 |
| `season_map.CATEGORIES`、`build_season_map_payload`、`validate_season_map_payload` | 二元 enum；single `source_status` | 依 §6.3 改為 registry 驅動與每類別 status；`load_season_map_config` 一併載入 registry 與其 hash |
| `season_map.load_official_market_registry` `market_kind` const | 單一常數 | **不變**（排除項） |
| `produce_icons.CATEGORIES`、`_SAFE_SYMBOL_ID`、`FALLBACK_ICON_REGISTRY`、`validate_produce_icon_registry`、`resolve_produce_icon` | 二元 | 依 §6.5 |
| `cli._base_js` `validCategories` | 硬編 set | 由 DOM 推導 |
| `cli.seasonality_catalog` | `category not in ('fruit','vegetable')` | registry id 集合 |
| `cli.persist_seasonality` LKG 逐類別計數、`catalog_lkg` 的 `=={'fruit','vegetable'}` | 字面 | 改用 `seasonality.CATEGORIES`（AFA-owned），語意不變 |
| `cli.build` | 只讀 AFA catalog | 合併 extension rows（§6.4）；把 registry hash 帶進 payload |
| `cli.verify_site` | 要求 `data-filter` fruit／vegetable；圖示 uses == catalog | fruit／vegetable 仍必要；另要求：有 rows 的其他類別才可有其篩選鈕、`data-season-semantics` section 存在、地圖 22 個 `data-season-semantics-unknown`（當且僅當 registry 含 `no_official_season_registry` 類別） |
| `cli.validate_data` | — | 驗證 extension 檔（若存在）、payload 1.1 |
| `cli.main validate-config` | 只算 fruit／vegetable 數量 | 另載入並驗證 registry、sprite fallback 覆蓋；輸出加入類別數 |
| `render._season_page`／`_season_map_produce_card`／`_recommendation_card`／`_produce_page`／`_home` 的 `'水果' if … else '蔬菜'` | 靜默降級 | 全部改 `category_label()`（未知 raise） |
| `render._season_page` 數量摘要與篩選鈕、`_season_map_county_section` 群組、`_season_map_page` intro、`_methodology` | 二元 | 依 §6.6 |
| `render._market_table`、`render_report` | 行情表只有 fruit／vegetable | 標題改用 `category_label()`；欄位邏輯不變 |
| `prototype.generate_market_rows` `種類代碼` | `N05`／`N04` 二元 | 對非 fruit／vegetable raise（8066 fixture 只服務 watchlist） |
| `schema/season-map.schema.json` | 1.0 | 1.1（§6.3） |
| `tests/browser/season-map.spec.mjs:213` 空狀態文字 | 依賴既有文字 | 文字不變；新增對 `data-season-semantics-unknown` 的斷言 |

---

## 8. 工作包（依序執行；同一時間最多兩個 implementer，且檔案集合不得重疊）

### WP-0 — Supervisor：基線與衝擊地圖

- 確認乾淨工作樹、`PYTHONPATH=src python3 -m unittest discover -s tests -t .` 為 `Ran 168 tests / OK`，並以 `find data reports site -type f -exec sha256sum {} + | sort | sha256sum` 確認前後 signature 相同。
- 用 `grep -rn -E "fruit|vegetable|水果|蔬菜|validCategories|seasonality_source_status" src schema tests config` 建立自己的衝擊清單，與 §7 比對；有出入以 grep 結果為準並記入 §12 回報。

### WP-1 — Implementer A：契約層

- 檔案：`config/produce-categories.json`、`schema/produce-categories.schema.json`、`src/tpw/categories.py`（新）、`src/tpw/model.py`、`src/tpw/produce_icons.py`、`src/tpw/assets/produce-icons.svg`、`src/tpw/season_map.py`、`schema/season-map.schema.json`、`src/tpw/seasonality.py`（僅：extension loader／validator，可放新模組 `src/tpw/season_extensions.py`；AFA 函式不動）、`tests/unit/test_categories.py`（新）、`tests/unit/test_season_map.py`、`tests/unit/test_produce_icons.py`、`tests/unit/test_model.py`、`tests/unit/test_season_extensions.py`（新）。
- 測試最少涵蓋：registry 全部驗證規則（含 `buy_score_eligible` 只允許 fruit／vegetable、`season_source` 若且唯若、重複 id／label、未知 enum、缺 fruit／vegetable）；`category_label` 未知 raise；payload 1.1 的每類別 status（跨類別不同 status 通過、同類別混用 raise、未登錄類別 raise、`categories[*].catalog_row_count` 正確、`inputs.seasonality_sources` 與 rows 一致、registry hash drift raise）；schema enum == registry ids；extension validator 每一條規則（尤其 `no_official_season_registry` rows 拒絕、AFA 類別拒絕、host 不在 allowlist 拒絕、`canonical_id` 非 null 拒絕）；icons：新 fallback 解析、regex 接受新 id、sprite 45 symbols 且 ⊇ registry fallbacks。
- Exit gate：`python3 -m unittest tests.unit.test_categories tests.unit.test_season_map tests.unit.test_produce_icons tests.unit.test_model tests.unit.test_season_extensions` 全綠；`unittest discover` 全套仍綠（此時 render／cli 尚未接上 1.1，若 `tests/integration/test_build.py` 因 payload 版本暫時失敗，必須在回報中列明並由 WP-2 收斂，不得跳過）。

### WP-2 — Implementer B：pipeline、render、CLI、browser（WP-1 完成後開始）

- 檔案：`src/tpw/cli.py`、`src/tpw/render.py`、`src/tpw/prototype.py`、`src/tpw/presentation.py`、`src/tpw/season_map_assets.py`（若需 CSS）、`tests/integration/test_build.py`、`tests/unit/test_presentation.py`、`tests/browser/season-map.spec.mjs`、`tests/browser/season-search.spec.mjs`。
- Integration 測試（全部在 per-test 暫存 repo 副本中）：(a) 無 extension 檔的 build：payload 1.1、`categories` 含四類且新類別 count 0、當季頁只有 fruit／vegetable 篩選鈕、`data-season-semantics` section 存在、地圖 22 個 `data-season-semantics-unknown`、`verify-site` 通過、雙次 build hash 相同；(b) 測試在副本中寫入**測試專用** registry 類別（例如 `{"id":"test_fishery","label":"測試漁產","season_semantics":"official_season_registry", …}`）與對應 extension 檔後 build：卡片、篩選鈕、圖示 fallback、地圖群組、`inputs.seasonality_sources` 兩種 status 並存，`verify-site`／`validate-data` 通過；(c) 對 `livestock` 寫 extension rows → build 失敗且既有 `data/`／`site/`／`reports/` 位元不變（LKG）；(d) 未登錄類別、schema 1.0 舊 payload 放進 `site/data/season-map/current.json` → `verify-site` 拒絕。
- Browser：更新 `season-map.spec.mjs`（若引用 `inputs.seasonality_source_status`）；新增對 intro notice、22 個 unknown 行、no-JS 仍可見的斷言；`season-search.spec.mjs` 確認 `category=livestock` 這種**無鈕**類別在 URL 中被視為 invalid → `all`。
- Exit gate：`unittest discover` 全綠且 publication signature 不變；在**scratch copy**（非 repo 根目錄）中執行 `seed-prototype --as-of 2026-08-25` → `build` → `tpw.presentation` → `validate-data` → `verify-site` → `npm run test:browser` 全綠。

### WP-3 — Supervisor（或 Implementer C）：committed publication 重建、版本、文件

- 版本：`src/tpw/__init__.py` `__version__ = "1.1.0"`。
- **重建 committed publication（live，不是 fixture）**：在 repo 根目錄、乾淨工作樹、**未執行 seed-prototype** 的前提下，鏡射 `daily-update.yml`「Build, normalize, and validate」：
  ```bash
  AS_OF="$(python3 -c 'import json,pathlib;print(json.loads(pathlib.Path("site/data/current.json").read_text())["as_of_date"])')"
  PYTHONPATH=src python3 -m tpw build --as-of "$AS_OF"
  PYTHONPATH=src python3 -m tpw.presentation
  PYTHONPATH=src python3 -m tpw validate-data --as-of "$AS_OF"
  PYTHONPATH=src python3 -m tpw verify-site --as-of "$AS_OF"
  ```
  之後再跑一次同樣四步，`site/`＋`reports/`＋`data/` 的 signature 必須與第一次相同（AC-010）。預期變動只在 `site/data/season-map/current.json`、`site/season/*.html`、`site/methodology.html`、`site/assets/{css,js}/*`、`site/index.html` footer 版本、`site/data/current.json`（若 catalog 形狀有變）與對應 `data/` 衍生檔；`data/market/**`、`data/seasonality/catalog/**` 不得變動。任何超出預期的 diff 都要在 §12 解釋。
- 對重建後的 publication 跑 `daily-update.yml` 後三個 gate：全套 unittest + signature 比對、`npm run test:browser`、兩個 `du` cap；另跑 `ci.yml` 的 secret pattern：`! rg -n 'AKIA|ghp_|glpat-|github_pat_|BEGIN PRIVATE KEY|base64,' site`。
- 文件：
  - `CHANGELOG.md` 新增 `## [1.1.0] — <日期>`：Added（類別 registry、extension slot、地圖 `categories` 軸、兩個 fallback 圖示）、Changed（season-map payload 1.1 欄位變動、15 處硬閘改 registry 驅動、未知類別 loud failure）、Unchanged（SPEC hash、Buy Score、watchlist、資料語意）、文件版本對應表。
  - `README.md`：原型功能表新增 `Issue #44 Part B · 多類別產季語意` 一列；資料信任邊界新增三點（畜產／養殖水產矩陣格子一律 unknown 且原因、extension slot 規則與 HITL、BC-5 維持）；Repository anatomy 補 `config/produce-categories.json`／`schema/produce-categories.schema.json`；CLI 表 `validate-config` 說明；狀態段新增 Part B 一行；`/season/map.html` 路由說明補「畜產／養殖水產 unknown」。
  - `VERIFICATION.md` 頂端新增 `## v1.1.0 — Issue #44 Part B — <日期>`：Verified locally（每條命令與實際輸出計數）、Artifact integrity（SPEC／reference hash）、Unverified（live 來源、remote runs 留給 orchestrator 補）、Explicit limits（§5 排除項逐條）。
  - `TASKS.md`：新增 `T-301`～`T-30x`（對應 WP-1～WP-3 與 D-1～D-9，附 requirement IDs：FR-003、NFR-001、NFR-003、NFR-004、NFR-008、NFR-010、AC-010），只在有證據時打勾；front matter version → 1.1.0。
  - `PLAN.md`：front matter `version: 1.1.0`、`status` 補一句；§2 target outcome 追加第 14 點（多類別產季語意）。
  - `DISCOVERY.md`：依 §13 追加續篇。
- Exit gate：§10 全部門檻通過；`git status --porcelain` 只含預期檔案；`git diff --stat` 附在回報。

---

## 9. 執行契約

1. 全程 deterministic：排序穩定、序列化用既有 `write_json`／`json.dumps(sort_keys=True, separators=(',',':'))`；不引入時間戳到 stable hash。
2. 測試 hermetic：驅動 CLI 的測試必須沿用 `tests/integration/test_build.py` 的暫存 repo 副本模式；跑完 `unittest discover` 後 publication signature 必須不變。
3. 不在 repo 根目錄執行 `seed-prototype`；需要 fixture site 時用 scratch copy。
4. Fail closed：新增的每一條驗證都要有一個對應的負向測試。
5. 錯誤訊息可診斷（指出欄位與原因），不吞例外。
6. 文案為台灣繁體中文；upstream／registry 字串一律 escape。
7. 文件中的每一句「已完成」都要能在 `VERIFICATION.md` 找到命令與結果；沒有證據就寫「unverified」。
8. 遇到本文件未涵蓋的設計歧義：選擇**最窄、最 fail-closed** 的解讀，並在 §12「Review focus」列出；遇到需要放寬既有 gate 或改 SPEC 才能繼續的情況：**停止並回報 blocker**，不得繞過。

---

## 10. 驗收門檻（Acceptance 獨立重跑；任一失敗即 FAIL）

| ID | 命令／檢查 | 預期 |
|---|---|---|
| G-1 | `sha256sum SPEC.md "references/00965_deep_analysis_20260826(1).html"` | `2be4f623…`、`bd2ddaeb…` |
| G-2 | `PYTHONPATH=src python3 -m compileall -q src tests` | 無輸出 |
| G-3 | signature 前後 + `PYTHONPATH=src python3 -m unittest discover -s tests -t .` | OK；測試數 > 168；signature 相同 |
| G-4 | `PYTHONPATH=src python3 -m tpw validate-config` | 通過，輸出含類別數 |
| G-5 | `validate-market-calendar --year 2026`、`validate-agent-run tests/fixtures/agent-run.valid.json`、`validate-traceability`、`validate-traceability-events` | 通過 |
| G-6 | 對 committed publication：`validate-data --as-of $AS_OF`、`verify-site --as-of $AS_OF` | 通過 |
| G-7 | 對 committed publication 重跑 §8 WP-3 四步 → signature 與 HEAD 相同（idempotent，模擬 merge 後 daily-update push run 應為 `No content changes`） | 相同 |
| G-8 | scratch copy：`seed-prototype --as-of 2026-08-25` → `validate-source-run --date 2026-08-25` → 全套 unittest → signature 比對 → `build` → `presentation` → `validate-traceability` → `validate-traceability-events` → `validate-data` → `verify-site` → `npm run test:browser` → 兩個 `du` cap → secret `rg`（即 `ci.yml` 順序） | 全綠 |
| G-9 | `npm run test:browser` 對 committed publication（repo 根目錄 `site/`） | 全綠 |
| G-10 | `python3 -c "import json;json.load(open('site/data/season-map/current.json'))"` 後檢查：`schema_version=="1.1"`、`categories` 四項且 livestock／aquaculture `catalog_row_count==0`、`inputs.seasonality_sources` 只含 fruit／vegetable、無 `seasonality_source_status` | 符合 |
| G-11 | `grep -rn -E "'水果' if|\(\"fruit\", ?\"vegetable\"\)|\('fruit', ?'vegetable'\)|\{'fruit', ?'vegetable'\}|validCategories=new Set" src` | 只剩 `seasonality.py` 的 AFA 契約與 `prototype.py` 的 8066 fixture 分支（各自有註解說明） |
| G-12 | `git diff --name-only HEAD~N -- data/market data/seasonality/catalog config/produce.yml SPEC.md` | 空 |
| G-13 | 對 `livestock` 寫 extension rows 的負向測試存在且通過；schema enum == registry ids 測試存在 | 存在 |
| G-14 | README／CHANGELOG／VERIFICATION／TASKS／PLAN 的每一項聲稱都能對應到 G-3～G-10 的輸出；無 model 名稱；無簡體中文 | 一致 |
| G-15 | `git diff` 中不存在任何畜產／水產的產期、縣市、月份或價格數值 | 不存在 |

---

## 11. Supervisor 跨檔案確認清單（回報前逐條勾）

- [ ] §7 每一列都有對應 diff 或明確「不變」理由。
- [ ] `render.py` 沒有任何殘留的類別三元式；`category_label` 未知輸入 raise 有測試。
- [ ] `season_map.py`、`schema/season-map.schema.json`、`render._season_map_county_section`、`tests/unit/test_season_map.py`、`tests/integration/test_build.py`、`tests/browser/season-map.spec.mjs` 對 payload 1.1 的欄位名完全一致（grep `seasonality_sources`、`category_registry_hash`、`catalog_row_count`）。
- [ ] `verify_site` 的新檢查與 `render` 的新 data attribute 名稱一致（`data-season-semantics`、`data-season-semantics-notice`、`data-season-semantics-unknown`）。
- [ ] `cli._base_js` 的 `validCategories` 推導在沒有 `[data-filter]` 的頁面不會拋錯。
- [ ] sprite：`validate_produce_icon_sprite` 通過、45 symbols、`site/assets/icons/produce.svg` 重建後與 `src/tpw/assets/produce-icons.svg` 位元相同。
- [ ] `tests/` 未寫入 publication（signature）；沒有任何測試被刪除、`skip`、放寬斷言；測試總數增加並列出新增測試名。
- [ ] `config/produce.yml`、`data/market/**`、`data/seasonality/catalog/**`、`SPEC.md`、`references/**`、workflow 檔皆無 diff。
- [ ] 所有新增文案為繁體中文；沒有 model 名稱。
- [ ] `VERIFICATION.md` 的每個數字（測試數、symbol 數、browser passed 數）與實際輸出一致。

---

## 12. Supervisor 回報格式（精確六節，勿多勿少）

1. **Summary** — Part B 現在做到什麼；live 發布上使用者會看到的差異。
2. **Changed** — 關鍵檔案／模組與理由（不要整檔傾印）；`git diff --stat`。
3. **Validation** — §10 每一條命令與實際輸出（測試數、passed 數、hash）。
4. **Requirement & constraint evidence** — FR-003、NFR-001、NFR-003、NFR-004、NFR-008、NFR-010、AC-010；BC-2、BC-4、BC-5、BC-7；TC-2、TC-3 各自對應到哪個測試或檢查。
5. **Unverified or blocked** — live 來源（§13 全部）、remote runs、任何未能完成的 WP 與原因。
6. **Review focus** — 最高風險處（例如 payload 1.1 對 browser test 的影響、registry 驅動 regex、extension merge 的排序）。

不得只因檔案存在就宣稱完成；完成的定義是 §10 全部通過且證據已寫入 `VERIFICATION.md`。

---

## 13. DISCOVERY.md 續篇規格（WP-3 撰寫；只記事實，不補造）

標題：`## Issue #44 Part B — bounded discovery attempt — 2026-09-04`。內容：

1. **本次環境證據（S 級，關於封鎖本身）**：對 §1 列出的每個 host 執行 `curl -sS -o /dev/null -m 20 -w '%{http_code} %{content_type}\n' <url>` 的實際結果（`CONNECT tunnel failed, response 403`）與 proxy `recentRelayFailures` 中的 `connect_rejected` 紀錄；標明時間與 host。
2. **候選來源表（全部 A／B 級，未一手讀取）**，每列含 URL、等級、對應 B-4 題號、單一 bounded probe 該記錄的東西：

| 對應 B-4 | 來源 | 等級 | 一次 bounded probe 應記錄 |
|---|---|---|---|
| Q6 | 農糧署「每月盛產農產品產地」：`https://data.gov.tw/dataset/8120`、`https://data.moa.gov.tw/open_detail.aspx?id=061`（搜尋摘要：欄位 類別／盛產月份／名稱／品種名稱／主要生產-縣市別／主要生產-鄉鎮市別；摘要另稱 2016 年後未更新，**待查證**） | A（URL）／B（欄位、更新狀態） | HTTP status、Content-Type、bytes、`類別` 欄位的**全部 distinct 值**、最新資料月份、SHA-256 |
| Q6 | AFA `https://www.afa.gov.tw/cht/index.php?code=list&ids=1103&mod_code=search` 的 `type` 選項全集 | A | 頁面 `種類` 選單全部 option label／value |
| Q7 | 漁業署「漁業月曆」`https://fa.gov.tw/list.php?subtheme=1813&theme=web_structure` | A（URL）／B（內容性質未知） | 是否為 (魚種 × 月份[× 縣市]) 結構化資料或僅敘述；授權條款 |
| Q7 | 農業部食農教育資訊整合平臺 `https://fae.moa.gov.tw/`（搜尋摘要：含水產「當季食材」敘述，如飛魚 3–7 月） | A／B | 是否有結構化欄位、是否含縣市、授權；**敘述性內容不得寫入正式 mapping（BC-7）** |
| Q1、Q4、Q5 | 漁產品交易行情：`https://data.gov.tw/dataset/7299`、`https://data.moa.gov.tw/open_detail.aspx?id=039`；市場站 `https://efish.fa.gov.tw/efish/`（搜尋摘要欄位：交易日期、品種代碼、魚貨名稱、市場名稱、上價、中價、下價、交易量、平均價；單位**未證**） | A／B | endpoint、分頁參數、日期格式、價格與交易量單位、市場代號與品種代碼格式（與 8066 三位數市場代號、作物代號是否碰撞） |
| Q2、Q4、Q5 | 毛豬交易行情：`https://data.gov.tw/dataset/7296`、`https://data.moa.gov.tw/open_detail.aspx?id=026`（搜尋摘要：交易日期、市場名稱、頭數、平均重量 公斤、平均價格 元/公斤；來源系統 `ppg.naif.org.tw`） | A／B | 同上；確認是否為 元/公斤 或 元/百公斤 |
| Q3、Q4 | 家禽交易行情（白肉雞／雞蛋）：`https://data.moa.gov.tw/open_detail.aspx?id=056`；畜產會 `https://www.naif.org.tw/` | A／B | 欄位、單位、授權（畜產會為財團法人，非主管機關 open data） |
| Q8 | 農業部畜牧處相關頁（搜尋摘要僅見「夏季蛋量自然減少」等敘述） | B | 是否存在任何官方「產期／產季」定義；預期：不存在（BC-2） |

3. **結論句**：本次仍未取得任何 S 級證據；Part B 的 live 切片（新類別 season adapter、行情 adapter）維持 blocked，需在具 `*.gov.tw` egress 的環境逐條完成上表 probe 後另開 work order。

---

## 14. 需要人工決定、但不阻塞本 work order 的事項（orchestrator 於 issue 留言提出）

1. BC-5：若日後要讓畜產／水產進入推薦排名，需正式修訂 `SPEC.md §9.2.1` 並解除 hash 釘住；本 work order 以 validator 把 `buy_score_eligible` 釘在 fruit／vegetable。
2. 是否授權在具 egress 的環境執行 §13 的 bounded probes，並依結果決定 `aquaculture`（或新增 `fishery`）是否升級為 `official_season_registry`。
3. 行情（語意 1）擴充：TC-1 單位與 TC-4 命名空間的處理原則（例如以 `dataset_semantics` 隔離、單位欄位化），需在 probe 之後另開 PLAN／work order。
