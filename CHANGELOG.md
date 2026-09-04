# Changelog

本檔案記錄對外可見的行為變更。格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號採 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

## [1.0.0] — 2026-09-04

第一個標記版本。內容對應 Issue #44 Part A 盤點出的三個既有缺陷，全部修正並各自留下回歸保護。

### Fixed

- **D-1｜當季圖示 registry 綁定輪替中的上游清單。**
  `season_catalog` 是農糧署完整月份清單而非 watchlist，名稱每月輪替且不受本專案控制，因此
  「published catalogue == `PRODUCE_ICON_REGISTRY`」的等值斷言在每個月份交界都必然失敗
  （9 月帶入 `芒果`、`葡萄柚`，退場 `龍眼`、`高接梨`）。同一斷言旁的 39／20／19 與 sprite 41
  等硬編數字也有相同耦合。
  現在 registry 是跨月份的聯集：補齊 `芒果` 與 `葡萄柚` 兩個 sprite symbol（41 個 registry
  entry + 2 個分類 fallback），並以 `uncovered_display_names()` 回報覆蓋缺口。測試改為斷言不會
  腐化的不變量——未涵蓋名稱只會被回報並安全降級為分類 fallback，且每個已發布名稱都能解析到
  sprite 內實際存在的 symbol。

- **D-2｜每日資料 commit 沒有任何 CI 覆蓋。**
  `daily-update.yml` 以 `github-actions[bot]` 與預設 `GITHUB_TOKEN` push 到 `main`，而 GitHub
  不會為這種 push 啟動新的 workflow run，因此 `ci.yml` 自 2026-09-01 之後未再執行，其後的資料
  commit 完全沒有 CI；紅燈會無聲落地，並在下一個無關的 PR 上看似由該 PR 造成。
  `update` job 現在於 commit 之前執行完整測試套件與 repository size gate，並比對測試前後的工作樹，
  只要測試動過工作樹就 fail closed。`ci.yml` 另加每日排程，`main` 的健康狀態不再只在有人 push
  時才被檢查。

- **D-3｜測試套件會把已發布內容覆寫成 fixture。**
  `tests/integration/test_build.py` 以 repository 根目錄為 cwd 驅動真實 CLI，一次執行即改動
  `data/`、`site/`、`reports/` 下 126 個 tracked 檔案，把 live 價格換成 prototype fixture 值；
  任何人跑完測試後 commit 就會發布 fixture 當 live 資料，違反 `README.md#資料信任邊界`。
  這同時遮蔽了 D-1：`unittest discover` 下該模組會先把 `site/data/current.json` 重建成 8 月
  fixture，圖示測試因此對著 fixture 斷言而通過，CI 綠燈即源於此。
  這些測試改為在每個 test 的暫存 repository 副本上執行，套件現在不會動到工作樹一個位元組。

### Added

- `tpw.__version__` 作為版本的唯一來源，`pyproject.toml` 以 `[tool.setuptools.dynamic]` 取用，兩者不會漂移。
- 首頁 footer 顯示發布版本。
- 每日排程在 job summary 與 `::warning::` 回報當季圖示覆蓋率；圖示是裝飾性的，缺漏不阻擋當日行情發布。

### Changed

- README 更正實際過時之處：圖示數量、`tests/` 含 Playwright specs、`schema/` 檔案範圍、
  repository anatomy 缺少 `docs/` 與 `references/`、路由表缺少 20 個品項履歷頁，以及快速開始
  漏掉 `python3 -m tpw.presentation`（照原步驟建置出的站台與已發布內容不一致）。

### 文件版本對應

參考文件隨本次 release 對齊，唯一例外是 `SPEC.md`。

| 文件 | 版本 | 說明 |
|---|---|---|
| `tpw.__version__`／`pyproject.toml` | 1.0.0 | 套件版本的唯一來源；pyproject 以 `[tool.setuptools.dynamic]` 取用 |
| `PLAN.md` | 1.0.0 | front matter 由 `0.3.0` 對齊至本次 release |
| `TASKS.md` | 1.0.0 | front matter 新增 `version` 欄位 |
| `VERIFICATION.md` | 逐次追加 | 最新段落為 `## v1.0.0 — Issue #44 Part A` |
| `DISCOVERY.md` | 不改版 | 2026-08-26 一次性來源探查的原始紀錄，保留原貌 |
| `SPEC.md` | **0.1.0（維持不變）** | `WORK_ORDER.md` 明列不得編輯，`PLAN.md` 要求 byte-for-byte 不變，acceptance criteria 要求 SHA-256 維持 `2be4f623…`。它是契約基線，不隨實作 release 改版 |

### Unchanged

- `SPEC.md` 與 hash-pinned 視覺參考未被修改，SHA-256 維持 `2be4f623…` 與 `bd2ddaeb…`。
- 資料語意、Buy Score、advice 模式與所有資料信任邊界均未變動。本專案仍是 side-project
  prototype：外部 AI provider 未啟用、僅 8066 為 production `authoritative_final`、產銷履歷
  仍使用最小化 fixture。v1.0.0 是版本標記，不是成熟度宣告。

[1.0.0]: https://github.com/trionnemesis/tw-agri-copilot/releases/tag/v1.0.0
