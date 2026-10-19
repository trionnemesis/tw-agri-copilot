import hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, unittest
from unittest import mock
from tpw.taipei_analysis import validate_taipei_analysis
REPO=pathlib.Path(__file__).parents[2]
IGNORED=shutil.ignore_patterns('.git','.venv','__pycache__','.pytest_cache','*.py[cod]','dist','build','*.egg-info','node_modules','playwright-report','test-results')
TAIPEI_OUTPUTS=('site/taipei/index.html','site/data/taipei/current.json','site/data/taipei/items.csv','site/data/taipei/observations.csv')
class TaipeiBuildTest(unittest.TestCase):
 def setUp(self):
  # Drive the real CLI against a throwaway copy so the fixture build never touches the published data/, site/ or reports/.
  workspace=tempfile.TemporaryDirectory();self.addCleanup(workspace.cleanup)
  self.root=pathlib.Path(workspace.name)/'repo';shutil.copytree(REPO,self.root,ignore=IGNORED,symlinks=True)
  patch=mock.patch('tpw.cli.ROOT',self.root);patch.start();self.addCleanup(patch.stop)
  self.command('seed-prototype','--as-of','2026-08-25')
 def command(self,*args,check=True):
  return subprocess.run([sys.executable,'-m','tpw',*args],cwd=self.root,check=check,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(REPO/'src')})
 def digest(self,paths):
  return {path:hashlib.sha256((self.root/path).read_bytes()).hexdigest() for path in paths}
 def test_build_publishes_taipei_scope_through_the_existing_build(self):
  self.command('build','--as-of','2026-08-25');first=self.digest(TAIPEI_OUTPUTS+('site/data/current.json',))
  self.command('build','--as-of','2026-08-25');self.assertEqual(first,self.digest(TAIPEI_OUTPUTS+('site/data/current.json',)))
  self.command('validate-data','--as-of','2026-08-25');self.command('verify-site','--as-of','2026-08-25')
  taipei=validate_taipei_analysis(json.loads((self.root/'site/data/taipei/current.json').read_text()))
  self.assertEqual((taipei['analysis_status'],taipei['as_of_date'],taipei['requested_date'],taipei['scope_status']),('published','2026-08-25','2026-08-25','all_markets_observed'))
  self.assertEqual(len(taipei['items']),20);self.assertTrue(all(item['recommendation_gate']['status'] in ('insufficient','not_evaluated') for item in taipei['items']))
  self.assertEqual({row['market_code'] for row in taipei['observations']},{'104','109'})
  national=json.loads((self.root/'site/data/current.json').read_text())
  self.assertNotIn('taipei',json.dumps(sorted(national)));self.assertEqual(len(national['scores']),20)
  page=(self.root/'site/taipei/index.html').read_text()
  self.assertIn("data-taipei-as-of='2026-08-25'",page);self.assertIn('批發市場平均行情',page);self.assertIn('不是產地',page);self.assertEqual(page.count('data-taipei-item='),20)
  self.assertIn("href='taipei/index.html'",(self.root/'site/index.html').read_text());self.assertIn("href='taipei/index.html'",(self.root/'site/methodology.html').read_text())
 def test_hand_edited_taipei_outputs_fail_closed(self):
  self.command('build','--as-of','2026-08-25')
  items=self.root/'site/data/taipei/items.csv';original=items.read_text()
  items.write_text(original.replace('not_evaluated','eligible',1))
  failed=self.command('verify-site','--as-of','2026-08-25',check=False);self.assertNotEqual(failed.returncode,0);self.assertIn('Taipei CSV',failed.stderr)
  items.write_text(original)
  current=self.root/'site/data/taipei/current.json';payload=json.loads(current.read_text())
  payload['items'][0]['today']['volume_kg']+=1;current.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')))
  failed=self.command('validate-data','--as-of','2026-08-25',check=False);self.assertNotEqual(failed.returncode,0);self.assertIn('Taipei analysis does not match',failed.stderr)
 def test_missing_taipei_route_fails_the_dated_site_check(self):
  # Without a date an absent Taipei payload is skipped, so a committed publication built before this scope still verifies.
  self.command('verify-site')
  self.command('build','--as-of','2026-08-25')
  for path in TAIPEI_OUTPUTS[1:]:(self.root/path).unlink()
  failed=self.command('verify-site','--as-of','2026-08-25',check=False);self.assertNotEqual(failed.returncode,0);self.assertIn('data/taipei/current.json',failed.stderr)
 def test_taipei_failure_is_isolated_from_the_nationwide_publication(self):
  national=('site/data/current.json','data/aggregates/daily/2026/08/2026-08-25.json','data/advice/2026/08/2026-08-25.json','data/quality/2026/08/2026-08-25.json','reports/daily/2026/08/2026-08-25.md')
  self.command('build','--as-of','2026-08-25');before=self.digest(national)
  path=self.root/'data/market/daily/2026/08/2026-08-25.json';rows=json.loads(path.read_text())
  drifted=next(row for row in rows if row['market_code']=='104');drifted['market_name']='台中市';path.write_text(json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')))
  result=self.command('build','--as-of','2026-08-25')
  self.assertIn('::warning title=Taipei analysis not published::TaipeiAnalysisError: 8066 row market name does not match the verified Taipei market 104',result.stdout)
  self.assertEqual(before,self.digest(national))
  self.command('validate-data','--as-of','2026-08-25');self.command('verify-site','--as-of','2026-08-25')
  taipei=validate_taipei_analysis(json.loads((self.root/'site/data/taipei/current.json').read_text()))
  self.assertEqual((taipei['analysis_status'],taipei['items'],taipei['observations']),('failed',[],[]))
  page=(self.root/'site/taipei/index.html').read_text();self.assertIn("data-taipei-analysis-status='failed'",page);self.assertNotIn('NT$',page)
  self.assertIn('臺北統計未發布',(self.root/'site/index.html').read_text())
