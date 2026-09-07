import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]


class DailyUpdateWorkflowTest(unittest.TestCase):
    def test_schedules_are_split_timezone_aware_and_evening_h44_matches(self):
        workflow = (ROOT / ".github/workflows/daily-update.yml").read_text()
        self.assertIn("cron: '17 9 * * *'", workflow)
        self.assertIn("cron: '17 18 * * *'", workflow)
        self.assertEqual(workflow.count("timezone: 'Asia/Taipei'"), 2)
        self.assertNotIn("cron: '0 9,18 * * *'", workflow)
        self.assertIn("github.event.schedule == '17 18 * * *'", workflow)
        self.assertIn("inputs.schedule_slot != 'morning-recovery'", workflow)
        self.assertIn("evening-recovery", workflow)
        self.assertIn("[ \"$SCHEDULE_SLOT\" = 'morning-recovery' ]", workflow)
        self.assertIn("[ \"$SCHEDULE_SLOT\" = 'evening-recovery' ]", workflow)
        self.assertIn("python3 -m tpw.traceability_snapshot --as-of", workflow)

    def test_external_recovery_uses_slot_specific_freshness_and_records_h44_execution(self):
        workflow = (ROOT / ".github/workflows/daily-update.yml").read_text()
        self.assertIn(
            'if [[ "$committed_requested" < "$today" ]] && [ "$local_clock" -ge 1000 ]',
            workflow,
        )
        self.assertIn(
            'elif [[ "$h44_attempted_date" < "$today" ]] && [ "$local_clock" -ge 1900 ]',
            workflow,
        )
        self.assertIn('[ "$local_clock" -lt 2330 ]', workflow)
        self.assertIn(
            "data/traceability/market-events/execution/current.json",
            workflow,
        )
        self.assertIn('"record_type": "h44_refresh_execution"', workflow)
        self.assertIn('"execution_status": execution_status', workflow)
        self.assertIn('"source_status": source_status', workflow)
        self.assertIn('"eligible_for_market_aggregate": False', workflow)
        self.assertIn('"affects_buy_score": False', workflow)
        self.assertIn(
            "H44 refresh: no explicitly mapped watchlist records; execution freshness recorded.",
            workflow,
        )

    def test_recovery_guard_is_staggered_and_has_minimal_dispatch_permission(self):
        guard = (
            ROOT / ".github/workflows/daily-update-scheduler-guard.yml"
        ).read_text()
        self.assertIn("cron: '47 9 * * *'", guard)
        self.assertIn("cron: '47 18 * * *'", guard)
        self.assertEqual(guard.count("timezone: 'Asia/Taipei'"), 2)
        self.assertIn("actions: write", guard)
        self.assertIn("contents: read", guard)
        self.assertIn("python3 -m tpw.scheduler_guard", guard)
