import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-update.yml"


class ExternalRerunRecoveryContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_push_attempt_one_remains_committed_evidence_only(self):
        self.assertIn("RUN_ATTEMPT: ${{ github.run_attempt }}", self.workflow)
        self.assertIn("if [ \"${RUN_ATTEMPT:-1}\" -gt 1 ]; then", self.workflow)
        self.assertIn("external_recovery=false", self.workflow)

    def test_stale_rerun_recomputes_requested_date_in_taipei(self):
        self.assertIn('today="$(TZ=Asia/Taipei date +%F)"', self.workflow)
        self.assertIn('committed_requested=', self.workflow)
        self.assertIn('requested="$today"', self.workflow)
        self.assertIn('allow_fallback=true', self.workflow)
        self.assertIn('external_recovery=true', self.workflow)

    def test_recovery_is_bounded_to_verifier_windows(self):
        self.assertIn('[ "$local_hour" -ge 10 ] && [ "$local_hour" -lt 14 ]', self.workflow)
        self.assertIn("effective_slot='morning-recovery'", self.workflow)
        self.assertIn('[ "$local_hour" -ge 19 ] && [ "$local_hour" -lt 23 ]', self.workflow)
        self.assertIn("effective_slot='evening-recovery'", self.workflow)

    def test_market_and_7556_refresh_only_on_non_push_or_explicit_rerun_recovery(self):
        condition = "if: github.event_name != 'push' || steps.dates.outputs.external_recovery == 'true'"
        self.assertEqual(self.workflow.count(condition), 2)
        self.assertIn("PYTHONPATH=src python3 -m tpw fetch-traceability --as-of \"$AS_OF_DATE\"", self.workflow)
        self.assertIn("PYTHONPATH=src python3 -m tpw.traceability_snapshot --as-of \"$AS_OF_DATE\"", self.workflow)

    def test_7556_refresh_has_a_publication_runtime_budget(self):
        self.assertIn("TRACEABILITY_TIMEOUT_SECONDS: '300'", self.workflow)
        self.assertIn('timeout "${TRACEABILITY_TIMEOUT_SECONDS}s" env PYTHONPATH=src python3 -m tpw fetch-traceability', self.workflow)
        self.assertIn('if [ "$traceability_status" -eq 124 ]; then', self.workflow)
        self.assertIn('using requested-date fixture/LKG context', self.workflow)
        self.assertIn("PYTHONPATH=src python3 -m tpw.traceability_snapshot --as-of \"$AS_OF_DATE\"", self.workflow)

    def test_h44_remains_evening_only_for_rerun_recovery(self):
        self.assertIn(
            "github.event_name == 'push' && steps.dates.outputs.external_recovery == 'true' && steps.dates.outputs.effective_slot == 'evening-recovery'",
            self.workflow,
        )

    def test_publication_rebases_only_when_newer_main_has_no_publication_changes(self):
        self.assertIn('base_before_update="$(git rev-parse HEAD^)"', self.workflow)
        self.assertIn("git fetch origin main", self.workflow)
        self.assertIn("git diff --name-only \"$base_before_update\" origin/main | grep -Eq '^(data|reports|site)/'", self.workflow)
        self.assertIn("refusing to overwrite it", self.workflow)
        self.assertIn("git rebase origin/main", self.workflow)
        self.assertIn("git push origin HEAD:main", self.workflow)


if __name__ == "__main__":
    unittest.main()
