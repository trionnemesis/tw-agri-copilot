# External scheduler recovery

GitHub Actions remains the only data-fetch, build, validation, commit, and Pages publication layer. An external ChatGPT schedule may act only as a bounded recovery actuator when GitHub's own primary schedule and scheduler guard both fail to materialize a run.

## Normal path

- 09:17 Asia/Taipei: primary `Daily market update` morning schedule.
- 09:47: internal GitHub scheduler guard checks whether the 09:17 run exists.
- 10:30: external verifier checks repository evidence.
- 18:17 / 18:47 / 19:30 repeat the same pattern for evening.

## External recovery trigger

At 10:30 or 19:30, the external verifier must first confirm all of the following:

1. the corresponding primary scheduled run does not exist;
2. the corresponding internal guard run did not produce a recovery run;
3. no `Daily market update` run is queued or in progress;
4. `site/data/current.json.publication_status.requested_date` is older than the current Asia/Taipei date;
5. a completed `Daily market update` push run created from the current recovery-capable workflow exists.

Only then may the external actuator re-run that push run's `update` job. It must not fetch MOA/TAPMC data itself, write data files, edit Buy Score, or synthesize market status.

## Why a push-run rerun is safe

A first-attempt push run remains committed-evidence-only and performs no external refresh. On `github.run_attempt > 1`, the workflow checks whether publication is stale and whether execution is inside a bounded verifier window:

- 10:00–13:59 Asia/Taipei → `morning-recovery`;
- 19:00–22:59 Asia/Taipei → `evening-recovery`.

When both conditions hold, GitHub Actions recomputes `requested_date` from the current Asia/Taipei date, enables the same market fallback semantics as a scheduled run, refreshes 7556 requested-date evidence, and then performs the normal build/validation/commit/Pages flow. Morning recovery skips H44. Evening recovery refreshes H44.

If publication is already current or the rerun occurs outside the bounded windows, the workflow stays in committed-evidence-only mode. This prevents an arbitrary push-job rerun from silently becoming a data refresh.

## Data boundaries

- ChatGPT is an actuator/verifier, never a market or traceability data source.
- MOA 8066 remains the authoritative transaction source used by the current production aggregate.
- 7556 remains outside market aggregation and Buy Score.
- H44 remains `eligible_for_market_aggregate=false` and `affects_buy_score=false` and is never joined to 7556 `Tracecode`.
- Market closure still requires official calendar/feed evidence; an external recovery never infers closure from missing data.

## Green evidence after recovery

A recovered publication is green only after GitHub evidence shows the recovery update completed successfully, the resulting data commit reached `main`, Pages deployment succeeded, and the deployment artifact matches `site/index.html` and `site/data/current.json` on `main`.
