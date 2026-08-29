import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from tpw.scheduler_guard import (
    EVENING,
    MORNING,
    SchedulerGuardError,
    decide_recovery,
    dispatch_payload,
    expected_primary_time,
    matching_scheduled_runs,
    recovery_slot,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def scheduled_run(
    run_id: int,
    created_at: str,
    *,
    status: str = "completed",
    conclusion: str | None = "success",
    event: str = "schedule",
    branch: str = "main",
) -> dict[str, object]:
    return {
        "id": run_id,
        "event": event,
        "head_branch": branch,
        "created_at": created_at,
        "status": status,
        "conclusion": conclusion,
    }


class SchedulerGuardTest(unittest.TestCase):
    def test_guard_cron_and_manual_aliases_resolve_to_the_same_slots(self):
        self.assertEqual(recovery_slot("47 9 * * *"), MORNING)
        self.assertEqual(recovery_slot("morning"), MORNING)
        self.assertEqual(recovery_slot("47 18 * * *"), EVENING)
        self.assertEqual(recovery_slot("evening"), EVENING)
        with self.assertRaisesRegex(SchedulerGuardError, "unsupported recovery slot"):
            recovery_slot("noon")

    def test_expected_time_uses_taipei_date_and_bounded_delay(self):
        now = datetime(2026, 8, 29, 18, 47, tzinfo=TAIPEI)
        self.assertEqual(
            expected_primary_time(EVENING, now),
            datetime(2026, 8, 29, 18, 17, tzinfo=TAIPEI),
        )
        with self.assertRaisesRegex(SchedulerGuardError, "too early"):
            expected_primary_time(EVENING, datetime(2026, 8, 29, 18, 20, tzinfo=TAIPEI))

    def test_late_after_midnight_fails_closed_instead_of_backfilling(self):
        now = datetime(2026, 8, 30, 0, 15, tzinfo=TAIPEI)
        with self.assertRaisesRegex(SchedulerGuardError, "too late"):
            expected_primary_time(EVENING, now)

    def test_matching_run_counts_every_state_but_only_schedule_on_main(self):
        now = datetime(2026, 8, 29, 18, 47, tzinfo=TAIPEI)
        expected = datetime(2026, 8, 29, 18, 17, tzinfo=TAIPEI)
        runs = [
            scheduled_run(1, "2026-08-29T10:17:05Z", status="queued", conclusion=None),
            scheduled_run(2, "2026-08-29T10:30:00Z", status="in_progress", conclusion=None),
            scheduled_run(3, "2026-08-29T10:35:00Z", conclusion="failure"),
            scheduled_run(4, "2026-08-29T10:20:00Z", event="workflow_dispatch"),
            scheduled_run(5, "2026-08-29T10:20:00Z", branch="feature"),
            scheduled_run(6, "2026-08-29T09:00:00Z"),
        ]
        self.assertEqual(
            [run["id"] for run in matching_scheduled_runs(runs, expected, now)],
            [3, 2, 1],
        )

    def test_existing_failed_run_is_an_attempt_and_does_not_dispatch(self):
        now = datetime(2026, 8, 29, 18, 47, tzinfo=TAIPEI)
        runs = [scheduled_run(77, "2026-08-29T10:20:00Z", conclusion="failure")]
        decision = decide_recovery("evening", runs, now)
        self.assertEqual(decision.action, "skip")
        self.assertEqual(decision.matching_run["id"], 77)

    def test_missing_morning_run_dispatches_without_evening_semantics(self):
        now = datetime(2026, 8, 29, 9, 47, tzinfo=TAIPEI)
        decision = decide_recovery("47 9 * * *", [], now)
        self.assertEqual(decision.action, "dispatch")
        self.assertEqual(
            dispatch_payload(decision),
            {
                "ref": "main",
                "inputs": {
                    "as_of_date": "2026-08-29",
                    "schedule_slot": "morning-recovery",
                },
            },
        )

    def test_missing_evening_run_dispatches_evening_recovery(self):
        now = datetime(2026, 8, 29, 18, 47, tzinfo=TAIPEI)
        decision = decide_recovery("47 18 * * *", [], now)
        self.assertEqual(decision.action, "dispatch")
        self.assertEqual(decision.slot.dispatch_slot, "evening-recovery")
        self.assertEqual(decision.requested_date, "2026-08-29")

    def test_naive_time_and_excessively_late_guard_fail_closed(self):
        with self.assertRaisesRegex(SchedulerGuardError, "timezone-aware"):
            expected_primary_time(MORNING, datetime(2026, 8, 29, 9, 47))
        with self.assertRaisesRegex(SchedulerGuardError, "too late"):
            expected_primary_time(
                MORNING, datetime(2026, 8, 29, 14, 0, tzinfo=TAIPEI)
            )


if __name__ == "__main__":
    unittest.main()
