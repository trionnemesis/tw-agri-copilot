import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]


class DailyUpdateWorkflowTest(unittest.TestCase):
    def test_schedules_are_split_and_evening_h44_condition_matches(self):
        workflow = (ROOT / ".github/workflows/daily-update.yml").read_text()
        self.assertIn("cron: '17 9 * * *'", workflow)
        self.assertIn("cron: '17 18 * * *'", workflow)
        self.assertNotIn("cron: '0 9,18 * * *'", workflow)
        self.assertIn("github.event.schedule == '17 18 * * *'", workflow)
        self.assertIn("python3 -m tpw.traceability_snapshot --as-of", workflow)
