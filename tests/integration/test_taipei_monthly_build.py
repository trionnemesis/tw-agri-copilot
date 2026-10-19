import hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, unittest
from unittest import mock
from tpw.taipei_monthly import validate_monthly_analysis
REPO=pathlib.Path(__file__).parents[2]
IGNORED=shutil.ignore_patterns('.git','.venv','__pycache__','.pytest_cache','*.py[cod]','dist','build','*.egg-info','node_modules','playwright-report','test-results')
MONTHLY_OUTPUTS=('site/taipei/monthly.html','site/data/taipei/monthly.json','site/data/taipei/monthly-retail.csv','site/data/taipei/monthly-supply.csv')
UNRELATED_OUTPUTS=('site/data/current.json','site/data/taipei/current.json','site/data/taipei/items.csv','data/aggregates/daily/2026/08/2026-08-25.json','reports/daily/2026/08/2026-08-25.md')
class TaipeiMonthlyBuildTest(unittest.TestCase):
 def setUp(self):
  # Drive the real CLI against a throwaway copy so fixture snapshots never reach the published data/, site/ or reports/.
  workspace=tempfile.TemporaryDirectory();self.addCleanup(workspace.cleanup)
  self.root=pathlib.Path(workspace.name)/'repo';shutil.copytree(REPO,self.root,ignore=IGNORED,symlinks=True)
  # CI seeds the working tree before the suite runs; start every test from no monthly snapshots.
  shutil.rmtree(self.root/'data/taipei-monthly',ignore_errors=True)
  patch=mock.patch('tpw.cli.ROOT',self.root);patch.start();self.addCleanup(patch.stop)
 def command(self,*args,check=True):
  return subprocess.run([sys.executable,'-m','tpw',*args],cwd=self.root,check=check,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(REPO/'src')})
 def digest(self,paths):
  return {path:hashlib.sha256((self.root/path).read_bytes()).hexdigest() for path in paths}
 def monthly(self):
  return validate_monthly_analysis(json.loads((self.root/'site/data/taipei/monthly.json').read_text()))
 def test_seeded_fixture_publishes_the_monthly_scope_through_build(self):
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25');first=self.digest(MONTHLY_OUTPUTS)
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25');self.assertEqual(first,self.digest(MONTHLY_OUTPUTS))
  self.command('validate-data','--as-of','2026-08-25');self.command('verify-site','--as-of','2026-08-25')
  monthly=self.monthly();self.assertEqual([(source['source'],source['status'],source['latest_period']) for source in monthly['sources']],[('retail','fixture','2025-12'),('supply','fixture','2025-12')])
  self.assertEqual(len(monthly['supply_categories']),5);self.assertTrue(all(item['commodity_family']=='unknown' for item in monthly['retail_items']))
  page=(self.root/'site/taipei/monthly.html').read_text();self.assertIn('原型測試資料',page);self.assertIn('不是今日報價',page);self.assertNotIn('NT$',page)
  self.assertIn("href='monthly.html'",(self.root/'site/taipei/index.html').read_text());self.assertIn("href='taipei/monthly.html'",(self.root/'site/methodology.html').read_text())
 def test_ingest_cli_is_idempotent_and_fails_closed_on_drift(self):
  raw=self.root.parent/'retail.csv';raw.write_text('序號,項目,平均(元/台斤)\n1,香蕉,30\n',encoding='utf-8')
  args=('ingest-taipei-monthly','--source','retail','--file',str(raw),'--period','2025-12','--resource-id','rid','--resource-name','114年12月份行情','--resource-url','https://data.taipei/x','--retrieved-at','2026-01-10T00:00:00Z','--license','test','--source-status','manual')
  self.assertIn('"status": "added"',self.command(*args).stdout);snapshot=self.root/'data/taipei-monthly/retail/2025-12.json';before=snapshot.read_bytes()
  self.assertIn('"status": "unchanged"',self.command(*args).stdout);self.assertEqual(before,snapshot.read_bytes())
  raw.write_text('日期,品名,平均_元/公斤\n2025-12-01,香蕉,50\n',encoding='utf-8')
  failed=self.command(*args,check=False);self.assertNotEqual(failed.returncode,0);self.assertIn('header does not match a pinned contract',failed.stderr);self.assertEqual(before,snapshot.read_bytes())
 def test_monthly_failure_is_isolated_from_other_publications(self):
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25');before=self.digest(UNRELATED_OUTPUTS)
  path=self.root/'data/taipei-monthly/retail/2025-12.json';snapshot=json.loads(path.read_text());snapshot['revisions'][0]['raw_text']=snapshot['revisions'][0]['raw_text'].replace('平均(元/台斤)','平均(元/公斤)');path.write_text(json.dumps(snapshot,ensure_ascii=False))
  result=self.command('build','--as-of','2026-08-25')
  self.assertIn('::warning title=Taipei monthly analysis not published::TaipeiMonthlyError: retail header does not match a pinned contract',result.stdout)
  self.assertEqual(before,self.digest(UNRELATED_OUTPUTS))
  self.command('validate-data','--as-of','2026-08-25');self.command('verify-site','--as-of','2026-08-25')
  monthly=self.monthly();self.assertEqual((monthly['analysis_status'],monthly['retail_items'],monthly['supply_categories']),('failed',[],[]))
  self.assertIn("data-monthly-analysis-status='failed'",(self.root/'site/taipei/monthly.html').read_text())
 def test_hand_edited_monthly_outputs_fail_closed(self):
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25')
  retail=self.root/'site/data/taipei/monthly-retail.csv';original=retail.read_text();retail.write_text(original.replace('fixture','live',1))
  failed=self.command('verify-site','--as-of','2026-08-25',check=False);self.assertNotEqual(failed.returncode,0);self.assertIn('Taipei monthly CSV',failed.stderr)
  retail.write_text(original);current=self.root/'site/data/taipei/monthly.json';payload=json.loads(current.read_text())
  payload['retail_items'][0]['median_price_raw']+=1;current.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')))
  failed=self.command('validate-data','--as-of','2026-08-25',check=False);self.assertNotEqual(failed.returncode,0);self.assertIn('Taipei monthly analysis does not match',failed.stderr)
 def test_without_snapshots_the_scope_publishes_no_numbers(self):
  as_of=json.loads((self.root/'site/data/current.json').read_text())['as_of_date']
  self.command('build','--as-of',as_of);self.command('validate-data','--as-of',as_of);self.command('verify-site','--as-of',as_of)
  monthly=self.monthly();self.assertEqual([source['status'] for source in monthly['sources']],['not_ingested','not_ingested'])
  self.assertEqual((monthly['retail_items'],monthly['supply_categories']),([],[]));self.assertIn('尚未匯入',(self.root/'site/taipei/monthly.html').read_text())
