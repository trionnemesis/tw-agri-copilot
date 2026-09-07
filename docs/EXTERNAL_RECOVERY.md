# External scheduler recovery

GitHub Actions remains the only data-fetch, build, validation, commit, and Pages publication layer. An external ChatGPT schedule may act only as a bounded recovery actuator when GitHub's own primary schedule and scheduler guard both fail to materialize the corresponding run.

## Normal path

- 09:17 Asia/Taipei: primary `Daily market update` morning schedule.
- 09:47: internal GitHub scheduler guard checks whether the 09:17 run exists.
- 10:30: external morning verifier checks repository evidence.
- 18:17 Asia/Taipei: primary `Daily market update` evening schedule.
- 18:47: internal GitHub scheduler guard checks whether the 18:17 run exists.
- 22:30: external evening verifier checks repository evidence after the bounded GitHub delivery window.

## External recovery trigger

At either verifier slot, the external verifier must first confirm all of the following:

1. the corresponding primary scheduled run does not exist;
2. the corresponding internal guard run did not produce a recovery run for that slot/date;
3. no `Daily market update` run is queued or in progress;
4. current `main` contains the recovery-capable push-rerun contract;
5. a completed/success `Daily market update` push run created from that recovery-capable workflow version exists and its `update` job identity is known.

The freshness gate is deliberately slot-specific:

- **Morning:** `site/data/current.json.publication_status.requested_date` must be older than the current Asia/Taipei date. The rerun is allowed only from 10:00 through 13:59.
- **Evening:** H44 execution freshness is independent of market publication freshness. `data/traceability/market-events/execution/current.json` must be absent or have `attempted_date` older than the current Asia/Taipei date. The rerun is allowed only from 19:00 through 23:29. A malformed or unreadable H44 execution marker fails closed.

Only then may the external actuator re-run that push run's `update` job. It must not use `workflow_dispatch`, create a commit as a trigger, fetch MOA/TAPMC data itself, write agricultural data files, edit Buy Score, or synthesize market status.

## Why a push-run rerun is safe

A first-attempt push run remains committed-evidence-only and performs no external refresh. On `github.run_attempt > 1`, the workflow recomputes the current Asia/Taipei date and chooses recovery only when the matching slot-specific freshness gate is stale and execution is inside its bounded window:

- 10:00–13:59 Asia/Taipei + stale market publication → `morning-recovery`;
- 19:00–23:29 Asia/Taipei + stale/missing H44 execution freshness → `evening-recovery`.

A valid recovery rerun refreshes the normal GitHub-owned sources, refreshes 7556 requested-date evidence, and performs the normal build/validation/commit/Pages flow. Morning recovery skips H44. Evening recovery executes H44 even when the morning market publication already advanced to today.

After an evening H44 attempt, GitHub Actions writes machine-readable execution evidence under `data/traceability/market-events/execution/`. The evidence records the requested attempt date, run identity, execution status and source status. `source_unavailable` and `no_mapped_records` are still attempts, so they prevent duplicate external reruns while preserving the existing H44 source/LKG semantics. The execution evidence itself is explicitly `eligible_for_market_aggregate=false` and `affects_buy_score=false`.

If the relevant slot freshness is already current or the rerun occurs outside the bounded window, the workflow stays in committed-evidence-only mode. This prevents an arbitrary push-job rerun from silently becoming a data refresh.

## Data boundaries

- ChatGPT is an actuator/verifier, never a market or traceability data source.
- MOA 8066 remains the authoritative transaction source used by the current production aggregate.
- 7556 remains outside market aggregation and Buy Score.
- H44 remains `eligible_for_market_aggregate=false` and `affects_buy_score=false` and is never joined to 7556 `Tracecode`.
- Market closure still requires official calendar/feed evidence; an external recovery never infers closure from missing data.

## Green evidence after recovery

A recovered publication is green only after GitHub evidence shows the recovery update completed successfully, the relevant slot freshness reached the current Asia/Taipei date, the resulting data commit reached `main`, Pages deployment succeeded, and the deployment artifact matches `site/index.html` and `site/data/current.json` on `main`.
