import copy
import json
import pathlib
import unittest

from tpw.agent_run import canonical_input_hash, validate_agent_run, validate_agent_run_file


ROOT = pathlib.Path(__file__).resolve().parents[2]


class AgentRunContractTest(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(
            (ROOT / "tests/fixtures/agent-run.valid.json").read_text(encoding="utf-8")
        )

    def test_fixture_is_valid(self):
        self.assertEqual(validate_agent_run(self.fixture), self.fixture)
        self.assertEqual(
            validate_agent_run_file(ROOT / "tests/fixtures/agent-run.valid.json"),
            self.fixture,
        )

    def test_run_id_and_input_hash_are_bounded(self):
        for field, value in (
            ("run_id", "../../workflow.yml"),
            ("input_hash", "sha256:not-a-digest"),
        ):
            invalid = copy.deepcopy(self.fixture)
            invalid[field] = value
            with self.assertRaises(ValueError):
                validate_agent_run(invalid)

    def test_unknown_fields_fail_closed(self):
        invalid = copy.deepcopy(self.fixture)
        invalid["score_override"] = 100
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_agent_run(invalid)

    def test_canonical_input_hash_is_order_independent(self):
        self.assertEqual(
            canonical_input_hash({"b": 2, "a": 1}),
            canonical_input_hash({"a": 1, "b": 2}),
        )
