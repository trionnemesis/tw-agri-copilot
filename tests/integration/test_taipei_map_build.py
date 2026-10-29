import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
IGNORE = shutil.ignore_patterns('.git', '.venv', '__pycache__', 'node_modules', 'test-results', 'playwright-report')
OUTPUTS = ('site/taipei/map.html', 'site/data/taipei/map.json', 'site/data/taipei/map-observations.csv', 'site/assets/js/taipei-map.js', 'site/assets/css/taipei-map.css')

class TaipeiMapBuildTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'repo'
        shutil.copytree(REPO, self.root, ignore=IGNORE, symlinks=True)
        self.run_cli('seed-prototype', '--as-of', '2026-08-25')

    def run_cli(self, *args, check=True):
        return subprocess.run([sys.executable, '-m', 'tpw', *args], cwd=self.root, check=check, capture_output=True, text=True, env={**os.environ, 'PYTHONPATH': str(REPO / 'src')})

    def hashes(self):
        return [hashlib.sha256((self.root / p).read_bytes()).hexdigest() for p in OUTPUTS]

    def test_fixture_rebuild_mode_and_tampering(self):
        args = ('--as-of', '2026-08-25', '--taipei-map-mode', 'fixture')
        self.run_cli('build', *args); first = self.hashes()
        self.run_cli('build', *args); self.assertEqual(first, self.hashes())
        self.run_cli('validate-data', *args); self.run_cli('verify-site', *args)
        self.assertNotEqual(self.run_cli('verify-site', '--as-of', '2026-08-25', check=False).returncode, 0)
        payload = self.root / OUTPUTS[1]; original = payload.read_text()
        doc = json.loads(original); doc['inputs']['normalized_input_hash'] = 'sha256:' + '0' * 64
        payload.write_text(json.dumps(doc, ensure_ascii=False))
        self.assertNotEqual(self.run_cli('validate-data', *args, check=False).returncode, 0)
        payload.write_text(original)
        csv = self.root / OUTPUTS[2]; csv.write_text(csv.read_text() + 'tampered\n')
        self.assertNotEqual(self.run_cli('verify-site', *args, check=False).returncode, 0)

    def test_corrupt_sidecar_is_isolated_and_never_reloaded_for_failed_map(self):
        args = ('--as-of', '2026-08-25', '--taipei-map-mode', 'fixture')
        self.run_cli('build', *args)
        national = (self.root / 'site/data/current.json').read_bytes()
        (self.root / 'config/taipei-market-geography.json').write_text('{broken')
        self.run_cli('build', *args)
        self.assertEqual(national, (self.root / 'site/data/current.json').read_bytes())
        doc = json.loads((self.root / OUTPUTS[1]).read_text())
        self.assertEqual(doc['analysis_status'], 'failed')
        self.assertTrue(doc['failure_reason'])
        self.assertEqual((doc['series'], doc['statistics'], doc['comparisons']), ([], [], []))
        self.run_cli('validate-data', *args); self.run_cli('verify-site', *args)
        self.assertNotEqual(self.run_cli('validate-config', check=False).returncode, 0)

    def test_corrupt_svg_produces_failed_scope(self):
        args = ('--as-of', '2026-08-25', '--taipei-map-mode', 'fixture')
        self.run_cli('build', *args)
        (self.root / 'src/tpw/assets/taipei-districts.svg').write_text('<svg><script/></svg>')
        result = self.run_cli('build', *args, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = json.loads((self.root / OUTPUTS[1]).read_text())
        self.assertEqual(doc['analysis_status'], 'failed')
        self.assertEqual(doc['series'], [])
        self.run_cli('validate-data', *args); self.run_cli('verify-site', *args)
        self.assertNotEqual(self.run_cli('validate-config', check=False).returncode, 0)
