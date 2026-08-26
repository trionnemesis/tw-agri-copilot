# PR 1 verification — 2026-08-26

## Verified locally

```text
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
Ran 12 tests in 0.683s
OK

PYTHONPATH=src python3 -m tpw validate-config
config valid: 20 mapped items

PYTHONPATH=src python3 -m tpw build --as-of 2026-08-25
build promoted safely
PYTHONPATH=src python3 -m tpw validate-data --as-of 2026-08-25
data valid
PYTHONPATH=src python3 -m tpw verify-site --as-of 2026-08-25
site verified
```

The double-build hash comparison produced no diff. Representative fixture artifacts:

| Artifact | SHA-256 |
|---|---|
| `site/index.html` | `4f23512192c19ca8a312f7668e017005cb84f3dc2a241edbff33b447f822c4b7` |
| normalized daily JSON | `0bba49ce83bc182ac72ab90d93dfe02fe4cb3b575512ae2b6fbcdd495d60b421` |
| daily aggregate JSON | `0c576a6013f5f0c7188c4219fdeb8dddd33da762c6122ba2c5e38dfb4805a524` |
| daily Markdown | `8dc5eb909523956735977d073b628b6be4b488276786052b7c3d9a232f7132bc` |

`rg -n 'AKIA|ghp_|glpat-|base64,' site` found no matches; `site/` is 1 MB by `du -sm`.

## Requirement evidence

- FR-001/FR-002, NFR-003/NFR-008/NFR-010: explicit-date, paginated market adapter with response validation; contract tests cover empty/HTML and duplicate page handling. `DISCOVERY.md` records live schema evidence.
- NFR-001/NFR-007, AC-003/AC-010: ROC date conversion, finite numeric validation, correction-safe logical-key upsert and volume-weighted aggregation; unit and double-build integration tests pass. The AC-003 example returns 20.19801980198, not 30.
- FR-009/FR-011/FR-013, NFR-004/NFR-005/NFR-009: deterministic fixture build produces homepage, daily HTML/Markdown, archive, methodology, current JSON, no-JS core text, responsive CSS, disclaimer, relative links, `.nojekyll`, no base64, size guard.
- FR-014: named CLI entry points and scheduled/manual workflow definitions are present. Fixture CI has no live API request. The opt-in Pages workflow uses GitHub's official configure, artifact, and deploy actions, but its deployment job remains skipped until `ENABLE_PAGES_DEPLOY=true` is explicitly configured.

## Source-input integrity

SHA-256 remained unchanged: `SPEC.md` `2be4f623cf882eca7302d41702ecf53a23564e8f82753a7f82d404f617858ff6`; `PLAN.md` `6614a7b2c7c8f63941ae0217cb6076287ad05d9bb741dfeb51c6af0d81d860bb`; `WORK_ORDER.md` `30a7f5b29ee4197e666ff7db2303e71e962c1adaa3e5cd35ad0422664d8733d7`; reference HTML `bd2ddaeb4a1ce1431d27ad5901310e0abd1a30a9cd8d8f4725f60f78a1b2e7dd`.

## Not verified / intentionally deferred at subagent handoff

- No GitHub Actions run, Pages enablement/repository variable, Pages deployment, credential, or live daily publication was dispatched during subagent implementation.
- The one bounded live request verified schema/codes only. It is not committed and not used by required tests.
- No live 120-day backfill was dispatched. The implemented `backfill --days 120` code path is genuine, bounded in four-day windows, and fixture-mocked in required tests.
- PR 2–5 remain deferred: rolling windows, crop detail/trend pages, seasonality, Buy Score/recommendations, AI, and traceability.

## Acceptance remediation

The lifecycle is now genuine rather than fixture-coupled: `fetch-market` converts ISO request dates to observed ROC source dates, validates and normalizes only configured mappings, writes per-day normalized JSON and source metadata, then merges corrections by logical key. An identical refetch preserves stored rows and source metadata despite a new fetch timestamp, while a changed row hash replaces the same logical key. Blocking input failures occur before the atomic directory swap, preserving the previous `data/` tree.

`backfill --days N --end YYYY-MM-DD` splits the exact inclusive date range into bounded four-day windows. It is fixture-mocked in required tests; no live 120-day request was run. `build --as-of` now reads only stored normalized data for that ISO date and fails before staging/promoting if it is absent or mismatched. Directory promotion uses rename-to-backup and rollback on replacement failure. The daily workflow stages generated paths before its cached-diff check, so a newly created date is included in content-change gating.

`verify-site` crawls generated HTML links, requires the homepage recommendations-section contract, checks price disclaimers, rejects secret/base64 patterns, validates the requested as-of JSON, and enforces the 900 MB size threshold with largest-file diagnostics. Nested daily CSS and navigation links are depth-correct. The daily workflow calculates Asia/Taipei dates at runtime and calls the real backfill CLI; Pages deployment remains opt-in.

All three workflow files were parsed with `python3 -c 'import yaml; ... yaml.safe_load(...)'`, returning `YAML OK: 3 workflows`. The integration suite retains two built dates (`2026-08-24`, `2026-08-25`) and asserts that both daily HTML/Markdown files and both archive links survive. A focused injected `os.replace` failure confirms the three-tree promotion restores `data`, `site`, and `reports` to their pre-promotion content.
