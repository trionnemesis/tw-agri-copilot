# Prototype verification evidence

## v1.1.0 — Issue #44 Part B — 2026-09-04

環境：Python 3.11.15、Node 22、`PYTHONPATH=src`、無網路（所有 `*.gov.tw` egress 封鎖）。版本：`src/tpw/__init__.py` `__version__ = "1.1.0"`。

### Verified locally

- `PYTHONPATH=src python3 -m compileall -q src tests` — 無輸出。
- Baseline（`main` @ `a87a722`）— `Ran 168 tests` / `OK`；本分支 — `Ran 258 tests` / `OK`（+90；91 個新增測試方法，其中 1 個為更嚴格的改名：`test_duplicate_county_produce_conflict_fails_closed` → `test_duplicate_category_display_name_in_catalog_fails_closed`）。Publication signature 於該次測試前後皆為
  `f6818e79871908884353c71e2ef09c87ce4d7c296f7b2f33d90270e82ca2b0dc` — 測試套件未寫入 publication。
- `validate-config` — `config valid: 20 mapped items, 22 counties, 2 verified markets, 4 produce categories`；`validate-market-calendar --year 2026` — `valid market calendar: 2026 115-114.07.30-fruit-vegetable`；`validate-agent-run tests/fixtures/agent-run.valid.json` — `agent run valid: 1`；`validate-traceability` — `valid traceability registry: fixture 5`；`validate-traceability-events` — `valid traceability market events: fixture 5`。
- Committed publication 重建（repo 根目錄，`AS_OF=2026-09-03` 讀自 `site/data/current.json`，未執行 `seed-prototype`，鏡射 `daily-update.yml` 的「Build, normalize, and validate」步驟，共執行兩次）：`build` — `build promoted safely`；`python3 -m tpw.presentation` — `presentation 2026-08-30.1 normalized: 55 files`；`validate-data` — `data valid`；`verify-site` — `site verified`。Signature：重建前（與 `main` @ `a87a722` 相同）= `b28c66e1147d470d4203b950e2e7b0ba78f056e63eff7caab199908bef06f47f`；第一次重建後 = `f6818e79871908884353c71e2ef09c87ce4d7c296f7b2f33d90270e82ca2b0dc`；第二次重建後 = 相同 → idempotent（`AC-010`）。Merge 後 `daily-update.yml` 的 push run（#58 attempt 1）未產生 content commit，與此預測一致；但該 run 於 2026-09-05 02:45 UTC（台北 10:45，落在 README 記載的 morning-recovery 窗口）被重跑為 attempt 2，依 recovery 路徑實際抓取上游後提交 `dba7746`（30 檔案）。詳見下方 Remote evidence。
- Scratch copy，完整 `ci.yml` 順序：`compileall` 無輸出；`validate-config`／`validate-market-calendar`／`validate-agent-run` 通過；對 committed publication 執行 `verify-site` + `validate-data` 通過；`seed-prototype --as-of 2026-08-25` — `seeded normalized rows: 1400`；`validate-source-run --date 2026-08-25` — `valid source run: 2026-07-22 2026-08-25 1`；完整套件 — `Ran 258 tests` / `OK`，signature `eafadf7ea85b3619a62c1a64c5dbfe6c1409e4129daaf26e3c7e6627a3696a40` 測試前後相同；`seed-prototype` → `build` → `presentation`（54 files）→ `validate-traceability` → `validate-traceability-events` → `validate-data` → `verify-site` 全部通過；`npm run test:browser` — `33 passed, 1 skipped`；`du -sm site` = 1（≤900）；`du -sm --exclude=.git .` = 8（≤900）；secret-pattern `rg 'AKIA|ghp_|glpat-|github_pat_|BEGIN PRIVATE KEY|base64,' site` — 無命中。
- `npm run test:browser` 對 committed publication（repo 根目錄 `site/`）— `33 passed, 1 skipped`（baseline 為 `31 passed, 1 skipped`；+2 為新的 season-semantics spec 在 desktop／mobile 兩個 project 各跑一次）；publication signature 不變（`f6818e79…`）；`test-results/` 事後已移除。
- `site/data/season-map/current.json` 重建後檢查：`schema_version` 為 `1.1`；`categories` = `[(fruit, official_season_registry, 20), (vegetable, official_season_registry, 19), (livestock, no_official_season_registry, 0), (aquaculture, no_official_season_registry, 0)]`；`inputs.seasonality_sources` = `{fruit: live, vegetable: live}`；`inputs.category_registry_hash` = `sha256:ed8e9fef8021c6f622bc9b9ee51dc6335c58b9e329415284a360caaf5211c77a`；`inputs.seasonality_source_status` 已不存在；`counties` 區塊與重建前位元相同；`seasonality_snapshot_hash` 不變（無 extension 檔存在，merge 為 no-op）。
- `grep -rn -E "'水果' if|\("fruit", ?"vegetable"\)|\('fruit', ?'vegetable'\)|\{'fruit', ?'vegetable'\}|validCategories=new Set" src` — 只有一處命中：`src/tpw/categories.py:50` 的 `_REQUIRED_WATCHLIST_CATEGORIES = ("fruit", "vegetable")`，是附註解的 `SPEC.md §9.2.1`／`§7.2.5` 釘住，並非靜默降級。
- `git diff --name-only a87a722 -- data/market data/seasonality/catalog config/produce.yml SPEC.md references .github` — 空；`data/**` 與 `reports/**` 對 `a87a722` 整體零 diff。
- 圖示覆蓋率（`daily-update.yml` 方法）：`season_catalog` 39 列，未覆蓋 0 個；sprite 45 symbols（41 個 registry entry + 4 個分類 fallback），14394 bytes（≤ 64 KiB）；`site/assets/icons/produce.svg` 與 `src/tpw/assets/produce-icons.svg` 位元相同。
- 重建後 publication diff（僅 `site/`）：`assets/css/app.css`（+`.produce-icon--livestock`／`--aquaculture`）、`assets/icons/produce.svg`（+2 symbols）、`assets/js/app.js`（分類集合改由 `[data-filter]` 推導）、`data/season-map/current.json`（`1.0` → `1.1`）、`index.html`（僅 footer 版本 `v1.0.0` → `v1.1.0`）、`methodology.html`（+「產季語意與類別」section）、`season/current.html`（+「產季語意」section）、`season/map.html`（intro notice + 22 行 unknown + 每類別來源狀態）。`site/data/current.json` 不變。
- 當季頁摘要行逐位元不變：`共 39 項：水果 20 項、蔬菜 19 項。`
- 新增測試：`test_categories.py` 32、`test_season_extensions.py` 35、`test_season_map.py` +7（+1 改名）、`test_season_source_notice.py` 6（新檔）、`test_produce_icons.py` +4、`test_model.py` +1、`test_build.py` +5（情境 a／b／c／d + 一個 registry-threading guard）；browser +1 spec「the intro notice and every county carry the no-official-season-registry explainer」（desktop／mobile 兩個 project 各一次）。
- `git diff --stat a87a722..985efd0`：37 files changed, 2504 insertions(+), 146 deletions(-)；其中程式／schema／設定／測試／`site/` 部分（即排除 `WORK_ORDER_PART_B.md`、`README.md`、`CHANGELOG.md`、`VERIFICATION.md`、`TASKS.md`、`PLAN.md`、`DISCOVERY.md` 七份 Markdown 文件）為 30 files changed, 1967 insertions(+), 132 deletions(-)。新增：`config/produce-categories.json`、`schema/produce-categories.schema.json`、`src/tpw/categories.py`、`src/tpw/season_extensions.py`、`tests/unit/test_categories.py`、`tests/unit/test_season_extensions.py`；修改：`schema/season-map.schema.json`、`src/tpw/{render,season_map,cli,produce_icons,prototype,model,seasonality,__init__}.py`、`src/tpw/assets/produce-icons.svg`、`tests/integration/test_build.py`、`tests/unit/{test_season_map,test_produce_icons,test_model}.py`、`tests/browser/{season-map,season-search}.spec.mjs`、`site/` 下 8 個檔案。

- PR #47 的自動化 code review（P2 兩則）已修正並各自留下測試：（A）`render._season_source_notice` 先前只讀 `rows[0]`，異質 merged catalog（AFA `live` + extension `stale`）會用單一狀態與 AFA 來源描述整份清單；現改為依 `(source_status, source_url)` 分組、以每組最低 registry rank 排序，單一分組時輸出與改版前**逐位元相同**（`tests/unit/test_season_source_notice.py` 6 個測試，其中 4 個以完整字串 `assertEqual` 鎖住輸出；整合情境 (a) 斷言兩個頁面各恰一則未標註 notice，情境 (b) 斷言 `live`／`fruit,vegetable` 與 `stale`／`test_fishery` 兩則並存且帶類別前綴）。（B）`season_extensions.validate_extension_rows` 的 `county_count`／`variety_count` 先前接受 `True`／`1.0`；現統一經 `_nonnegative_int()` 拒絕 bool、非 int 與負值（`county_count`／`variety_count`／`district_count` 各 3 個負向測試；`season_map` 的 `catalog_row_count` 原已排除 bool，另補一個負向測試）。修正後於 repo 根目錄重跑一次 live 四步重建，`site/` 位元不變（`git status` 無 `site/` 項目），`npm run test:browser` 仍為 `33 passed, 1 skipped`。

**Documented deviation.** `cli.ingest_sources` 仍以預設（default）類別 registry 呼叫 `canonical_map`，而不是 `tpw.cli` 其餘各處使用的、以顯式 `ROOT` 載入的 registry。這是安全的：registry validator 強制 `fruit`／`vegetable` 必須維持為 official watchlist 類別，因此**任何合法 registry 的 watchlist 都是 `{fruit, vegetable}` 的超集**；而 `config/produce.yml` 從未設定 `fruit`／`vegetable` 以外的類別，所以 `canonical_map` 的閘門在預設 registry 與 `ROOT` registry 之下判定結果完全相同。

### Artifact integrity

Hash-pinned inputs are unchanged by this release:

- SPEC.md: `2be4f623cf882eca7302d41702ecf53a23564e8f82753a7f82d404f617858ff6`
- reference HTML: `bd2ddaeb4a1ce1431d27ad5901310e0abd1a30a9cd8d8f4725f60f78a1b2e7dd`

### Remote evidence

Merge `2963922` 後由 GitHub Actions 產生，全部經 API 逐一查證（非引用他處摘要）：

- [`Fixture CI` #299](https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33905991927) — success（attempt 1）。
- [`Deploy Pages` #26](https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33905991892) — success（attempt 1）。
- [`Daily market update` #58](https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33905992037) — success。**該 run 目前為 attempt 2**：`Fetch bounded rolling windows` 與 `Refresh seasonality and 7556 registry` 皆為 `success` 而非 skipped，`Refresh H44` skipped，即 README 記載的 morning-recovery 路徑。gate 逐項結果：測試套件 gate success；browser suite `33 passed`／`1 skipped`；size guard success；`Produce icon coverage: 39/39.`；commit 步驟輸出 `[main dba7746] data: daily market update`、`30 files changed`，並推送 `2963922..dba7746`。`deploy` job Pages 部署成功。

`2963922` 之後 `main` 上僅有 `dba7746` 一個 daily commit，時間戳與 attempt 2 的 log 一致，因此 attempt 1 未提交內容。

### Unverified for this release

- Work order §13 列出的全部候選來源：無 S 級證據；所有 `*.gov.tw` egress 封鎖（見 `DISCOVERY.md` 的 Part B 續篇）。
- 畜產與養殖水產未新增任何 live season 或行情 adapter；兩者在每個縣市矩陣格子中維持 `unknown`。

### Explicit limits

- 不編輯或擴張 `SPEC.md`；SHA-256 維持 `2be4f623…` 未變動；`references/*.html` 維持 `bd2ddaeb…`。
- 未新增任何 live adapter（畜產／水產產期或行情）；未對 `*.gov.tw` 或任何外部來源發出請求；required tests 不依賴 live API。
- 未把畜產／水產加入 `config/produce.yml` watchlist；未新增第二種 `dataset_semantics` 的行情資料；未處理 TC-1 單位、TC-4 代號命名空間、TC-5 `market_kind`／`MARKET_HOST_ALLOWLIST`（`official-produce-markets` 契約原封不動）。
- 未改動 Buy Score、eligibility、verdict 或 `scoring.yml`（BC-5 由 registry validator 維持）。
- 未 commit 任何畜產／水產的產期、縣市、月份或行情數值，包括 fixture 或 manual fallback。
- 未新增 fuzzy matching；未新增 runtime 外連資源、CDN 或 data URI。
- 未變更 workflow 的 trigger／schedule／permissions。
- 未刪除、跳過或弱化既有測試；未放寬既有 fail-closed 條件；未在 repo 根目錄執行 `seed-prototype`。
- 未建立 Git commit、push、PR，未變更 GitHub 設定，未部署 Pages。


## v1.0.0 — Issue #44 Part A — 2026-09-04

### Verified locally

- `PYTHONPATH=src python3 -m compileall -q src tests` — clean.
- `PYTHONPATH=src python3 -m unittest discover -s tests -t .` — `Ran 168 tests` / `OK`.
- `git status --porcelain` compared either side of that run — identical, so the suite no longer
  writes to `data/`, `site/` or `reports/`. Before the fix the same run left **126 modified tracked
  files** plus 6 untracked artifacts, replacing live prices with prototype fixture values.
- `PYTHONPATH=src python3 -m unittest tests.unit.test_produce_icons` standalone — `Ran 6 tests` / `OK`.
  Before the fix this failed with `published` holding `('fruit','葡萄柚')` and `('fruit','芒果')`
  while the registry held `('fruit','龍眼')` and `('fruit','高接梨')`, and passed only under
  `unittest discover` because an earlier integration test had rewritten `site/data/current.json`
  to the August fixture first.
- CI order simulated in a scratch copy: `seed-prototype --as-of 2026-08-25` →
  `validate-source-run --date 2026-08-25` → full suite → tree-comparison guard — guard passes.
- `validate-config` (20 mapped items, 22 counties, 2 verified markets), `validate-market-calendar
  --year 2026`, `validate-agent-run tests/fixtures/agent-run.valid.json`, `validate-traceability`,
  `validate-traceability-events`, `validate-data --as-of 2026-09-03`, `verify-site` — all pass.
- `npm run test:browser` (Playwright, chromium desktop + mobile) against the fixture rebuild —
  `31 passed, 1 skipped`; against the committed live publication — `31 passed`.
- The widened icon-fidelity assertion was verified both ways: with one live season card injected
  as `category_fallback`, `season-search.spec.mjs` gives `6 passed`, and the original
  `['exact','representative']` assertion gives `1 failed`. Without that change the new daily
  browser gate would have blocked a publication over a decorative icon gap.
- `verify-site` and `validate-data --as-of 2026-09-03` run against the checkout *before*
  `seed-prototype` replaces `data/` — reproduced that `seed-prototype` alone leaves 38 dirty
  paths under `data/` and none under `site/`, so every later check in `ci.yml` had been seeing
  the August fixture rather than the committed publication.
- AC-010 idempotency on the live publication: `build --as-of 2026-09-03` → `tpw.presentation` →
  `enhance_price_trends()` run twice produced an identical aggregate hash over `site/` and
  `reports/` (`0b3bd654…`).
- Workflow YAML parsed with `yaml.safe_load` for `ci.yml` and `daily-update.yml`.
- Published homepage footer carries the release version after presentation rewriting:
  `Taiwan Produce Watch · 台灣蔬果公開資料觀察 · v1.0.0`.
- Produce icon coverage on the published catalogue: 39/39.

### Artifact integrity

Hash-pinned inputs are unchanged by this release:

- SPEC.md: `2be4f623cf882eca7302d41702ecf53a23564e8f82753a7f82d404f617858ff6`
- reference HTML: `bd2ddaeb4a1ce1431d27ad5901310e0abd1a30a9cd8d8f4725f60f78a1b2e7dd`

### Remote evidence

Merging #45 as `df81f55` triggered the push path of `daily-update.yml`, which is the first remote
execution of the pre-push gates added by this release.

`Daily market update` run #54 — success
(https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33835384821):

- `Run the repository test suite against the publication` — success. Run #54 ran the original form
  of this guard, which compared `git status --porcelain` either side of the suite, so its success
  proves the suite added, removed and re-statused nothing under the publication trees. It does not
  prove content equality: porcelain reports status codes and pathnames only, so a test overwriting
  a file the build had already modified would have left it byte-identical. Reproduced directly — a
  live `site/data/current.json` written by the build and then replaced with fixture values keeps
  the porcelain output ` M site/data/current.json` on both sides. The guard now compares a
  sha256 signature of every file under `data/`, `reports/` and `site/` instead; that stronger form
  has no remote evidence yet.
- `Run the browser suite against the publication` — `31 passed`, `1 skipped`, run against the built
  publication rather than the fixture rebuild.
- `Guard the published size` — success, both `du` caps.
- `Report produce icon coverage` — `Produce icon coverage: 39/39.`
- `Commit changed content to main` — `No content changes`.
- `deploy` job — Pages deployment successful.

`Fixture CI` run #275 on `main` — success
(https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33835384855), including the new step
that validates the committed publication before `seed-prototype` replaces it. This is the first
green CI recorded on `main` since 2026-09-01.

`Deploy Pages` run #25 — success
(https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33835384836).

`Fixture CI` run #278 — success
(https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33841026727), the first remote run of
the content-hash form of the publication guard (`Run the test suite and prove it leaves the
publication untouched`) and of the committed-publication validation that now runs ahead of
`seed-prototype`.

### Unverified for this release

- No live 8066, seasonality, 7556 or H44 fetch was performed anywhere in this release. Run #54 was
  a `push` event, so its refresh steps were skipped by design and the gates ran against a build
  from committed normalized history. *(Superseded after this release: scheduled runs
  [#56](https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33842043784) and
  [#57](https://github.com/trionnemesis/tw-agri-copilot/actions/runs/33883459760), both on
  `a87a722`, did fetch upstream first — `Fetch bounded rolling windows`, `Refresh seasonality and
  7556 registry` and, on #57, `Refresh H44` all ran — and every gate passed.)*
- The `ci.yml` schedule (`cron: '40 22 * * *'`) has not fired yet; only its push and pull_request
  paths have remote runtime evidence.
- The content-hash guard's *negative* case has local evidence only. Run #278 shows it passing on
  the hermetic suite; that it catches the overwrite case the status-only form missed was verified
  in a scratch copy, and no remote run has been made to fail on purpose.
- Part B of Issue #44 (livestock and aquaculture seasonality) is untouched and remains at Phase 1.


## Scheduler missing/delayed recovery — 2026-08-29

- 19:30 Asia/Taipei 的公開 Actions evidence 顯示：18:17 primary scheduled run 未建立；最近 scheduled run 仍為 `33211062672`（2026-08-29 05:05 Asia/Taipei）。Workflow 位於 default branch、GitHub API 狀態為 active，09:17／18:17 timezone-aware cron 與 H44 evening condition 均存在。公開 evidence 無法再判定 GitHub 內部未 enqueue 的確切原因。
- 新增獨立 09:47／18:47 `Daily update scheduler guard`。它查詢同一 primary 時段的 `schedule` runs；queued、in progress、success、failure 都代表 primary 已嘗試，guard 不 dispatch。只有 run 完全不存在才建立 `morning-recovery`／`evening-recovery` `workflow_dispatch`。
- Recovery 沿用 scheduled fallback semantics：09:47 recovery 會更新 7556 requested-date evidence、跳過 H44；18:47 recovery 會更新 7556 並執行 H44。手動 dispatch 的既有預設仍執行 H44。
- Guard 只取得 `contents: read`／`actions: write`，API 或時區判定異常時 fail closed；超過 primary 四小時不補跑舊日期。外部 ChatGPT verifier 維持唯讀。
- 使用 2026-08-29 19:30 Asia/Taipei 與公開 workflow run 清單重播 decision，結果為 `dispatch`，payload 僅含 `ref=main`、`as_of_date=2026-08-29`、`schedule_slot=evening-recovery`；本地驗證未實際觸發遠端 workflow。

~~~text
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
Ran 127 tests
OK

PYTHONPATH=src python3 -m tpw validate-traceability
valid traceability registry: fixture 5
PYTHONPATH=src python3 -m tpw validate-traceability-events
valid traceability market events: fixture 5

PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-27
data valid
PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-27
site verified
~~~

此 evidence 只驗證 recovery decision、workflow contract 與既有資料邊界；在 PR 合併且下一個 guard slot 實際執行前，不宣稱 remote recovery runtime 已成功。

## Issue #3 Traceability PR B — 2026-08-28

- 農業部 H44 adapter 使用單日 `StartDate`／`EndDate` 與 bounded `$top`／`$skip` pagination，檢查 HTTP、Content-Type、JSON collection、8 個官方欄位、日期、非負有限數值、重複頁、最大頁數與 content hash。
- 公開事件保留日期、市場、作物、交易金額、交易量與官方溯源代號；event identity 是完整官方欄位的 SHA-256。溯源代號不會被解讀為 7556 `Tracecode`。
- H44 固定為 `authoritative_market_event`／`traceability_market_event`，profile 與每列皆有 `eligible_for_market_aggregate=false`、`affects_buy_score=false`；Pages 以 `/traceability/market-events.html` 與獨立區塊呈現。
- Contract／unit／integration tests 覆蓋 bounded 日期分頁、empty／HTML／non-JSON、retry、schema／日期／數值漂移、exact mapping、exact duplicate、unknown item、80% count regression、atomic preservation 與 same-source LKG。

~~~text
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
Ran 111 tests
OK

PYTHONPATH=src python3 -m tpw validate-traceability
valid traceability registry: fixture 5
PYTHONPATH=src python3 -m tpw validate-traceability-events
valid traceability market events: fixture 5

PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-26
data valid
PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-26
site verified
~~~

Committed H44 artifacts intentionally remain `fixture`; the endpoint and schema are based on the official H44 source description, but this verification does not claim a successful live H44 fetch, merge to `main`, or deployment to the public Pages site.

## Issue #3 Traceability PR A — 2026-08-28

- 農業部 7556 registry adapter 使用 bounded `$top`／`$skip` pagination，並檢查 HTTP、Content-Type、JSON collection、18 個官方欄位、重複頁與最大頁數。
- Public snapshot 只保留 tracecode、公開經營業者／組織代碼、explicit-mapped product、粗粒度縣市、包裝日、驗證機構與有效日。姓名、精確地址、地段地號、通路、作業明細與一籤一碼資料不會進入 artifact。
- Contract／integration tests 覆蓋 active、expired、missing tracecode、duplicate、conflicting tracecode、unknown item、schema drift、HTML／empty／non-JSON、retry、80% count regression、atomic promotion 與 same-source LKG。
- H44 market event、8066 aggregate 與 Buy Score 變更不在本 PR。

~~~text
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
Ran 102 tests
OK

PYTHONPATH=src python3 -m tpw validate-traceability
valid traceability registry: fixture 5

PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-25
data valid
PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-25
site verified
~~~

Committed Pages artifacts intentionally remain `fixture` until a scheduled live refresh succeeds; this evidence does not claim that PR A has been merged or deployed to the public `main` Pages site.

## Issue #3 Phase 2A source contract — 2026-08-28

- `moa_market_8066` now enters ingestion through the same `SourceAdapter`／`RawBatch` contract used by a second, differently shaped offline fixture adapter.
- Source runs record role, adapter／source schema version, retrieved time, content hash and precedence. Resolution uses `(transaction_date, market_code, crop_code, dataset_semantics)` and permits at most one `eligible_for_aggregate=true` record.
- Contract tests cover validation／provisional／contextual exclusion, lower-precedence suppression, equal-precedence final-source ambiguity, same-source correction, provisional supersession evidence, schema drift and atomic last-known-good preservation.
- No TAPMC transaction scraping, parity claim, contextual production feed or Buy Score change is included in 2A.

~~~text
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
Ran 90 tests
OK

PYTHONPATH=src python3 -m tpw validate-source-run --date 2026-08-25
valid source run: 2026-07-22 2026-08-25 1

PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-25
data valid
PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-25
site verified
~~~

The same 2026-08-25 fixture was seeded and built once from `main` and once from the Phase 2A branch. These behavior-bearing artifacts had identical SHA-256 values:

| Artifact | Both builds |
|---|---|
| normalized market rows | `9005a3f943ad96b491e769d19800e73ce1398a922c65778fdb4be4b5a48ec07b` |
| daily aggregate | `e64a341717f3583f8c163abdd12b1ffc7c7c9618af6fe22355e5c973f8e7b795` |
| `site/index.html` | `d37a000625bfe5b5b500b6a4351f407bf35e6e64facd4989444dc582211829ec` |
| `site/data/current.json` | `9c9f957da6107fc8b260e8a806b9909db27841df582fd4887e18cf933ba791f6` |
| `site/methodology.html` | `92594cd7d620676d948a812d11346bc61b896aa40573d0bf8ca7767da1423890` |
| daily Markdown report | `1fdf5f2313494d6b16ae85751461b9fafff1e4d66389382eb95449feff1e21ac` |

The Phase 2A branch was then seeded and built again. Source-run evidence (`8c1bbe…`) and all listed artifacts retained their hashes, covering deterministic double-build behavior. Remote PR checks are recorded on the PR; this section does not claim a merge or production activation.

## Issue #8 live seasonality evidence — 2026-08-27

- Official AFA fruit and vegetable pagination fetched successfully for `2026-08`.
- Aggregated catalog: 39 products (20 fruit, 19 vegetables); 13 exact-name mappings to the configured 20-item market watchlist. The generic official `花椰菜` row is intentionally not mapped to the narrower `青梗花椰菜` market item.
- Generated `season/current.html`: 39 server-rendered cards, all/fruit/vegetable filter metadata, origin-county counts, market-data status, traceability status and base-path-safe detail links.
- Source status is `live` in both `data/seasonality/catalog/2026-08.json` and `site/data/current.json`; no fuzzy mapping is used.
- Contract tests cover sequential pagination, schema/category/month drift, duplicate pages and transient retry classification.
- Integration tests cover manual fallback, stale last-known-good reuse, catalog/page parity and required filters.

~~~text
PYTHONPATH=src python3 -m compileall -q src tests
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
Ran 48 tests
OK

PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-26
data valid
PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-26
site verified
~~~

Remote PR checks and deployment are recorded separately after GitHub completes them; this section does not claim main or Pages deployment yet.

## Acceptance status

Local implementation, remote-main, GitHub Actions, Pages deployment and live-browser acceptance are complete for the side-project prototype. The market feed now includes a successful 2026-08-26 upstream snapshot; seasonality and traceability remain clearly labelled prototype reference data.

## Verified locally

~~~text
PYTHONPATH=src python3 -m compileall -q src tests

PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
Ran 24 tests in 1.605s
OK

PYTHONPATH=src python3 -m tpw validate-config
config valid: 20 mapped items

PYTHONPATH=src python3 -m tpw seed-prototype --as-of 2026-08-25
seeded normalized rows: 1400

PYTHONPATH=src python3 -m tpw build --as-of 2026-08-25
build promoted safely

PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-25
data valid

PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-25
site verified

python3 -c 'import yaml; ... yaml.safe_load(...)'
YAML OK: 3 workflows
~~~

The complete data/, reports/ and site/ file manifest was hashed, the same build was run again, and the second manifest had no diff. git diff --check passed. A site-only secret/base64 pattern scan returned no matches.

## Prototype evidence

| Surface | Observed result |
|---|---|
| Fixture history | 35 calendar days, 20 canonical items, 2 markets, 1,400 normalized rows |
| Analytics | previous valid trading day plus 7／30／90D volume-weighted windows and coverage |
| Recommendation | 20 score rows; 13 eligible; homepage shows top 6 |
| Advice | deterministic_fallback, tpw-advice-v1, stable input hash |
| Static routes | 20 produce pages, 4 trend pages, season page, 21 traceability pages including index, daily/archive/methodology |
| Derived data | 20 series JSON files plus seasonality, advice, quality and minimized traceability history |
| Output budget | site/ 388 KB; repository working tree 2.6 MB |

## Browser acceptance

Local site was served through a real browser at http://127.0.0.1:8765/.

- 1366×768: #recommendations top = 272 px, 3 columns, exactly 3 cards visible in the initial viewport, no horizontal overflow.
- 900×800: 2 recommendation columns, no horizontal overflow.
- 390×844: 1 recommendation column, #recommendations top = 274 px, no horizontal overflow.
- Seasonality filter changed to vegetables only: 3 visible vegetables, 0 fruits, and aria-pressed updated.
- Recommendation-card flow opened /produce/banana.html; title, wholesale disclaimer, inline SVG trend and 14-day table were present.
- /trends/daily.html showed a real previous-trading-day reference; /trends/quarterly.html showed 20 rows with the 90D heading.
- /traceability/index.html showed five minimized fixture cards and the exact non-join warning.
- Local server log showed only 200/304 responses for tested HTML, CSS and JS; no 404 occurred.

Local screenshots:

- tpw-desktop-1366x768.jpg
- tpw-mobile-390x844.jpg

## Requirement traceability

- **PR 2 / FR-004, FR-010:** analytics unit tests cover previous-valid-day skipping, zero-reference behavior, coverage, weighted windows and volatility; integration and browser checks cover all detail/trend routes and chart/table fallback.
- **PR 3 / FR-003, FR-005, FR-006:** seasonality and score unit tests cover unknown/fallback behavior, market-count/coverage gates and deterministic score boundaries; fixture acceptance requires at least three eligible cards.
- **PR 4 / FR-007, FR-008:** advice tests prove minimized provider input, deterministic output, strict language/schema checks and fallback on prohibited or invalid provider output.
- **PR 5 / FR-015, FR-016, FR-017:** traceability tests prove watchlist filtering, nullable dates, coarse place, removal of farmer/store values and non-join semantics.
- **PR 1 regression:** market contract, normalization/upsert, history retention and injected three-tree rollback tests remain green.

## Artifact integrity

| Artifact | SHA-256 |
|---|---|
| site/index.html | b9512f286b761dfd13f0e3a35b71ca8f24ed555faa2f62755cf31779eb2f5f0f |
| site/data/current.json | cba29eb96fc4a2d3597cb94515ea965a6e1dc6d460cb8e690a42cf5341f9e479 |
| normalized 2026-08-25 JSON | 36cf85214ccf1bd3e3c2e80a63ed6aaecf3a7d05f0eba818844175a7b312a3f7 |
| aggregate 2026-08-25 JSON | fa63c8757e1ab0700d333fcbde6cb612bfcec47e98ec1bebacb6601d0c452b99 |
| advice 2026-08-25 JSON | f6506baa63eeea08dc3a19e298fd158a763f19263c0c92f3d2d4abd3e726eb7b |
| daily 2026-08-25 Markdown | 901336886a62e71757a1a1b1fd54ed8e0358e52a4efe8f0c459d0f09ecb364af |

Source-input hashes remained unchanged:

- SPEC.md: 2be4f623cf882eca7302d41702ecf53a23564e8f82753a7f82d404f617858ff6
- reference HTML: bd2ddaeb4a1ce1431d27ad5901310e0abd1a30a9cd8d8f4725f60f78a1b2e7dd

## Remote evidence

- Public repository: https://github.com/trionnemesis/tw-agri-copilot
- CI regression fix: `4538e1d2e17cd9d946cdc068199658616608a4f8`; push builds now reuse the committed verified date and skip external market/context fetches.
- Generated presentation normalization: `b54d88c`; created by the repaired workflow and fast-forwarded back to the local `main`.
- Fixture CI after the fix: success — https://github.com/trionnemesis/tw-agri-copilot/actions/runs/32984784012
- Daily market update after the fix: success — https://github.com/trionnemesis/tw-agri-copilot/actions/runs/32984784867. The run shows both external fetch steps skipped on `push`, with build, normalization, validation, commit and Pages deployment successful.
- Deploy Pages after the fix: success — https://github.com/trionnemesis/tw-agri-copilot/actions/runs/32985003582
- PR2–PR5 feature tip: `c708ee712f7e364fdb3885768ea9d7a71bddf3ad`; observed on remote `main`.
- Fixture CI: success — https://github.com/trionnemesis/tw-agri-copilot/actions/runs/32956554494
- Deploy Pages: success — https://github.com/trionnemesis/tw-agri-copilot/actions/runs/32956554533
- Pages API: public, HTTPS enforced, workflow build type.
- Live URL: https://trionnemesis.github.io/tw-agri-copilot/ returned HTTP 200.
- Live `data/current.json`: 2026-08-25, fixture, deterministic_fallback, prototype_complete=true, 13 eligible rows.
- Live browser 1366×768: recommendation top 272 px, 3 columns, 3 cards visible, no overflow.
- Live browser 390×844: recommendation top 274 px, 1 column, no overflow.
- Live recommendation flow opened `/produce/banana.html` with chart/disclaimer; live traceability index showed five cards and the exact non-join warning.

Live screenshots:

- `tpw-live-desktop-1366x768.jpg`
- `tpw-live-mobile-390x844.jpg`

## Explicit limits

- No live 120-day backfill was dispatched for this release.
- No live seasonality or traceability API snapshot was published.
- No external AI provider was enabled.
- Twice-daily scheduled publication remains lightly observed; the separate push rebuild path now has successful remote runtime evidence and does not contact the upstream market service.
- Fixture/fallback status and wholesale/non-retail wording are intentionally visible on the public prototype.
