import json
import pathlib
import shutil
import tempfile
import unittest

from tpw.traceability_snapshot import ensure_traceability_snapshot


ROOT = pathlib.Path(__file__).parents[2]


class TraceabilitySnapshotIntegrationTest(unittest.TestCase):
    def isolated_root(self):
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        (root / "config").mkdir()
        shutil.copy2(ROOT / "config/produce.yml", root / "config/produce.yml")
        shutil.copy2(
            ROOT / "config/traceability.fixture.json",
            root / "config/traceability.fixture.json",
        )
        return temporary, root

    def test_fixture_context_is_archived_for_requested_date(self):
        temporary, root = self.isolated_root()
        with temporary:
            profile = ensure_traceability_snapshot("2026-08-29", root)
            rows_path = root / "data/traceability/daily/2026/08/2026-08-29.json"
            profile_path = root / "data/traceability/profiles/2026/08/2026-08-29.json"
            self.assertTrue(rows_path.exists())
            self.assertTrue(profile_path.exists())
            self.assertEqual(profile["as_of_date"], "2026-08-29")
            self.assertEqual(profile["source_status"], "fixture")
            rows = json.loads(rows_path.read_text())
            archived = json.loads(profile_path.read_text())
            self.assertEqual(archived["published_record_count"], len(rows))
            self.assertEqual(
                archived["published_record_count"],
                archived["active_record_count"]
                + archived["expired_record_count"]
                + archived["unknown_validity_count"],
            )
            forbidden = {"FarmerName", "StoreInfo", "LandSecNO", "farmer_name", "store_info"}
            self.assertTrue(all(not forbidden.intersection(row) for row in rows))

    def test_existing_exact_date_snapshot_is_not_replaced(self):
        temporary, root = self.isolated_root()
        with temporary:
            first = ensure_traceability_snapshot("2026-08-29", root)
            rows_path = root / "data/traceability/daily/2026/08/2026-08-29.json"
            profile_path = root / "data/traceability/profiles/2026/08/2026-08-29.json"
            before = (rows_path.read_bytes(), profile_path.read_bytes())
            second = ensure_traceability_snapshot("2026-08-29", root)
            self.assertEqual(first, second)
            self.assertEqual(before, (rows_path.read_bytes(), profile_path.read_bytes()))
