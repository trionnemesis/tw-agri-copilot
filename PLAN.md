---
plan_id: TPW-PLAN-001
version: 0.2.0
status: Public prototype released and verified
scope: PR 1-5 - Public side-project prototype
source_spec: SPEC.md
prepared_at: 2026-08-26
---

# Taiwan Produce Watch — Implementation Plan

## 1. Authority, decisions, and boundaries

- `SPEC.md` is the product and system source of truth and must remain byte-for-byte unchanged during this work order.
- The user explicitly requires the public GitHub repository to match the current folder name, so the repository will be `tw-agri-copilot`. The product/site name remains **Taiwan Produce Watch**. This is a repository-naming override only.
- The original PR 1 foundation remains the baseline; the user subsequently authorized a lean continuation through **PR 2–5** to complete the public prototype.
- The reference file `references/00965_deep_analysis_20260826(1).html` is visual input only. Reuse layout language and CSS tokens; do not copy its ETF content or embedded base64 charts into the generated site.
- The required CI path must be fixture-based and offline. Live public API access is allowed only for bounded schema/crop-code discovery and an explicitly invoked data refresh.
- The main agent owns repository creation, commits, push, and final acceptance. The implementation subagent must not create or mutate remote repositories.
- A base-path-safe site and active official GitHub Pages workflow are in scope. Remote deployment is claimed only after the main agent observes the workflow and live URL.

## 2. Target outcome

Deliver a reviewable PR 1–5 prototype that:

1. fetches market data with explicit dates and safe pagination;
2. validates and normalizes only a curated 10-fruit + 10-vegetable watchlist;
3. upserts deterministic daily JSON and computes volume-weighted daily price/volume aggregates;
4. generates a static homepage, daily HTML archive, daily Markdown report, archive index, and methodology page;
5. always labels displayed prices as wholesale-market averages rather than retail prices;
6. supports a 120-day backfill command and rolling four-day update path;
7. preserves last-known-good output when input/build validation fails;
8. includes fixture-based tests, CI, a Pages-ready deployment workflow, and reproducible verification evidence.
9. computes previous-trading-day and 7／30／90D analytics with coverage;
10. renders 20 produce pages, four trend views, seasonality, recommendations, movers, and archives;
11. keeps advice provider-neutral with strict validation and deterministic fallback;
12. filters/minimizes traceability context without joining it into Buy Score.

Primary PR 1 traceability: `FR-001`, `FR-002`, `FR-009`, `FR-011`, `FR-013`; supporting constraints: `NFR-001`–`NFR-004`, `NFR-007`–`NFR-010`, `AC-002`, `AC-003`, `AC-009`–`AC-011`, `AC-013`, `AC-014` where applicable to this slice.

## 3. Delivery sequence

### Phase A — Discovery and contracts

- Record the live endpoint, bounded query, retrieval time, response content type, exact observed field names, date format, pagination behavior, and sample hashes in `DISCOVERY.md`.
- Validate 20 actual market crop codes against observed public data; do not invent codes or promote fuzzy matches.
- Commit minimal sanitized fixtures for success, empty body, HTML body, missing fields, duplicate page, and upstream correction cases.
- Define source metadata and normalized-record contracts before implementing the adapter.

Exit gate: `DISCOVERY.md`, curated mapping, and fixtures agree on field names/codes and contain no secrets or unnecessary upstream dump.

### Phase B — Deterministic Python foundation

- Create a `src/tpw` package and CLI entry point.
- Implement ROC/Gregorian date parsing, numeric parsing, row validation, stable row hashing, duplicate handling, correction-safe upsert, and source metadata.
- Implement explicit `StartDate`/`EndDate`, `$top`/`$skip`, maximum-page and repeated-page guards, HTTP/content-type/JSON validation, and rolling four-day fetch behavior.
- Implement volume-weighted price aggregation with valid-row/excluded-row counts and no arithmetic-mean fallback.
- Keep output ordering and serialization deterministic.

Exit gate: unit and contract tests cover the adapter and weighted example from `AC-003`; invalid/empty upstream input cannot replace last-known-good data.

### Phase C — Static report generation

- Generate `site/index.html`, `site/daily/YYYY/MM/YYYY-MM-DD.html`, `reports/daily/YYYY/MM/YYYY-MM-DD.md`, `site/archive/index.html`, `site/methodology.html`, `site/data/current.json`, and `.nojekyll`.
- Use the reference visual system: compact navy/blue-green Hero, 1,180px content container, sticky pill navigation, white rounded cards, responsive grids, print rules, and accessible semantic HTML.
- Populate `#recommendations` only from deterministic score rows that pass seasonality, coverage, market-count, and quality gates.
- Render the required wholesale disclaimer next to every price-bearing view.
- Use only escaped upstream strings and base-path-safe relative links.

Exit gate: generated HTML remains useful with JavaScript disabled, has no embedded base64 charts, and passes local link/text/size checks.

### Phase D — Automation and verification

- Add fixture-only CI for tests, build verification, secret-pattern checks, and size guards.
- Add `daily-update.yml` with schedule/manual inputs, concurrency, rolling four-day update, backfill input, validation-before-write, and content-change gating.
- Add an active deploy workflow using official GitHub Pages actions; enable it only after local acceptance and verify the resulting URL.
- Run the same fixture/as-of build twice and compare output hashes to prove determinism.
- Produce `VERIFICATION.md` with commands, results, requirement evidence, incomplete later-slice items, and release limitations.

Exit gate: targeted tests, full local suite, package/static checks, deterministic rebuild, and clean working-tree review all pass before the main agent considers a commit/push.

## 4. Proposed repository topology

Follow the lean subset of SPEC section 13 required by the PR 1–5 prototype:

```text
config/produce.yml
src/tpw/{market,model,analytics,seasonality,scoring,advice,traceability,render,cli}.py
data/{source-meta,market/daily,aggregates/daily,series,seasonality,advice,traceability,quality}/
reports/daily/
site/{assets,data,daily,archive}/
tests/{fixtures,unit,contract,integration}/
.github/workflows/{ci,daily-update,deploy-pages}.yml
```

The prototype implements seasonality fallback, Buy Score, deterministic advice fallback, crop/trend pages, and minimized traceability fixtures. Live seasonality, traceability, AI-provider and full 120-day release validation remain outside this slice and must not be implied.

## 5. Failure and rollback model

- Fetch into a temporary/staging location, validate, then atomically promote successful output.
- Treat non-2xx responses, non-JSON content, empty/malformed collections, missing required fields, repeated pages, pagination overflow, and abnormal empty ranges as blocking.
- Never clear or overwrite committed `data/`, `reports/`, or `site/` on a blocking failure.
- Keep generated outputs content-addressable/deterministic; unchanged input must create no diff.
- Rollback is a normal Git revert of the isolated PR 1 commit(s); no database or destructive migration exists.

## 6. Test strategy

- **Unit:** date/numeric parsing, stable hash, upsert correction, weighted price, escaping, deterministic serialization.
- **Contract:** normal response, alternate/null fields, HTML body, empty response, duplicate page, missing fields, and upstream correction.
- **Integration:** fixture → normalize → aggregate → report/site generation → verify links and disclaimer.
- **Static:** workflow/YAML validity, package import, no secret-like values, no base64 images in `site/`, relative-link checks, and size budget.
- **Determinism:** build twice for the same fixture/as-of date and compare tracked output hashes.

Live API discovery is evidence, not a required test dependency.

## 7. Acceptance and handoff gates

The implementation subagent may report completion only after:

- every completed task in `TASKS.md` references requirement IDs;
- all validation commands and their actual outcomes are recorded in `VERIFICATION.md`;
- any unavailable live/API/Pages evidence is explicitly marked unverified;
- `SPEC.md` and the reference HTML hashes still match their imported originals;
- no secret, token, credential, private endpoint, or generated credential-bearing file is present;
- no Git commit, push, repository creation, or live deployment was performed by the subagent.

The main agent will independently inspect the diff, rerun focused and related validation, exercise the generated site, and only then commit/push the existing public GitHub repository and enable Pages.

## 8. Lean prototype release gates

This side project intentionally does not require the full Hermes engineering process. Release requires only:

1. correct deterministic fixture data and exact score/coverage behavior;
2. preserved normalized/generated history and rollback-safe promotion;
3. unit, contract, integration, workflow-YAML, secret, size, and deterministic-build checks;
4. desktop/mobile browser verification with working routes and no horizontal overflow;
5. observed remote `main`, successful CI/Pages workflows, and a reachable public site.
