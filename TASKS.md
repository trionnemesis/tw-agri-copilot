---
task_set: TPW-PR1-PR5-PROTOTYPE
version: 1.1.0
status: Done
owner: gpt-5.6-terra implementation subagent
reviewer: main agent
source_spec: SPEC.md
---

# Taiwan Produce Watch — PR 1–5 Prototype Tasks

Status values: `TODO`, `IN_PROGRESS`, `DONE`, `BLOCKED`. A task may be marked `DONE` only with file and command evidence in `VERIFICATION.md`.

## Planning baseline

- [x] **T-000 — Preserve source inputs and define bounded plan** (`NFR-002`, `NFR-008`)
  - Inputs: `SPEC.md`, `references/00965_deep_analysis_20260826(1).html`.
  - Evidence: `PLAN.md`, `WORK_ORDER.md`, recorded SHA-256 hashes.

## Execution tasks

- [x] **T-101 — Produce upstream discovery report and sanitized fixtures** (`FR-001`, `FR-002`, `NFR-003`, `NFR-008`, `NFR-010`)
  - Create `DISCOVERY.md` with bounded request details, observed fields/date format, pagination findings, 20 validated crop codes, provenance, timestamps, and hashes.
  - Commit only minimal fixtures; include success, HTML/empty, missing-field, duplicate-page, and correction scenarios.
  - Dependencies: T-000.

- [x] **T-102 — Scaffold package, configuration, and deterministic schemas** (`FR-001`, `NFR-001`, `NFR-002`, `NFR-009`)
  - Create `pyproject.toml`, `src/tpw`, config files needed by PR 1, `.gitignore`, and concise `README.md`.
  - Configure the validated 10-fruit + 10-vegetable watchlist using exact observed crop codes.
  - Lock runtime/test dependencies and exclude caches/build products.
  - Dependencies: T-101.

- [x] **T-103 — Implement market fetch and validation adapter** (`FR-001`, `FR-002`, `NFR-007`, `NFR-008`, `NFR-010`, `AC-009`)
  - Explicit dates, `$top`/`$skip`, maximum pages, repeated-page detection, HTTP/content-type/JSON/field validation, source metadata, and rolling four-day fetch.
  - Invalid/empty input must fail before promotion and preserve last-known-good content.
  - Dependencies: T-102.

- [x] **T-104 — Implement normalization and correction-safe upsert** (`FR-002`, `NFR-001`, `NFR-007`, `NFR-010`, `AC-010`)
  - Parse ROC/Gregorian dates and finite nonnegative numeric fields.
  - Exact curated mapping only; stable row hash; deterministic ordering; upstream corrections replace the same logical key without duplicates.
  - Dependencies: T-103.

- [x] **T-105 — Implement weighted daily aggregation** (`FR-001`, `NFR-001`, `AC-003`)
  - Use `sum(price × volume) / sum(volume)` for valid rows only.
  - Output total volume, market count, valid/excluded counts, median/min/max market prices, and quality warnings.
  - Dependencies: T-104.

- [x] **T-106 — Implement CLI and safe data lifecycle** (`FR-001`, `FR-002`, `FR-014`, `NFR-001`, `NFR-007`, `AC-009`, `AC-010`)
  - PR 1 commands: `validate-config`, `fetch-market`, `build`, `backfill --days 120`, `validate-data`, `verify-site`.
  - Stage, validate, and atomically promote outputs; unchanged content creates no tracked diff.
  - Later-slice commands must not falsely claim working behavior.
  - Dependencies: T-103–T-105.

- [x] **T-107 — Generate static homepage and daily archives** (`FR-009`, `FR-011`, `FR-013`, `NFR-004`, `NFR-005`, `NFR-006`, `NFR-008`, `NFR-010`, `AC-002`, `AC-011`, `AC-013`)
  - Generate homepage, daily HTML/Markdown, archive index, methodology page, current JSON, CSS, optional progressive JS, and `.nojekyll`.
  - Apply the reference visual language without copying ETF content/base64 charts.
  - Include a truthful PR 3 recommendation placeholder and wholesale/non-retail wording anywhere a price appears.
  - Ensure semantic HTML, mobile layout, no horizontal overflow, JS-independent core content, escaping, and base-path-safe links.
  - Dependencies: T-105–T-106.

- [x] **T-108 — Add GitHub automation definitions** (`FR-001`, `FR-002`, `FR-013`, `FR-014`, `NFR-002`, `NFR-003`, `NFR-007`, `NFR-009`)
  - Add fixture-only CI, scheduled/manual daily update with concurrency and rolling four-day/backfill inputs, and a Pages-ready deployment workflow.
  - Use least-privilege permissions, pinned action major versions, validation-before-write, content-change gating, link/HTML smoke checks, and size guards.
  - Do not enable or dispatch live Pages deployment.
  - Dependencies: T-106–T-107.

- [x] **T-109 — Implement automated tests** (`FR-001`, `FR-002`, `FR-009`, `FR-011`, `FR-013`, `NFR-001`–`NFR-004`, `NFR-007`–`NFR-010`, `AC-002`, `AC-003`, `AC-009`–`AC-011`, `AC-013`, `AC-014`)
  - Unit, contract, and integration tests must run without live APIs.
  - Include deterministic double-build, LKG failure, link/disclaimer, escaping, secret-pattern, no-base64-in-site, and size-guard assertions.
  - Dependencies: T-103–T-108.

- [x] **T-110 — Produce verification and implementation handoff** (all IDs claimed above)
  - Create `VERIFICATION.md` with exact commands/results, requirement mapping, generated artifact hashes, known limits, and explicitly unverified remote/live evidence.
  - Leave the worktree ready for main-agent review; do not commit, push, create a repository, or deploy.
  - Dependencies: T-101–T-109.

## Dependency order

```text
T-000 → T-101 → T-102 → T-103 → T-104 → T-105
                                      └────────→ T-106 → T-107 → T-108
                                                          └────→ T-109 → T-110
```

## Authorized prototype continuation

- [x] **T-201 — PR 2 rolling analytics and routes** (`FR-004`, `FR-010`)
  - Previous valid trading day, 7／30／90D volume-weighted windows, coverage, 20 produce pages, four trend routes, inline SVG plus table fallback.
  - Evidence: analytics unit tests, complete-route integration test, browser route checks.

- [x] **T-202 — PR 3 seasonality and deterministic recommendations** (`FR-003`, `FR-005`, `FR-006`)
  - Manual fallback contract, canonical mapping, hard eligibility gates, exact score components, first-viewport cards and price movers.
  - Evidence: seasonality/scoring unit tests, >=3 fixture recommendation gate, responsive browser checks.

- [x] **T-203 — PR 4 provider-neutral advice fallback** (`FR-007`, `FR-008`)
  - Minimized evidence input, strict zh-Hant output schema, prohibited-claim checks, input hash/prompt metadata and deterministic fallback.
  - Evidence: advice unit tests and deterministic build hash.

- [x] **T-204 — PR 5 traceability context** (`FR-015`, `FR-016`, `FR-017`)
  - Watchlist filtering, nullable fields, coarse location, minimized persistence, detail routes and exact non-join warning.
  - Evidence: traceability unit/integration tests and generated route inspection.

- [x] **T-205 — Public prototype release** (`FR-013`, `FR-014`)
  - AgentSec-inspired README, fixture CI, active official Pages workflow, independent Sol acceptance, direct main push, observed CI/deploy and live desktop/mobile verification.
  - Evidence: `VERIFICATION.md` records the observed remote commit, successful workflow runs, live HTTP response and browser checks.

- [x] **T-206 — Official current-month seasonality catalog** (`FR-003`)
  - Official AFA HTML adapter for fruit/vegetable pagination, strict contract validation, explicit watchlist name mapping, monthly catalog persistence and transient-only LKG/fallback.
  - Evidence: seasonality contract/unit/integration tests plus generated 39-item August catalog and static page assertions.

## Issue #44 Part B — multi-category season semantics

- [x] **T-301 — Produce category registry, schema and `tpw.categories`** (`FR-003`, `NFR-008`, `NFR-010`)
  - `config/produce-categories.json` + `schema/produce-categories.schema.json` + `src/tpw/categories.py`: config-driven registry for fruit/vegetable/livestock/aquaculture, replacing the fifteen call sites that used to hard-code the fruit/vegetable binary; an unknown category id raises (loud failure) instead of silently falling back to one of the two original labels.
  - Evidence: `VERIFICATION.md` `## v1.1.0 — Issue #44 Part B` (`validate-config` output, registry hash, `git diff --stat` new-file list); `tests/unit/test_categories.py` (32 tests).

- [x] **T-302 — Season-map payload `schema_version 1.1`** (`NFR-001`, `NFR-008`)
  - `src/tpw/season_map.py`: per-category `source_status` under `inputs.seasonality_sources`, top-level `categories` axis with `catalog_row_count`, `inputs.category_registry_hash`; `schema/season-map.schema.json` synced to the same field set and category enum.
  - Evidence: `VERIFICATION.md` `## v1.1.0 — Issue #44 Part B` (`site/data/season-map/current.json` field-by-field check); `tests/unit/test_season_map.py` (+6 tests, +1 stricter rename).

- [x] **T-303 — Extension catalog slot** (`NFR-001`, `NFR-003`, `NFR-007`)
  - `data/seasonality/extensions/<YYYY-MM>.json` loader/validator (`src/tpw/season_extensions.py`): accepts only registered, non-AFA `official_season_registry` categories; rejects `no_official_season_registry` rows citing `SPEC.md §6.2.6` / Issue #44 BC-2; no extension file is committed by this work order.
  - Evidence: `VERIFICATION.md` `## v1.1.0 — Issue #44 Part B`; `tests/unit/test_season_extensions.py` (32 tests); `tests/integration/test_build.py` scenarios (no-extension build, test-only category build, livestock-extension fail-closed, stale-schema rejection).

- [x] **T-304 — Registry-driven render/CLI/icons and loud failure on unknown category** (`FR-003`, `NFR-004`, `NFR-010`)
  - `src/tpw/render.py`, `src/tpw/cli.py`, `src/tpw/produce_icons.py`, `src/tpw/assets/produce-icons.svg`: the fifteen category hard gates now read the registry; two new category fallback icons (sprite 43 → 45 symbols); season page 「產季語意」 section; map intro notice plus 22 per-county unknown lines; methodology 「產季語意與類別」 table; `assets/js/app.js` filter set derived from the DOM instead of hard-coded.
  - Evidence: `VERIFICATION.md` `## v1.1.0 — Issue #44 Part B`; `tests/integration/test_build.py`; `tests/browser/season-map.spec.mjs`, `tests/browser/season-search.spec.mjs` — `33 passed, 1 skipped`.

- [x] **T-305 — Committed publication rebuild and idempotency** (`AC-010`)
  - `src/tpw/__init__.py` `__version__` → `1.1.0`; the committed publication was rebuilt in place (`build` → `tpw.presentation` → `validate-data` → `verify-site`), mirroring `daily-update.yml`'s "Build, normalize, and validate" step, without running `seed-prototype` at the repository root.
  - Evidence: `VERIFICATION.md` `## v1.1.0 — Issue #44 Part B` — signature before rebuild `b28c66e1…`, after the first and second rebuild pass both `f6818e79…` (idempotent).

- [x] **T-306 — Documentation and `DISCOVERY.md` continuation** (`NFR-008`)
  - `README.md`, `CHANGELOG.md` (`[1.1.0]`), `VERIFICATION.md` (new `## v1.1.0` section), `TASKS.md` (this section), `PLAN.md` (`version 1.1.0` + target-outcome item 14), `DISCOVERY.md` (Part B bounded-discovery continuation; the existing 2026-08-26 text is unchanged).
  - Evidence: this section and the six documents it lists; `VERIFICATION.md` `## v1.1.0 — Issue #44 Part B`.

## Completion definition for this work order

This work order completes the **PR 1–5 side-project prototype**, not the full production P0 Definition of Done. Live 120-day bootstrap, live traceability, an external AI provider, long-running scheduled publication and production data freshness remain explicitly unverified. Issue #8 adds the live seasonality adapter without expanding those remaining scopes.

Issue #44 Part B ships the multi-category produce contract with livestock and aquaculture mapped as explicit `unknown` across the 22-county matrix; live adapters for those two categories remain out of scope pending S-grade discovery on a `*.gov.tw`-reachable environment.
