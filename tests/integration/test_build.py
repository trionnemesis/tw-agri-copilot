import hashlib, html, io, json, os, pathlib, re, shutil, subprocess, sys, tempfile, unittest
from collections import Counter
from unittest import mock
from tpw.cli import ingest, backfill, main, persist_seasonality, refresh_seasonality, swap_all, verify_site
from tpw.market import UpstreamUnavailable
REPO=pathlib.Path(__file__).parents[2]
ROOT=REPO
# Everything .gitignore excludes, plus .git. A local .venv or a browser run's test-results/
# would otherwise be copied for every test, and copytree dereferences symlinks by default,
# so one dangling link inside an ignored directory would error the whole class.
IGNORED=shutil.ignore_patterns('.git','.venv','__pycache__','.pytest_cache','*.py[cod]','dist','build','*.egg-info','node_modules','playwright-report','test-results')
def official_seasonality_rows(month_number):
 return [
  {'category':'fruit','display_name':'香蕉','variety':'北蕉','county':'屏東縣','district':'高樹鄉','months':[month_number]},
  {'category':'vegetable','display_name':'胡瓜','variety':'黑刺','county':'屏東縣','district':'里港鄉','months':[month_number]},
 ]
class BuildTest(unittest.TestCase):
 def setUp(self):
  # These tests drive the real CLI, which writes data/, site/ and reports/ below tpw.cli.ROOT.
  # Point the CLI and this module's assertions at a throwaway copy of the repository so a test
  # run can never replace published live content with prototype fixture values.
  workspace=tempfile.TemporaryDirectory();self.addCleanup(workspace.cleanup)
  work=pathlib.Path(workspace.name)/'repo';shutil.copytree(REPO,work,ignore=IGNORED,symlinks=True)
  for patch in (mock.patch.object(sys.modules[__name__],'ROOT',work),mock.patch('tpw.cli.ROOT',work)):patch.start();self.addCleanup(patch.stop)
 def command(self,*args): subprocess.run([sys.executable,"-m","tpw",*args],cwd=ROOT,check=True,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(REPO/'src')})
 def command_from_temp_src(self,*args):
  # Unlike command() above (always PYTHONPATH=REPO/src, the real repository), this imports tpw
  # from the throwaway copy's OWN src/. Needed only when a test edits config/produce-categories.json
  # or src/tpw/assets/produce-icons.svg inside the copy: tpw.categories.default_category_registry()
  # and tpw.produce_icons.SPRITE_PATH are both derived from the importing package's own location
  # (pathlib.Path(__file__)), not from ROOT/cwd, so a subprocess started with the real repo's
  # PYTHONPATH would silently keep reading the real registry/sprite instead of the copy's.
  subprocess.run([sys.executable,"-m","tpw",*args],cwd=ROOT,check=True,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT/'src')})
 def test_double_build_and_site_contract(self):
  ingest(json.loads((ROOT/'tests/fixtures/market_success.json').read_text()),'2026-08-25','2026-08-25')
  self.command("build","--as-of","2026-08-25"); first=hashlib.sha256((ROOT/"site/index.html").read_bytes()).hexdigest(); self.command("build","--as-of","2026-08-25"); self.assertEqual(first,hashlib.sha256((ROOT/"site/index.html").read_bytes()).hexdigest()); self.command("validate-data","--as-of","2026-08-25"); self.command("verify-site")
  for p in ["site/index.html","site/daily/2026/08/2026-08-25.html","reports/daily/2026/08/2026-08-25.md"]: self.assertTrue((ROOT/p).exists())
  html=(ROOT/"site/index.html").read_text(); self.assertIn("批發市場平均行情",html); self.assertIn("資料狀態：fixture",html); self.assertIn("id='recommendations'",html); self.assertNotIn("base64",html)
  from tpw.render import page
  self.assertIn("&lt;script&gt;",page("<script>","ok"))
  from tpw.render import build_site
  with tempfile.TemporaryDirectory() as raw:
   rendered=pathlib.Path(raw); build_site([{'canonical_id':'banana','display_name':'香蕉','category':'fruit','weighted_avg_price_twd_per_kg':20,'total_volume_kg':10}],'2026-08-25',rendered,"<live>")
   self.assertIn("資料狀態：&lt;live&gt;",(rendered/'index.html').read_text())
 def test_mismatch_and_backfill_windows(self):
  with self.assertRaises(subprocess.CalledProcessError): self.command('build','--as-of','2026-07-01')
  calls=[]; self.assertEqual(backfill(9,'2026-08-25',lambda a,b:calls.append((a,b))),calls)
  self.assertEqual(calls,[('2026-08-17','2026-08-20'),('2026-08-21','2026-08-24'),('2026-08-25','2026-08-25')])
 def test_ingest_metadata_correction_and_lkg(self):
  success=json.loads((ROOT/'tests/fixtures/market_success.json').read_text()); self.assertEqual(ingest(success,'2026-08-25','2026-08-25','first'),3)
  path=ROOT/'data/market/daily/2026/08/2026-08-25.json'; meta_path=ROOT/'data/source-meta/2026-08-25.json'; before=path.read_bytes(); meta_before=meta_path.read_bytes(); meta=json.loads(meta_before); self.assertEqual(meta['record_count'],3); self.assertEqual(meta['http_status'],200); self.assertIn('https://',meta['source_url'])
  ingest(success,'2026-08-25','2026-08-25','second'); self.assertEqual(before,path.read_bytes()); self.assertEqual(meta_before,meta_path.read_bytes())
  correction=json.loads((ROOT/'tests/fixtures/market_correction.json').read_text()); ingest(correction,'2026-08-25','2026-08-25','second'); rows=json.loads(path.read_text()); self.assertEqual(len([r for r in rows if r['crop_code']=='A1' and r['market_code']=='104']),1)
  self.assertEqual([r for r in rows if r['crop_code']=='A1' and r['market_code']=='104'][0]['avg_price_twd_per_kg'],21)
  saved=path.read_bytes()
  with self.assertRaises(ValueError): ingest([], '2026-08-25','2026-08-25')
  self.assertEqual(saved,path.read_bytes()); self.assertNotEqual(before,b'')
 def test_market_closure_is_persisted_without_fake_market_rows(self):
  closed=[dict(row,交易日期='115.08.28') for row in json.loads((ROOT/'tests/fixtures/market_closed.json').read_text())]
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data').mkdir()
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml')
   shutil.copy2(ROOT/'config/market-calendar.json',isolated/'config/market-calendar.json');shutil.copytree(ROOT/'data/market-calendar',isolated/'data/market-calendar')
   with mock.patch('tpw.cli.ROOT',isolated):
    self.assertEqual(ingest(closed,'2026-08-28','2026-08-28','live-check'),0)
   status=json.loads((isolated/'data/market-status/current.json').read_text())
   self.assertEqual(status['status'],'market_closed');self.assertEqual(status['requested_date'],'2026-08-28')
   self.assertEqual(status['calendar']['schedule_status'],'scheduled_closed')
   self.assertFalse((isolated/'data/market/daily/2026/08/2026-08-28.json').exists())
 def test_market_closure_banner_matches_public_json(self):
  from tpw.render import build_site
  rows=[{'canonical_id':'banana','display_name':'香蕉','category':'fruit','weighted_avg_price_twd_per_kg':20,'total_volume_kg':10}]
  status={'schema_version':'1.0','requested_date':'2026-08-27','resolved_date':'2026-08-26','status':'market_closed','source_status':'success','expected_watchlist_count':20,'covered_watchlist_count':0,'observed_record_count':4}
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);build_site(rows,'2026-08-26',root,publication_status=status)
   html=(root/'index.html').read_text();current=json.loads((root/'data/current.json').read_text())
   self.assertIn('2026-08-27 行情來源回報休市',html);self.assertNotIn('官方公告休市',html)
   self.assertEqual(current['publication_status'],status)
 def test_official_calendar_closure_banner_exposes_lineage(self):
  from tpw.market_calendar import evaluate_market_calendar
  from tpw.publication import apply_market_calendar
  from tpw.render import build_site
  rows=[{'canonical_id':'banana','display_name':'香蕉','category':'fruit','weighted_avg_price_twd_per_kg':20,'total_volume_kg':10}]
  status={'schema_version':'1.0','requested_date':'2026-08-28','resolved_date':'2026-08-26','status':'market_closed','source_status':'success','feed_status':'empty','expected_watchlist_count':20,'covered_watchlist_count':0,'observed_record_count':25}
  status=apply_market_calendar(status,evaluate_market_calendar(ROOT,'2026-08-28'));status['resolved_date']='2026-08-26'
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);build_site(rows,'2026-08-26',root,publication_status=status)
   rendered=(root/'index.html').read_text();current=json.loads((root/'data/current.json').read_text())
  self.assertIn('2026-08-28 臺北一、臺北二官方公告休市',rendered);self.assertIn('中元節後循例休市',rendered);self.assertIn('查看官方休市日程',rendered)
  self.assertEqual(current['publication_status']['calendar']['content_hash'],'sha256:97775f09206973fb5c9f77d9c9777736710ce4a93c6e6e911a59388c53552b55')
 def test_season_search_name_is_html_escaped(self):
  from tpw.render import _season_page
  catalog=[{'canonical_id':None,'display_name':"木瓜' <script>",'category':'fruit','county_count':1,'variety_count':0,'counties':['高雄市']}]
  rendered=_season_page(catalog,[],[])
  self.assertIn("data-search-name='木瓜&#x27; &lt;script&gt;'",rendered);self.assertNotIn('<script>',rendered)
  self.assertIn("href='../assets/icons/produce.svg#produce-fruit-fallback'",rendered);self.assertIn("data-icon-fidelity='category_fallback'",rendered)
 def test_seasonality_transient_failure_uses_fallback_then_lkg(self):
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data').mkdir()
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml');shutil.copy2(ROOT/'config/seasonality.manual.json',isolated/'config/seasonality.manual.json')
   unavailable=mock.patch('tpw.cli.fetch_official',side_effect=UpstreamUnavailable('temporary'))
   with mock.patch('tpw.cli.ROOT',isolated),unavailable:
    result=persist_seasonality('2026-08')
   self.assertEqual(result['source_status'],'fallback')
   fallback=json.loads((isolated/'data/seasonality/2026-08.json').read_text())
   self.assertTrue(all(row['source_status']=='fallback' for row in fallback))
   shutil.copy2(ROOT/'data/seasonality/2026-08.json',isolated/'data/seasonality/2026-08.json')
   (isolated/'data/seasonality/catalog').mkdir(exist_ok=True)
   shutil.copy2(ROOT/'data/seasonality/catalog/2026-08.json',isolated/'data/seasonality/catalog/2026-08.json')
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',side_effect=UpstreamUnavailable('temporary')):
    result=persist_seasonality('2026-08')
   self.assertEqual(result['source_status'],'stale')
   stale=json.loads((isolated/'data/seasonality/catalog/2026-08.json').read_text())
   self.assertTrue(all(row['source_status']=='stale' for row in stale))
   before=(isolated/'data/seasonality/catalog/2026-08.json').read_bytes()
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',side_effect=ValueError('schema drift')):
    with self.assertRaisesRegex(ValueError,'schema drift'):persist_seasonality('2026-08')
   self.assertEqual(before,(isolated/'data/seasonality/catalog/2026-08.json').read_bytes())
 def test_seasonality_catalog_decrease_preserves_same_month_lkg(self):
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data/seasonality/catalog').mkdir(parents=True)
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml');shutil.copy2(ROOT/'config/seasonality.manual.json',isolated/'config/seasonality.manual.json')
   shutil.copy2(ROOT/'data/seasonality/2026-08.json',isolated/'data/seasonality/2026-08.json')
   shutil.copy2(ROOT/'data/seasonality/catalog/2026-08.json',isolated/'data/seasonality/catalog/2026-08.json')
   before=(isolated/'data/seasonality/catalog/2026-08.json').read_bytes()
   partial=[{'category':'fruit','display_name':'香蕉','variety':'北蕉','county':'屏東縣','district':'高樹鄉','months':[8]},{'category':'vegetable','display_name':'胡瓜','variety':'黑刺','county':'屏東縣','district':'里港鄉','months':[8]}]
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',return_value=partial):
    result=persist_seasonality('2026-08',fetched_at='fixture')
   self.assertEqual(result['source_status'],'stale')
   self.assertEqual(len(json.loads(before)),result['catalog_count'])
   self.assertTrue(all(row['source_status']=='stale' for row in json.loads((isolated/'data/seasonality/catalog/2026-08.json').read_text())))
 def test_seasonality_refresh_reuses_live_and_force_fetches(self):
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data').mkdir()
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml');shutil.copy2(ROOT/'config/seasonality.manual.json',isolated/'config/seasonality.manual.json')
   rows=official_seasonality_rows(8)
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',return_value=rows):
    persist_seasonality('2026-08',fetched_at='initial')
    catalog_path=isolated/'data/seasonality/catalog/2026-08.json';watch_path=isolated/'data/seasonality/2026-08.json';before=(catalog_path.read_bytes(),watch_path.read_bytes())
    fetcher=mock.Mock()
    reused=refresh_seasonality('2026-08',fetcher=fetcher)
    fetcher.assert_not_called();self.assertEqual(reused['action'],'reuse');self.assertEqual(before,(catalog_path.read_bytes(),watch_path.read_bytes()))
    refreshed=refresh_seasonality('2026-08',force=True,fetcher=lambda month:persist_seasonality(month,fetched_at='forced'))
   self.assertEqual((refreshed['action'],refreshed['reason'],refreshed['source_status']),('refresh','forced','live'))
   catalog=json.loads(catalog_path.read_text());self.assertTrue(all(row['fetched_at']=='forced' and row['source_status']=='live' for row in catalog))
 def test_seasonality_month_boundary_preserves_history_and_uses_new_month_fallback(self):
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data').mkdir()
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml');shutil.copy2(ROOT/'config/seasonality.manual.json',isolated/'config/seasonality.manual.json')
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',return_value=official_seasonality_rows(8)):
    persist_seasonality('2026-08',fetched_at='august')
   august_paths=(isolated/'data/seasonality/2026-08.json',isolated/'data/seasonality/catalog/2026-08.json');august_before=tuple(path.read_bytes() for path in august_paths)
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',return_value=official_seasonality_rows(9)):
    september=refresh_seasonality('2026-09',fetcher=lambda month:persist_seasonality(month,fetched_at='september'))
   self.assertEqual((september['action'],september['reason'],september['source_status']),('refresh','missing_snapshot','live'));self.assertEqual(august_before,tuple(path.read_bytes() for path in august_paths))
   september_paths=(isolated/'data/seasonality/2026-09.json',isolated/'data/seasonality/catalog/2026-09.json');september_before=tuple(path.read_bytes() for path in september_paths)
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',side_effect=UpstreamUnavailable('temporary')):
    october=refresh_seasonality('2026-10')
   self.assertEqual((october['action'],october['reason'],october['source_status']),('refresh','missing_snapshot','fallback'));self.assertEqual(august_before,tuple(path.read_bytes() for path in august_paths));self.assertEqual(september_before,tuple(path.read_bytes() for path in september_paths))
   self.assertTrue(all(row['month']=='2026-10' and row['source_status']=='fallback' for row in json.loads((isolated/'data/seasonality/2026-10.json').read_text())))
 def test_wrong_month_cache_is_never_reused_as_target_month_lkg(self):
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data').mkdir()
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml');shutil.copy2(ROOT/'config/seasonality.manual.json',isolated/'config/seasonality.manual.json')
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',return_value=official_seasonality_rows(8)):
    persist_seasonality('2026-08',fetched_at='august')
   for source,target in ((isolated/'data/seasonality/2026-08.json',isolated/'data/seasonality/2026-09.json'),(isolated/'data/seasonality/catalog/2026-08.json',isolated/'data/seasonality/catalog/2026-09.json')):shutil.copy2(source,target)
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',side_effect=UpstreamUnavailable('temporary')):
    result=refresh_seasonality('2026-09')
   self.assertEqual((result['action'],result['reason'],result['source_status']),('refresh','month_mismatch','fallback'))
   for path in (isolated/'data/seasonality/2026-09.json',isolated/'data/seasonality/catalog/2026-09.json'):
    self.assertTrue(all(row['month']=='2026-09' and row['source_status']=='fallback' for row in json.loads(path.read_text())))
 def test_forced_seasonality_failure_keeps_same_month_lkg_and_schema_drift_bytes(self):
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data').mkdir()
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml');shutil.copy2(ROOT/'config/seasonality.manual.json',isolated/'config/seasonality.manual.json')
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',return_value=official_seasonality_rows(8)):
    persist_seasonality('2026-08',fetched_at='initial')
   catalog_path=isolated/'data/seasonality/catalog/2026-08.json';watch_path=isolated/'data/seasonality/2026-08.json';live_count=len(json.loads(catalog_path.read_text()))
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',side_effect=UpstreamUnavailable('temporary')):
    stale=refresh_seasonality('2026-08',force=True)
   self.assertEqual((stale['action'],stale['reason'],stale['source_status'],stale['catalog_count']),('refresh','forced','stale',live_count))
   for path in (catalog_path,watch_path):self.assertTrue(all(row['source_status']=='stale' for row in json.loads(path.read_text())))
   before=(catalog_path.read_bytes(),watch_path.read_bytes())
   with mock.patch('tpw.cli.ROOT',isolated),mock.patch('tpw.cli.fetch_official',side_effect=ValueError('schema drift')):
    with self.assertRaisesRegex(ValueError,'schema drift'):refresh_seasonality('2026-08',force=True)
   self.assertEqual(before,(catalog_path.read_bytes(),watch_path.read_bytes()))
 def test_seasonality_refresh_rejects_malformed_json_and_workflow_uses_shared_policy(self):
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);path=isolated/'data/seasonality/catalog/2026-08.json';path.parent.mkdir(parents=True);path.write_text('{')
   with mock.patch('tpw.cli.ROOT',isolated),self.assertRaisesRegex(ValueError,'valid JSON'):refresh_seasonality('2026-08',force=True)
  workflow=(ROOT/'.github/workflows/daily-update.yml').read_text();dispatch=workflow.split('concurrency:',1)[0]
  self.assertIn('force_seasonality_refresh:',dispatch);self.assertRegex(dispatch,r'force_seasonality_refresh:[\s\S]*type: boolean[\s\S]*default: false')
  self.assertIn('refresh-seasonality',workflow);self.assertIn('seasonality_args+=(--force)',workflow);self.assertNotIn('row.get("source_status")=="live"',workflow)
 def test_seasonality_refresh_cli_forwards_force_and_prints_json_result(self):
  result={'action':'refresh','reason':'forced','month':'2026-08','source_status':'live'}
  with mock.patch('tpw.cli.refresh_seasonality',return_value=result) as refresh,mock.patch('sys.stdout',new_callable=io.StringIO) as output:
   main(['refresh-seasonality','--month','2026-08','--force'])
  refresh.assert_called_once_with('2026-08',True);self.assertIn(json.dumps(result,ensure_ascii=False,sort_keys=True),output.getvalue())
 def test_two_date_history_survives(self):
  first=json.loads((ROOT/'tests/fixtures/market_success.json').read_text()); ingest(first,'2026-08-25','2026-08-25'); self.command('build','--as-of','2026-08-25')
  second=[dict(r,交易日期='115.08.24') for r in first]; ingest(second,'2026-08-24','2026-08-24'); self.command('build','--as-of','2026-08-24')
  for day in ('2026-08-24','2026-08-25'):
   self.assertTrue((ROOT/'site/daily/2026/08'/(day+'.html')).exists()); self.assertTrue((ROOT/'reports/daily/2026/08'/(day+'.md')).exists())
  archive=(ROOT/'site/archive/index.html').read_text(); self.assertIn('2026-08-24',archive); self.assertIn('2026-08-25',archive)
 def test_multi_tree_swap_rolls_back(self):
  with tempfile.TemporaryDirectory() as raw:
   base=pathlib.Path(raw); pairs=[]
   for name in ('data','site','reports'):
    dest=base/name; dest.mkdir(); (dest/'v').write_text('old'); stage=base/(name+'-stage'); stage.mkdir(); (stage/'v').write_text('new'); pairs.append((stage,dest))
   calls=[0]
   def fail(src,dst):
    calls[0]+=1
    if calls[0]==4: raise OSError('injected replace failure')
    __import__('os').replace(src,dst)
   with self.assertRaises(OSError): swap_all(pairs,fail)
   self.assertEqual([(base/n/'v').read_text() for n in ('data','site','reports')],['old','old','old'])
 def test_prototype_routes_context_and_determinism(self):
  self.command('seed-prototype','--as-of','2026-08-25');catalog_path=ROOT/'data/seasonality/catalog/2026-08.json';catalog_before=catalog_path.read_bytes();self.command('build','--as-of','2026-08-25');self.assertEqual(catalog_before,catalog_path.read_bytes())
  tracked=[ROOT/'site/index.html',ROOT/'site/season/current.html',ROOT/'site/assets/js/app.js',ROOT/'site/assets/css/app.css',ROOT/'site/assets/icons/produce.svg',ROOT/'site/data/current.json',ROOT/'data/advice/2026/08/2026-08-25.json']
  before=[hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked];self.command('build','--as-of','2026-08-25');self.assertEqual(before,[hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked])
  current=json.loads((ROOT/'site/data/current.json').read_text());self.assertTrue(current['prototype_complete']);self.assertGreaterEqual(current['eligible_recommendations'],3);self.assertEqual(len(current['scores']),20);self.assertEqual(current['advice']['generation_mode'],'deterministic_fallback')
  self.assertEqual(len(list((ROOT/'site/produce').glob('*.html'))),20);self.assertEqual(len(list((ROOT/'site/traceability').glob('*.html'))),22)
  for route in ('season/current.html','trends/daily.html','trends/weekly.html','trends/monthly.html','trends/quarterly.html','traceability/index.html','traceability/market-events.html'):
   self.assertTrue((ROOT/'site'/route).exists(),route)
  event_date=current['traceability_event_status']['requested_date'];event_path=ROOT/'data/traceability/market-events/daily'/event_date[:4]/event_date[5:7]/(event_date+'.json')
  self.assertEqual(len(list((ROOT/'data/series').glob('*.json'))),20);self.assertTrue((ROOT/'data/seasonality/2026-08.json').exists());self.assertTrue((ROOT/'data/traceability/monthly/2026-08.json').exists());self.assertTrue(event_path.exists())
  season=(ROOT/'site/season/current.html').read_text();self.assertEqual(season.count("class='card season-card'"),len(current['season_catalog']));self.assertEqual(season.count('data-search-name='),len(current['season_catalog']));self.assertIn("data-season-source='live'",season)
  card_tags=re.findall(r"<article class='card season-card'[^>]*>",season);search_names=[html.unescape(value) for value in re.findall(r"data-search-name='([^']*)'",season)]
  self.assertEqual(Counter(search_names),Counter(row['display_name'] for row in current['season_catalog']));self.assertTrue(all(' hidden' not in tag for tag in card_tags))
  for token in ("data-filter='all'","data-filter='fruit'","data-filter='vegetable'","type='search'",'data-season-search','data-season-result-count',"role='status'","aria-live='polite'","aria-atomic='true'",'data-season-empty','有行情資料','無行情資料','有相關履歷'):self.assertIn(token,season)
  for token in ('data-season-search','data-season-result-count','data-season-empty'):self.assertEqual(season.count(token),1)
  self.assertIn('data-season-empty hidden',season)
  self.assertNotIn('data-season-search',(ROOT/'site/index.html').read_text())
  from tpw.produce_icons import read_produce_icon_sprite, resolve_produce_icon, uncovered_display_names
  self.assertEqual((ROOT/'site/assets/icons/produce.svg').read_bytes(),read_produce_icon_sprite())
  self.assertEqual(season.count("class='produce-icon "),len(current['season_catalog']));self.assertEqual(season.count("aria-hidden='true' focusable='false'"),len(current['season_catalog']));self.assertEqual(season.count("<use href='../assets/icons/produce.svg#"),len(current['season_catalog']))
  expected_fidelity=Counter(resolve_produce_icon(row['category'],row['display_name']).fidelity for row in current['season_catalog'])
  for fidelity,count in expected_fidelity.items():self.assertEqual(season.count("data-icon-fidelity='"+fidelity+"'"),count)
  for row in current['season_catalog']:
   spec=resolve_produce_icon(row['category'],row['display_name']);self.assertIn("href='../assets/icons/produce.svg#"+spec.symbol_id+"'",season);self.assertNotIn('icon',row)
  self.assertEqual(uncovered_display_names(current['season_catalog']),[])
  from tpw.cli import css, js, market_status_css
  script=(ROOT/'site/assets/js/app.js').read_text();self.assertEqual(script,js());self.assertEqual((ROOT/'site/assets/css/app.css').read_text(),css()+market_status_css())
  for token in ("normalize('NFKC')",'dataset.searchName','const applyFilters','textContent','URLSearchParams','replaceState','pushState','popstate'):self.assertIn(token,script)
  for token in ('fetch(','XMLHttpRequest','localStorage','sessionStorage'):self.assertNotIn(token,script)
  trace=(ROOT/'data/traceability/current.json').read_text();self.assertNotIn('不得保存的姓名',trace);self.assertNotIn('不得保存的通路明細',trace)
  self.assertTrue(current['traceability_events']);self.assertTrue(all(row['record_type']=='traceability_market_event' and row['eligible_for_market_aggregate'] is False and row['affects_buy_score'] is False for row in current['traceability_events']))
  self.assertIs(current['traceability_event_status']['eligible_for_market_aggregate'],False);self.assertIs(current['traceability_event_status']['affects_buy_score'],False)
  event_page=(ROOT/'site/traceability/market-events.html').read_text();self.assertIn("data-traceability-event-source='fixture'",event_page);self.assertIn('不納入行情彙總或 Buy Score',event_page);self.assertIn('H44',event_page);self.assertIn('溯源代號',event_page)
  self.assertNotIn('PR 1 不產生推薦',(ROOT/'reports/daily/2026/08/2026-08-25.md').read_text())
 def test_season_map_payload_is_published_and_deterministic(self):
  self.command('seed-prototype','--as-of','2026-08-25');self.command('validate-config');self.command('build','--as-of','2026-08-25')
  payload_path=ROOT/'site/data/season-map/current.json';page_path=ROOT/'site/season/map.html'
  self.assertTrue(payload_path.exists());self.assertTrue(page_path.exists())
  first=payload_path.read_bytes();payload=json.loads(first);current=json.loads((ROOT/'site/data/current.json').read_text())
  self.assertEqual(payload['schema_version'],'1.1');self.assertEqual(payload['as_of_month'],current['publication_status']['requested_date'][:7]);self.assertEqual(payload['resolved_market_date'],'2026-08-25')
  self.assertEqual(len(payload['counties']),22);self.assertNotIn('season_map',current)
  self.assertNotIn('seasonality_source_status',payload['inputs'])
  self.assertEqual(
   [(row['id'],row['season_semantics'],row['catalog_row_count']) for row in payload['categories']],
   [('fruit','official_season_registry',20),('vegetable','official_season_registry',19),('livestock','no_official_season_registry',0),('aquaculture','no_official_season_registry',0)],
  )
  self.assertEqual(payload['inputs']['seasonality_sources'],{'fruit':{'source_status':'live'},'vegetable':{'source_status':'live'}})
  taipei=next(county for county in payload['counties'] if county['slug']=='taipei-city')
  self.assertEqual([(market['market_code'],market['feed_market_name']) for market in taipei['official_markets']],[('104','臺北二'),('109','臺北一')])
  tampered=json.loads(first);county=next(row for row in tampered['counties'] if row['local_seasonal_produce']);county['local_seasonal_produce'][0]['canonical_id']='tampered-canonical-id';payload_path.write_text(json.dumps(tampered,ensure_ascii=False,separators=(',',':')))
  with self.assertRaises(subprocess.CalledProcessError) as raised:self.command('verify-site','--as-of','2026-08-25')
  self.assertIn('does not match the public seasonality catalog',raised.exception.stderr)
  payload_path.write_bytes(first)
  self.command('validate-data','--as-of','2026-08-25');self.command('verify-site','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25')
  self.assertEqual(first,payload_path.read_bytes())
 def test_site_guard_rejects_secret_and_oversize(self):
  from tpw.render import build_site
  rows=[{'canonical_id':'banana','display_name':'香蕉','category':'fruit','weighted_avg_price_twd_per_kg':None,'total_volume_kg':0}]
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw); build_site(rows,'2026-08-25',root)
   index=root/'index.html'; index.write_text(index.read_text()+'ghp_example')
   with self.assertRaises(ValueError): verify_site(root)
   build_site(rows,'2026-08-25',root); large=root/'large.bin'
   with large.open('wb') as handle: handle.truncate(901*1024*1024)
   with self.assertRaises(ValueError): verify_site(root)
 def test_site_guard_rejects_unsafe_or_missing_svg_references(self):
  from tpw.render import build_site
  from tpw.produce_icons import read_produce_icon_sprite
  rows=[{'canonical_id':'banana','display_name':'香蕉','category':'fruit','weighted_avg_price_twd_per_kg':None,'total_volume_kg':0}]
  references=('https://example.invalid/icons.svg#produce-fruit-banana','HtTpS://example.invalid/icons.svg#produce-fruit-banana','file:assets/icons/produce.svg#produce-fruit-banana','javascript:alert(1)#produce-fruit-banana',' data.svg#produce-fruit-banana',r'assets\icons\produce.svg#produce-fruit-banana','assets/%70roduce.svg#produce-fruit-banana','assets/icons/produce.svg?cache=1#produce-fruit-banana','assets/icons/produce.svg#missing','missing.svg#produce-fruit-banana','#produce-fruit-banana','../outside.svg#produce-fruit-banana')
  with tempfile.TemporaryDirectory() as raw:
   base=pathlib.Path(raw);root=base/'site';(base/'outside.svg').write_bytes(read_produce_icon_sprite())
   for reference in references:
    with self.subTest(reference=reference):
     build_site(rows,'2026-08-25',root);index=root/'index.html';index.write_text(index.read_text().replace('</body>',"<svg><use href='"+reference+"'></use></svg></body>"))
     with self.assertRaises(ValueError):verify_site(root)
   build_site(rows,'2026-08-25',root);sprite=root/'assets/icons/produce.svg';sprite.write_bytes(sprite.read_bytes().replace(b'</svg>',b'<!-- ghp_example -->\n</svg>'))
   with self.assertRaises(ValueError):verify_site(root)
 def test_no_extension_file_build_exposes_categories_axis_and_semantics_sections(self):
  # Scenario (a): the ordinary, no-extension-file build. Issue #44 Part B, work order section 8 WP-2.
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25')
  payload=json.loads((ROOT/'site/data/season-map/current.json').read_text())
  self.assertEqual(payload['schema_version'],'1.1')
  self.assertEqual(
   [(row['id'],row['season_semantics'],row['catalog_row_count']) for row in payload['categories']],
   [('fruit','official_season_registry',20),('vegetable','official_season_registry',19),('livestock','no_official_season_registry',0),('aquaculture','no_official_season_registry',0)],
  )
  season_html=(ROOT/'site/season/current.html').read_text()
  self.assertEqual(season_html.count("data-filter='"),3)
  self.assertIn("id='season-semantics' data-season-semantics",season_html)
  self.assertIn('畜產',season_html);self.assertIn('養殖水產',season_html)
  map_html=(ROOT/'site/season/map.html').read_text()
  self.assertEqual(map_html.count('data-season-semantics-unknown'),22)
  self.assertIn('data-season-semantics-notice',map_html)
  self.command('verify-site','--as-of','2026-08-25');self.command('validate-data','--as-of','2026-08-25')
  first=hashlib.sha256((ROOT/'site/index.html').read_bytes()).hexdigest();self.command('build','--as-of','2026-08-25')
  self.assertEqual(first,hashlib.sha256((ROOT/'site/index.html').read_bytes()).hexdigest())
 def test_category_label_change_is_reflected_in_the_rendered_season_page(self):
  # Guard test (supervisor B-1): render.py must thread the loaded registry through, not fall
  # back to a package-location-bound default -- a label edit in this copy's own
  # config/produce-categories.json must reach the rendered page built from this same copy.
  categories_path=ROOT/'config/produce-categories.json';payload=json.loads(categories_path.read_text())
  fruit=next(entry for entry in payload['categories'] if entry['id']=='fruit');fruit['label']='測試水果'
  categories_path.write_text(json.dumps(payload,ensure_ascii=False))
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25')
  season_html=(ROOT/'site/season/current.html').read_text()
  # The fixed filter button text ("水果") is a SPEC section 11.7 pin and correctly stays as-is;
  # only the per-card category label is registry-driven, so check that element specifically.
  self.assertIn("<div class='label'>測試水果</div>",season_html)
  self.assertNotIn("<div class='label'>水果</div>",season_html)
  self.assertIn("data-filter='fruit' aria-pressed='false'>水果</button>",season_html)
  self.command('verify-site','--as-of','2026-08-25')
 def test_extension_slot_with_a_test_only_category_builds_and_verifies(self):
  # Scenario (b): a test-only registry category plus its extension file (supervisor B-2). Never
  # committed -- config/produce-categories.json and the sprite are edited only in this copy.
  categories_path=ROOT/'config/produce-categories.json';payload=json.loads(categories_path.read_text())
  payload['categories'].append({
   'id':'test_fishery','label':'測試漁產','season_semantics':'official_season_registry',
   'season_source':{'source_id':'test_fishery_source','source_url':'https://example.test/season','allowed_hosts':['example.test']},
   'market_watchlist':False,'buy_score_eligible':False,
   'icon_fallback_symbol':'produce-test_fishery-fallback','note':'測試用',
  })
  categories_path.write_text(json.dumps(payload,ensure_ascii=False))
  sprite_path=ROOT/'src/tpw/assets/produce-icons.svg';sprite=sprite_path.read_text(encoding='utf-8')
  symbol=("  <symbol id='produce-test_fishery-fallback' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'>"
          "<circle cx='12' cy='12' r='8'/></symbol>\n")
  sprite_path.write_text(sprite.replace('</svg>',symbol+'</svg>'),encoding='utf-8')
  self.command('seed-prototype','--as-of','2026-08-25')
  self.command_from_temp_src('validate-config')
  extension_path=ROOT/'data/seasonality/extensions/2026-08.json';extension_path.parent.mkdir(parents=True,exist_ok=True)
  extension_row={
   'schema_version':'1.0','month':'2026-08','canonical_id':None,'display_name':'測試魚甲',
   'source_display_names':['測試魚甲'],'category':'test_fishery','counties':['屏東縣'],
   'county_count':1,'district_count':1,'varieties':[],'variety_count':0,
   'source_url':'https://example.test/season','source_status':'stale','fetched_at':'fixture',
   'source_id':'test_fishery_source',
  }
  extension_path.write_text(json.dumps([extension_row],ensure_ascii=False))
  self.command_from_temp_src('build','--as-of','2026-08-25')
  payload=json.loads((ROOT/'site/data/season-map/current.json').read_text())
  test_fishery_row=next(row for row in payload['categories'] if row['id']=='test_fishery')
  self.assertEqual(test_fishery_row['catalog_row_count'],1)
  self.assertEqual(payload['inputs']['seasonality_sources']['test_fishery'],{'source_status':'stale'})
  self.assertEqual(payload['inputs']['seasonality_sources']['fruit'],{'source_status':'live'})
  pingtung=next(county for county in payload['counties'] if county['slug']=='pingtung-county')
  self.assertIn('test_fishery',{row['category'] for row in pingtung['local_seasonal_produce']})
  season_html=(ROOT/'site/season/current.html').read_text()
  self.assertIn("data-filter='test_fishery'",season_html);self.assertIn('測試漁產',season_html)
  self.assertIn('produce-test_fishery-fallback',season_html)
  self.command_from_temp_src('verify-site','--as-of','2026-08-25')
  self.command_from_temp_src('validate-data','--as-of','2026-08-25')
 def test_livestock_extension_rows_fail_closed_and_preserve_last_known_good(self):
  # Scenario (c): SPEC section 6.2.6 / Issue #44 BC-2 -- a no_official_season_registry category
  # must never be populated from an extension file; a bad extension file must not corrupt the
  # already-published data/site/reports.
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25')
  data_before=hashlib.sha256((ROOT/'data/seasonality/catalog/2026-08.json').read_bytes()).hexdigest()
  site_before=hashlib.sha256((ROOT/'site/index.html').read_bytes()).hexdigest()
  reports_before=hashlib.sha256((ROOT/'reports/daily/2026/08/2026-08-25.md').read_bytes()).hexdigest()
  extension_path=ROOT/'data/seasonality/extensions/2026-08.json';extension_path.parent.mkdir(parents=True,exist_ok=True)
  bad_row={
   'schema_version':'1.0','month':'2026-08','canonical_id':None,'display_name':'毛豬',
   'source_display_names':['毛豬'],'category':'livestock','counties':['雲林縣'],
   'county_count':1,'district_count':1,'varieties':[],'variety_count':0,
   'source_url':'https://example.test/season','source_status':'live','fetched_at':'fixture',
   'source_id':'whatever',
  }
  extension_path.write_text(json.dumps([bad_row],ensure_ascii=False))
  with self.assertRaises(subprocess.CalledProcessError) as raised:self.command('build','--as-of','2026-08-25')
  self.assertIn('BC-2',raised.exception.stderr)
  self.assertEqual(data_before,hashlib.sha256((ROOT/'data/seasonality/catalog/2026-08.json').read_bytes()).hexdigest())
  self.assertEqual(site_before,hashlib.sha256((ROOT/'site/index.html').read_bytes()).hexdigest())
  self.assertEqual(reports_before,hashlib.sha256((ROOT/'reports/daily/2026/08/2026-08-25.md').read_bytes()).hexdigest())
 def test_verify_site_rejects_unregistered_category_and_stale_schema_in_published_payload(self):
  # Scenario (d): a tampered / stale-schema site/data/season-map/current.json must be rejected.
  self.command('seed-prototype','--as-of','2026-08-25');self.command('build','--as-of','2026-08-25')
  payload_path=ROOT/'site/data/season-map/current.json';original=payload_path.read_bytes()
  tampered=json.loads(original);county=next(row for row in tampered['counties'] if row['local_seasonal_produce'])
  county['local_seasonal_produce'][0]['category']='grain'
  payload_path.write_text(json.dumps(tampered,ensure_ascii=False,separators=(',',':')))
  with self.assertRaises(subprocess.CalledProcessError) as raised:self.command('verify-site','--as-of','2026-08-25')
  self.assertIn('unregistered',raised.exception.stderr)
  payload_path.write_bytes(original)
  old=json.loads(original);old['schema_version']='1.0';old['inputs']=dict(old['inputs'])
  old['inputs']['seasonality_source_status']='live';del old['inputs']['seasonality_sources'];del old['categories']
  payload_path.write_text(json.dumps(old,ensure_ascii=False,separators=(',',':')))
  with self.assertRaises(subprocess.CalledProcessError) as raised:self.command('verify-site','--as-of','2026-08-25')
  # An old schema_version 1.0 shape is missing 1.1's categories/inputs.seasonality_sources
  # fields entirely, so this rejects at the top-level field-set check before schema_version is
  # ever compared -- itself proof that an old payload cannot slip past verify-site.
  self.assertIn('SeasonMapContractError',raised.exception.stderr)
  self.assertIn('fields do not match the contract',raised.exception.stderr)
  payload_path.write_bytes(original)
