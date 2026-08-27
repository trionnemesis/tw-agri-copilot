import hashlib, html, json, pathlib, re, shutil, subprocess, sys, tempfile, unittest
from collections import Counter
from unittest import mock
from tpw.cli import ingest, backfill, persist_seasonality, swap_all, verify_site
from tpw.market import UpstreamUnavailable
ROOT=pathlib.Path(__file__).parents[2]
class BuildTest(unittest.TestCase):
 def command(self,*args): subprocess.run([sys.executable,"-m","tpw",*args],cwd=ROOT,check=True,capture_output=True,text=True)
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
  closed=json.loads((ROOT/'tests/fixtures/market_closed.json').read_text())
  with tempfile.TemporaryDirectory() as raw:
   isolated=pathlib.Path(raw);(isolated/'config').mkdir();(isolated/'data').mkdir()
   shutil.copy2(ROOT/'config/produce.yml',isolated/'config/produce.yml')
   with mock.patch('tpw.cli.ROOT',isolated):
    self.assertEqual(ingest(closed,'2026-08-27','2026-08-27','live-check'),0)
   status=json.loads((isolated/'data/market-status/current.json').read_text())
   self.assertEqual(status['status'],'market_closed');self.assertEqual(status['requested_date'],'2026-08-27')
   self.assertFalse((isolated/'data/market/daily/2026/08/2026-08-27.json').exists())
 def test_market_closure_banner_matches_public_json(self):
  from tpw.render import build_site
  rows=[{'canonical_id':'banana','display_name':'香蕉','category':'fruit','weighted_avg_price_twd_per_kg':20,'total_volume_kg':10}]
  status={'schema_version':'1.0','requested_date':'2026-08-27','resolved_date':'2026-08-26','status':'market_closed','source_status':'success','expected_watchlist_count':20,'covered_watchlist_count':0,'observed_record_count':4}
  with tempfile.TemporaryDirectory() as raw:
   root=pathlib.Path(raw);build_site(rows,'2026-08-26',root,publication_status=status)
   html=(root/'index.html').read_text();current=json.loads((root/'data/current.json').read_text())
   self.assertIn('2026-08-27 今日休市',html);self.assertIn('並非網站漏更新',html)
   self.assertEqual(current['publication_status'],status)
 def test_season_search_name_is_html_escaped(self):
  from tpw.render import _season_page
  catalog=[{'canonical_id':None,'display_name':"木瓜' <script>",'category':'fruit','county_count':1,'variety_count':0,'counties':['高雄市']}]
  rendered=_season_page(catalog,[],[])
  self.assertIn("data-search-name='木瓜&#x27; &lt;script&gt;'",rendered);self.assertNotIn('<script>',rendered)
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
  tracked=[ROOT/'site/index.html',ROOT/'site/season/current.html',ROOT/'site/assets/js/app.js',ROOT/'site/assets/css/app.css',ROOT/'site/data/current.json',ROOT/'data/advice/2026/08/2026-08-25.json']
  before=[hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked];self.command('build','--as-of','2026-08-25');self.assertEqual(before,[hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked])
  current=json.loads((ROOT/'site/data/current.json').read_text());self.assertTrue(current['prototype_complete']);self.assertGreaterEqual(current['eligible_recommendations'],3);self.assertEqual(len(current['scores']),20);self.assertEqual(current['advice']['generation_mode'],'deterministic_fallback')
  self.assertEqual(len(list((ROOT/'site/produce').glob('*.html'))),20);self.assertEqual(len(list((ROOT/'site/traceability').glob('*.html'))),21)
  for route in ('season/current.html','trends/daily.html','trends/weekly.html','trends/monthly.html','trends/quarterly.html','traceability/index.html'):
   self.assertTrue((ROOT/'site'/route).exists(),route)
  self.assertEqual(len(list((ROOT/'data/series').glob('*.json'))),20);self.assertTrue((ROOT/'data/seasonality/2026-08.json').exists());self.assertTrue((ROOT/'data/traceability/monthly/2026-08.json').exists())
  season=(ROOT/'site/season/current.html').read_text();self.assertEqual(season.count("class='card season-card'"),len(current['season_catalog']));self.assertEqual(season.count('data-search-name='),len(current['season_catalog']));self.assertIn("data-season-source='live'",season)
  card_tags=re.findall(r"<article class='card season-card'[^>]*>",season);search_names=[html.unescape(value) for value in re.findall(r"data-search-name='([^']*)'",season)]
  self.assertEqual(Counter(search_names),Counter(row['display_name'] for row in current['season_catalog']));self.assertTrue(all(' hidden' not in tag for tag in card_tags))
  for token in ("data-filter='all'","data-filter='fruit'","data-filter='vegetable'","type='search'",'data-season-search','data-season-result-count',"role='status'","aria-live='polite'","aria-atomic='true'",'data-season-empty','有行情資料','無行情資料','有相關履歷'):self.assertIn(token,season)
  for token in ('data-season-search','data-season-result-count','data-season-empty'):self.assertEqual(season.count(token),1)
  self.assertIn('data-season-empty hidden',season)
  self.assertNotIn('data-season-search',(ROOT/'site/index.html').read_text())
  from tpw.cli import css, js, market_status_css
  script=(ROOT/'site/assets/js/app.js').read_text();self.assertEqual(script,js());self.assertEqual((ROOT/'site/assets/css/app.css').read_text(),css()+market_status_css())
  for token in ("normalize('NFKC')",'dataset.searchName','const applyFilters','textContent','URLSearchParams','replaceState','pushState','popstate'):self.assertIn(token,script)
  for token in ('fetch(','XMLHttpRequest','localStorage','sessionStorage'):self.assertNotIn(token,script)
  trace=(ROOT/'data/traceability/current.json').read_text();self.assertNotIn('不得保存的姓名',trace);self.assertNotIn('不得保存的通路明細',trace)
  self.assertNotIn('PR 1 不產生推薦',(ROOT/'reports/daily/2026/08/2026-08-25.md').read_text())
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
