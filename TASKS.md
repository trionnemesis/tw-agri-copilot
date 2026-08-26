---
task_set: TPW-PR1-WORK-ORDER
status: Ready
owner: gpt-5.6-terra implementation subagent
reviewer: main agent
source_spec: SPEC.md
---

# Taiwan Produce Watch — PR 1 Tasks

Status values: `TODO`, `IN_PROGRESS`, `DONE`, `BLOCKED`. A task may be marked `DONE` only with file and command evidence in `VERIFICATION.md`.

## Planning baseline

- [x] **T-000 — Preserve source inputs and define bounded plan** (`NFR-002`, `NFR-008`)
  - Inputs: `SPEC.md`, `references/00965_deep_analysis_20260826(1).html`.
  - Evidence: `PLAN.md`, `WORK_ORDER.md`, recorded SHA-256 hashes.

## Execution tasks

- [ ] **T-101 — Produce upstream discovery report and sanitized fixtures** (`FR-001`, `FR-002`, `NFR-003`, `NFR-008`, `NFR-010`)
  - Create `DISCOVERY.md` with bounded request details, observed fields/date format, pagination findings, 20 validated crop codes, provenance, timestamps, and hashes.
  - Commit only minimal fixtures; include success, HTML/empty, missing-field, duplicate-page, and correction scenarios.
  - Dependencies: T-000.

- [ ] **T-102 — Scaffold package, configuration, and deterministic schemas** (`FR-001`, `NFR-001`, `NFR-002`, `NFR-009`)
  - Create `pyproject.toml`, `src/tpw`, config files needed by PR 1, `.gitignore`, and concise `README.md`.
  - Configure the validated 10-fruit + 10-vegetable watchlist using exact observed crop codes.
  - Lock runtime/test dependencies and exclude caches/build products.
  - Dependencies: T-101.

- [ ] **T-103 — Implement market fetch and validation adapter** (`FR-001`, `FR-002`, `NFR-007`, `NFR-008`, `NFR-010`, `AC-009`)
  - Explicit dates, `$top`/`$skip`, maximum pages, repeated-page detection, HTTP/content-type/JSON/field validation, source metadata, and rolling four-day fetch.
  - Invalid/empty input must fail before promotion and preserve last-known-good content.
  - Dependencies: T-102.

- [ ] **T-104 — Implement normalization and correction-safe upsert** (`FR-002`, `NFR-001`, `NFR-007`, `NFR-010`, `AC-010`)
  - Parse ROC/Gregorian dates and finite nonnegative numeric fields.
  - Exact curated mapping only; stable row hash; deterministic ordering; upstream corrections replace the same logical key without duplicates.
  - Dependencies: T-103.

- [ ] **T-105 — Implement weighted daily aggregation** (`FR-001`, `NFR-001`, `AC-003`)
  - Use `sum(price × volume) / sum(volume)` for valid rows only.
  - Output total volume, market count, valid/excluded counts, median/min/max market prices, and quality warnings.
  - Dependencies: T-104.

- [ ] **T-106 — Implement CLI and safe data lifecycle** (`FR-001`, `FR-002`, `FR-014`, `NFR-001`, `NFR-007`, `AC-009`, `AC-010`)
  - PR 1 commands: `validate-config`, `fetch-market`, `build`, `backfill --days 120`, `validate-data`, `verify-site`.
  - Stage, validate, and atomically promote outputs; unchanged content creates no tracked diff.
  - Later-slice commands must not falsely claim working behavior.
  - Dependencies: T-103–T-105.

- [ ] **T-107 — Generate static homepage and daily archives** (`FR-009`, `FR-011`, `FR-013`, `NFR-004`, `NFR-005`, `NFR-006`, `NFR-008`, `NFR-010`, `AC-002`, `AC-011`, `AC-013`)
  - Generate homepage, daily HTML/Markdown, archive index, methodology page, current JSON, CSS, optional progressive JS, and `.nojekyll`.
  - Apply the reference visual language without copying ETF content/base64 charts.
  - Include a truthful PR 3 recommendation placeholder and wholesale/non-retail wording anywhere a price appears.
  - Ensure semantic HTML, mobile layout, no horizontal overflow, JS-independent core content, escaping, and base-path-safe links.
  - Dependencies: T-105–T-106.

- [ ] **T-108 — Add GitHub automation definitions** (`FR-001`, `FR-002`, `FR-013`, `FR-014`, `NFR-002`, `NFR-003`, `NFR-007`, `NFR-009`)
  - Add fixture-only CI, scheduled/manual daily update with concurrency and rolling four-day/backfill inputs, and a Pages-ready deployment workflow.
  - Use least-privilege permissions, pinned action major versions, validation-before-write, content-change gating, link/HTML smoke checks, and size guards.
  - Do not enable or dispatch live Pages deployment.
  - Dependencies: T-106–T-107.

- [ ] **T-109 — Implement automated tests** (`FR-001`, `FR-002`, `FR-009`, `FR-011`, `FR-013`, `NFR-001`–`NFR-004`, `NFR-007`–`NFR-010`, `AC-002`, `AC-003`, `AC-009`–`AC-011`, `AC-013`, `AC-014`)
  - Unit, contract, and integration tests must run without live APIs.
  - Include deterministic double-build, LKG failure, link/disclaimer, escaping, secret-pattern, no-base64-in-site, and size-guard assertions.
  - Dependencies: T-103–T-108.

- [ ] **T-110 — Produce verification and implementation handoff** (all IDs claimed above)
  - Create `VERIFICATION.md` with exact commands/results, requirement mapping, generated artifact hashes, known limits, and explicitly unverified remote/live evidence.
  - Leave the worktree ready for main-agent review; do not commit, push, create a repository, or deploy.
  - Dependencies: T-101–T-109.

## Dependency order

```text
T-000 → T-101 → T-102 → T-103 → T-104 → T-105
                                      └────────→ T-106 → T-107 → T-108
                                                          └────→ T-109 → T-110
```

## Completion definition for this work order

This work order completes **PR 1 only**. It must not mark full P0 or SPEC Definition of Done complete. PR 2 analytics, PR 3 seasonality/recommendations, PR 4 AI, and PR 5 traceability remain explicitly pending.
