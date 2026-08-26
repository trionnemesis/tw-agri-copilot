# Work Order — TPW PR 1 Implementation

## Objective

Implement the bounded **PR 1 — Static Market Dashboard Foundation** described by `SPEC.md`, `PLAN.md`, and `TASKS.md`, then leave a locally verified worktree for independent main-agent acceptance.

## Required inputs

Read these files completely before editing implementation files:

1. `SPEC.md` — authoritative requirements; do not edit.
2. `PLAN.md` — scope, sequencing, risks, and acceptance gates.
3. `TASKS.md` — executable tasks and requirement IDs.
4. `references/00965_deep_analysis_20260826(1).html` — visual reference only.

## Owned scope

The implementation subagent owns all new PR 1 implementation, configuration, tests, generated fixture outputs, `DISCOVERY.md`, `README.md`, and `VERIFICATION.md`. It may update task checkboxes/status in `TASKS.md` as evidence is produced.

The subagent is not alone in the workspace. Preserve existing files and changes, do not revert others, and accommodate concurrent user/main-agent edits if any appear.

## Exclusions

- Do not edit or expand `SPEC.md`.
- Do not implement PR 2–5: rolling analytics/detail pages, seasonality/Buy Score/recommendations, LLM advice, or traceability.
- Do not fabricate crop codes, live API results, recommendation data, or verification evidence.
- Do not make required tests depend on live APIs.
- Do not add secrets, credentials, `.env` values, credential-bearing backups, or private data.
- Do not create Git commits, push branches, create/modify a GitHub repository, change GitHub settings, or deploy Pages.
- Do not copy the reference HTML's ETF content or embedded base64 images into `site/`.

## Execution contract

1. Perform bounded live public-data discovery first and write `DISCOVERY.md`. If the source is unavailable, record the exact non-sensitive failure, use clearly identified committed fixtures, and leave live evidence unverified.
2. Execute T-101 through T-110 in dependency order. Keep edits cohesive and scoped.
3. Use deterministic serialization, stable ordering, fixture-based required tests, and staging-before-promotion for last-known-good safety.
4. Generate a representative fixture-built site/report for a fixed as-of date; do not label fixture output as current live data.
5. Run targeted tests first, then the related/full local suite, package/static checks, and a double-build hash comparison.
6. Update `TASKS.md` only when evidence exists and write exact commands/results to `VERIFICATION.md`.
7. Stop and report a real blocker rather than weakening validation, deleting tests, inventing data, or expanding scope.

## Acceptance criteria

- `SPEC.md` and the reference HTML retain their recorded SHA-256 hashes.
- All implemented claims map to explicit PR 1 requirement IDs.
- The weighted example in `AC-003` is automated and returns the volume-weighted result, never 30.
- Empty/HTML/malformed/duplicate-page upstream cases fail safely without replacing last-known-good content.
- The same fixture/as-of build twice produces identical normalized, aggregate, report, and site hashes.
- Generated price views include the wholesale/non-retail disclaimer and escaped upstream strings.
- Generated site uses relative/base-path-safe links, works without JavaScript for core content, and contains no embedded base64 images.
- CI and workflow YAML are syntactically valid; remote execution/deployment remains unclaimed.
- `VERIFICATION.md` clearly separates verified, unverified, later-slice, and known-limit items.

## Required return schema

Return a concise report with exactly these sections:

1. **Summary** — what PR 1 now does.
2. **Changed** — key files/modules, not a full file dump.
3. **Validation** — commands and pass/fail counts.
4. **Requirement evidence** — FR/NFR/AC IDs covered.
5. **Unverified or blocked** — live API, GitHub, Pages, or environment gaps.
6. **Review focus** — highest-risk areas the main agent should independently inspect.

Do not claim completion solely because files exist; completion requires the validation and evidence above.
