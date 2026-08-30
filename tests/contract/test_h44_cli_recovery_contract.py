import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
ENTRYPOINT = ROOT / "src/tpw/__main__.py"


class H44CliRecoveryContractTest(unittest.TestCase):
    def test_zero_match_error_marks_same_date_context_before_propagating(self):
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn(
            'ZERO_MAPPED_ERROR = "traceability market events have no explicitly mapped records"',
            text,
        )
        self.assertIn('sys.argv[1] == "fetch-traceability-events"', text)
        self.assertIn("preserve_same_date_h44_as_stale", text)
        self.assertIn("raise\n", text)


if __name__ == "__main__":
    unittest.main()
