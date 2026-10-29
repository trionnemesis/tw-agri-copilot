# Explicit fixture exclusion from market statistics

Base: `f5e20443edb3687d7d0d3872c544132926c39381`. Related: #51.

## Policy

Production market aggregation excludes rows explicitly marked `fetched_at=fixture` or
`source_status=fixture` (case/whitespace normalized), even when `source_id` is the real
MOA 8066 identifier. The same policy applies before current/history loading, Taipei
scope metadata and lineage, publication completeness checks and latest-date resolution.
Direct aggregation defaults to exclusion. Only explicitly labelled prototype fixture
builds opt in, retaining deterministic offline tests. Unmarked observations are not
thereby independently authenticated. Raw history and source evidence are retained.

## Rebuild and measured effect

Rebuilt the existing current publication with:

```
PYTHONPATH=src python -m tpw build --as-of 2026-10-21
PYTHONPATH=src python -m tpw.presentation
PYTHONPATH=src python -m tpw validate-data --as-of 2026-10-21
PYTHONPATH=src python -m tpw verify-site --as-of 2026-10-21
```

Two complete builds produce identical data/reports/site file hashes. The requested date
remains 2026-10-29, observation date 2026-10-21 and status `source_unavailable`.
These are corrected historical statistics, not today's prices or a new live fetch.

- Retained history has 1,327 explicit fixture rows across 35 dates; 1,247 rows across
  33 dates fall inside the current 90-day window (July 24–October 21).
- All 19 Taipei observed-item 90-day prices change; coverage falls from 76 to 45 days
  for 18 items and from 71 to 40 for watermelon. 7/30-day windows are unchanged.
- Spinach 90-day weighted price: 74.841577 → 77.751459 TWD/kg.
  Watermelon: 12.946413 → 12.663442 TWD/kg.
- Independent raw-row recomputation matches all 57 Taipei and 60 national window
  price/volume/coverage checks (national price/coverage independently reviewed).
- Current national series, current score inputs, produce/quarterly trend pages, and
  Taipei JSON/CSV/page are regenerated together. Current score/verdict values do not
  change. Tiny unrounded national daily float changes (~1e-14) are rebuild noise.

## Scope and verification limits

Older dated daily pages/reports and raw snapshots are retained historical artifacts,
not silently rewritten as new observations. This repair corrects the current publication
and future builds; it does not certify unmarked history or remediate all historical
archives. Source outages, monthly fixtures and official calendar fixtures are separate
contracts and unchanged. No scoring threshold, source trust gate or workflow was changed.

Tests cover direct aggregation, mixed live/fixture rows, historical coverage/ranges,
Taipei market counts/lineage, fixture-only latest dates, false completeness, explicitly
labelled prototype compatibility and end-to-end live-shaped rebuild invariance.
No merge, deployment or live-site verification is implied by these local results.

## Concurrent map integration

Revalidated against `bc3f826` after #57 (Taipei map) and #58 (home navigation).
The map keeps its own stricter provenance gate and receives raw rows, so rejected
fixture counts remain visible rather than disappearing from its quality evidence.
Its JSON, observations CSV and map HTML, plus homepage navigation, remain byte-identical
to that main snapshot after this repair's rebuild. National and Taipei aggregate paths
still exclude fixtures. Separate map provenance/UI concerns are outside this repair.
