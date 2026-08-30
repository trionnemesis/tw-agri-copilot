import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/daily-update.yml"


class H44WorkflowFallbackContractTest(unittest.TestCase):
    def h44_step(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        return text.split("      - name: Refresh H44 traceability market events\n", 1)[1].split(
            "      - name: Build, normalize, and validate\n", 1
        )[0]

    def test_zero_mapped_watchlist_records_degrade_without_blocking_publication(self):
        step = self.h44_step()
        self.assertIn("traceability_event_status=$?", step)
        self.assertIn(
            "traceability market events have no explicitly mapped records", step
        )
        self.assertIn("preserving exact-date fixture/LKG context", step)
        self.assertIn("exit 0", step)

    def test_other_h44_failures_still_fail_closed(self):
        step = self.h44_step()
        self.assertIn('exit "$traceability_event_status"', step)
        self.assertNotIn("|| true", step)


if __name__ == "__main__":
    unittest.main()
