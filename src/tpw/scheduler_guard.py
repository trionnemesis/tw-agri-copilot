from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
WORKFLOW_FILE = "daily-update.yml"
API_VERSION = "2022-11-28"
MIN_RECOVERY_DELAY = timedelta(minutes=20)
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SchedulerGuardError(RuntimeError):
    """Raised when the guard cannot make a safe recovery decision."""


@dataclass(frozen=True)
class RecoverySlot:
    name: str
    guard_cron: str
    primary_cron: str
    primary_hour: int
    primary_minute: int
    dispatch_slot: str


MORNING = RecoverySlot(
    name="morning",
    guard_cron="47 9 * * *",
    primary_cron="17 9 * * *",
    primary_hour=9,
    primary_minute=17,
    dispatch_slot="morning-recovery",
)
EVENING = RecoverySlot(
    name="evening",
    guard_cron="47 18 * * *",
    primary_cron="17 18 * * *",
    primary_hour=18,
    primary_minute=17,
    dispatch_slot="evening-recovery",
)
SLOT_ALIASES = {
    MORNING.name: MORNING,
    MORNING.guard_cron: MORNING,
    EVENING.name: EVENING,
    EVENING.guard_cron: EVENING,
}


@dataclass(frozen=True)
class GuardDecision:
    action: str
    slot: RecoverySlot
    expected_at: datetime
    matching_run: dict[str, Any] | None

    @property
    def requested_date(self) -> str:
        return self.expected_at.date().isoformat()


def recovery_slot(value: str) -> RecoverySlot:
    try:
        return SLOT_ALIASES[value]
    except KeyError as exc:
        allowed = ", ".join(sorted(SLOT_ALIASES))
        raise SchedulerGuardError(
            f"unsupported recovery slot {value!r}; expected one of: {allowed}"
        ) from exc


def expected_primary_time(slot: RecoverySlot, now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise SchedulerGuardError("current time must be timezone-aware")
    local_now = now.astimezone(TAIPEI)
    expected = local_now.replace(
        hour=slot.primary_hour,
        minute=slot.primary_minute,
        second=0,
        microsecond=0,
    )
    if expected > local_now:
        expected -= timedelta(days=1)
    delay = local_now - expected
    if delay < MIN_RECOVERY_DELAY:
        raise SchedulerGuardError(
            f"recovery guard is too early for {slot.primary_cron}: delay={delay}"
        )
    return expected


def _parse_github_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def matching_scheduled_runs(
    runs: Iterable[dict[str, Any]], expected_at: datetime, observed_at: datetime
) -> list[dict[str, Any]]:
    window_start = expected_at.astimezone(timezone.utc) - timedelta(minutes=2)
    window_end = observed_at.astimezone(timezone.utc) + timedelta(minutes=2)
    matches: list[dict[str, Any]] = []
    for run in runs:
        created_at = _parse_github_time(run.get("created_at"))
        if (
            run.get("event") == "schedule"
            and run.get("head_branch") == "main"
            and created_at is not None
            and window_start <= created_at <= window_end
        ):
            matches.append(run)
    return sorted(
        matches,
        key=lambda run: _parse_github_time(run.get("created_at"))
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def decide_recovery(
    trigger: str, runs: Iterable[dict[str, Any]], now: datetime
) -> GuardDecision:
    slot = recovery_slot(trigger)
    expected_at = expected_primary_time(slot, now)
    matches = matching_scheduled_runs(runs, expected_at, now)
    return GuardDecision(
        action="skip" if matches else "dispatch",
        slot=slot,
        expected_at=expected_at,
        matching_run=matches[0] if matches else None,
    )


def dispatch_payload(decision: GuardDecision) -> dict[str, Any]:
    if decision.action != "dispatch":
        raise SchedulerGuardError("cannot build a dispatch payload for a skip decision")
    return {
        "ref": "main",
        "inputs": {
            "as_of_date": decision.requested_date,
            "schedule_slot": decision.slot.dispatch_slot,
        },
    }


class GitHubActionsClient:
    def __init__(self, repository: str, token: str, api_url: str) -> None:
        if not REPOSITORY_RE.fullmatch(repository):
            raise SchedulerGuardError("repository must use owner/name format")
        if not token:
            raise SchedulerGuardError("GITHUB_TOKEN is required")
        self.repository = repository
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "tw-agri-copilot-scheduler-guard",
                "X-GitHub-Api-Version": API_VERSION,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise SchedulerGuardError(
                f"GitHub API {method} {path} returned {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise SchedulerGuardError(
                f"GitHub API {method} {path} was unavailable: {exc.reason}"
            ) from exc
        if not body:
            return None
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SchedulerGuardError("GitHub API returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise SchedulerGuardError("GitHub API response must be an object")
        return decoded

    def list_primary_runs(self) -> list[dict[str, Any]]:
        query = urlencode({"branch": "main", "event": "schedule", "per_page": 100})
        workflow = quote(WORKFLOW_FILE, safe="")
        response = self._request(
            "GET",
            f"/repos/{self.repository}/actions/workflows/{workflow}/runs?{query}",
        )
        runs = None if response is None else response.get("workflow_runs")
        if not isinstance(runs, list) or not all(isinstance(run, dict) for run in runs):
            raise SchedulerGuardError("GitHub API response has no workflow_runs list")
        return runs

    def dispatch_recovery(self, decision: GuardDecision) -> None:
        workflow = quote(WORKFLOW_FILE, safe="")
        self._request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{workflow}/dispatches",
            dispatch_payload(decision),
        )


def _write_runner_metadata(decision: GuardDecision) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"action={decision.action}\n")
            output.write(f"requested_date={decision.requested_date}\n")
            output.write(f"schedule_slot={decision.slot.dispatch_slot}\n")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        run = decision.matching_run
        lines = [
            "### Daily update scheduler guard",
            "",
            f"- Primary slot: `{decision.slot.primary_cron}` (`Asia/Taipei`)",
            f"- Requested date: `{decision.requested_date}`",
            f"- Decision: **{decision.action}**",
        ]
        if run is not None:
            lines.extend(
                [
                    f"- Existing run: `{run.get('id', 'unknown')}`",
                    f"- Existing state: `{run.get('status', 'unknown')}` / "
                    f"`{run.get('conclusion') or 'none'}`",
                ]
            )
        else:
            lines.append(f"- Recovery slot: `{decision.slot.dispatch_slot}`")
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")


def _parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SchedulerGuardError("--now must use ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchedulerGuardError("--now must include a timezone")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dispatch a bounded recovery only when a primary scheduled run is absent."
    )
    parser.add_argument("--slot", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--now", help="ISO-8601 override for deterministic verification")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    client = GitHubActionsClient(
        repository=args.repository,
        token=os.environ.get("GITHUB_TOKEN", ""),
        api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    observed_at = _parse_now(args.now)
    decision = decide_recovery(args.slot, client.list_primary_runs(), observed_at)
    if decision.action == "dispatch" and not args.dry_run:
        client.dispatch_recovery(decision)
    _write_runner_metadata(decision)

    result = {
        "action": "dry-run" if args.dry_run and decision.action == "dispatch" else decision.action,
        "primary_cron": decision.slot.primary_cron,
        "requested_date": decision.requested_date,
        "schedule_slot": decision.slot.dispatch_slot,
        "matching_run_id": (
            None if decision.matching_run is None else decision.matching_run.get("id")
        ),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
