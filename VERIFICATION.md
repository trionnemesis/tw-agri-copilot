# Prototype verification evidence

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
