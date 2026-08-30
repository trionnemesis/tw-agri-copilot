import datetime as dt
import pathlib
import unittest
from unittest import mock

from tpw import entrypoint


ROOT = pathlib.Path(__file__).parents[2]


class H44CliRecoveryContractTest(unittest.TestCase):
    def test_both_supported_cli_entry_points_use_shared_wrapper(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        module_entrypoint = (ROOT / "src/tpw/__main__.py").read_text(encoding="utf-8")
        self.assertIn('tpw = "tpw.entrypoint:main"', pyproject)
        self.assertIn("from .entrypoint import main", module_entrypoint)

    def test_default_h44_date_is_made_explicit_before_cli_parse(self):
        argv, requested_date = entrypoint._normalize_h44_argv(
            ["fetch-traceability-events"], today=dt.date(2026, 8, 30)
        )
        self.assertEqual(requested_date, "2026-08-30")
        self.assertEqual(
            argv, ["fetch-traceability-events", "--as-of", "2026-08-30"]
        )

    def test_zero_match_recovery_runs_before_original_error_propagates(self):
        error = ValueError(entrypoint.ZERO_MAPPED_ERROR)
        with mock.patch("tpw.entrypoint.cli.main", side_effect=error) as cli_main, mock.patch(
            "tpw.entrypoint.preserve_same_date_h44_as_stale"
        ) as recover:
            with self.assertRaisesRegex(ValueError, entrypoint.ZERO_MAPPED_ERROR):
                entrypoint.main(
                    ["fetch-traceability-events", "--as-of", "2026-08-30"]
                )
        cli_main.assert_called_once_with(
            ["fetch-traceability-events", "--as-of", "2026-08-30"]
        )
        recover.assert_called_once_with("2026-08-30")


if __name__ == "__main__":
    unittest.main()
