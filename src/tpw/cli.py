import argparse,datetime as dt,hashlib,json,os,pathlib,shutil,tempfile
from html.parser import HTMLParser
from .model import canonical_map,normalize,upsert
from .market import fetch
from .analytics import aggregate
from .render import build_site,render_report,DISCLAIM
from .prototype import generate_market_rows
from .analytics import build_series
from .seasonality import load_manual
from .scoring import score_all
from .advice import generate_advice
from .traceability import filter_traceability
from .publication import classify_market_status,load_resolved_market_status,source_unavailable_status,validate_market_status
ROOT=pathlib.Path.cwd(); SECRET=('AKIA','ghp_','glpat-','github_pat_','sk-','-----BEGIN PRIVATE KEY-----','bearer ','base64,')
def config(): return json.loads((ROOT/'config/produce.yml').read_text())['items']
def write_json(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf-8')
def path_for(base,date): return base/'market/daily'/date[:4]/date[5:7]/(date+'.json')
def roc(iso): d=dt.date.fromisoformat(iso);return '%03d.%02d.%02d'%(d.year-1911,d.month,d.day)
def swap(stage,dest):
 backup=dest.with_name(dest.name+'.backup');shutil.rmtree(backup,ignore_errors=True)
 if dest.exists(): os.replace(dest,backup)
 try: os.replace(stage,dest)
 except Exception:
  if backup.exists():os.replace(backup,dest)
  raise
 shutil.rmtree(backup,ignore_errors=True)
def swap_all(pairs, replace=os.replace):
 backups=[]
 try:
  for stage,dest in pairs:
   backup=dest.with_name(dest.name+'.backup');shutil.rmtree(backup,ignore_errors=True)
   if dest.exists():replace(dest,backup)
   backups.append((dest,backup));replace(stage,dest)
 except Exception:
  for dest,backup in reversed(backups):
   if dest.exists():shutil.rmtree(dest)
   if backup.exists():replace(backup,dest)
  raise
 else:
  for _,backup in backups:shutil.rmtree(backup,ignore_errors=True)
def ingest(raw,start,end,fetched_at='fixture'):
 if not raw:raise ValueError('no upstream rows')
 configured=config();mapping=canonical_map(configured);lo,hi=dt.date.fromisoformat(start),dt.date.fromisoformat(end)
 observed=[normalize(r,mapping,fetched_at) for r in raw]
 if any(not lo<=dt.date.fromisoformat(r['transaction_date'])<=hi for r in observed):raise ValueError('upstream record outside requested date range')
 rows=[r for r in observed if r['canonical_id']]
 stage=pathlib.Path(tempfile.mkdtemp(prefix='tpw-ingest-',dir=ROOT));sd=stage/'data'
 try:
  if (ROOT/'data').exists():shutil.copytree(ROOT/'data',sd)
  for date in sorted({r['transaction_date'] for r in rows}):
   p=path_for(sd,date); old=json.loads(p.read_text()) if p.exists() else [];write_json(p,upsert(old+[r for r in rows if r['transaction_date']==date]))
  end_path=path_for(sd,end);stored=json.loads(end_path.read_text()) if end_path.exists() else []
  source_status='fixture' if fetched_at=='fixture' else 'success'
  market_status=classify_market_status(observed,stored,end,{item['canonical_id'] for item in configured},source_status)
  write_json(sd/'market-status/current.json',market_status)
  meta_path=sd/'source-meta'/(end+'.json'); meta={'source_id':'moa_market_8066','source_url':'https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx','requested_start':start,'requested_end':end,'fetched_at':fetched_at,'http_status':200,'record_count':len(rows),'raw_record_count':len(raw),'content_hash':'sha256:'+hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'adapter_version':'1.0','status':source_status}
  if meta_path.exists():
   previous=json.loads(meta_path.read_text())
   if all(previous.get(key)==meta[key] for key in ('requested_start','requested_end','content_hash','adapter_version','status')):meta=previous
  write_json(meta_path,meta)
  swap(sd,ROOT/'data')
 finally:shutil.rmtree(stage,ignore_errors=True)
 return len(rows)
def fetch_market(start,end,opener=None):
 raw=fetch(roc(start),roc(end),opener=opener) if opener else fetch(roc(start),roc(end));return ingest(raw,start,end,dt.datetime.now(dt.UTC).isoformat())
def backfill(days,end,fetcher=fetch_market):
 if days<1:raise ValueError('days must be positive')
 finish=dt.date.fromisoformat(end);cursor=finish-dt.timedelta(days=days-1);out=[]
 while cursor<=finish:
  last=min(cursor+dt.timedelta(days=3),finish);fetcher(cursor.isoformat(),last.isoformat());out.append((cursor.isoformat(),last.isoformat()));cursor=last+dt.timedelta(days=1)
 return out
def record_unavailable_status(requested_date):
 path=ROOT/'data/market-status/current.json'
 if path.exists():
  previous=validate_market_status(json.loads(path.read_text()))
  if previous['requested_date']==requested_date and previous['status'] in ('complete','market_closed'):return previous
 status=source_unavailable_status(requested_date,len(config()))
 write_json(path,status);return status
def load_date(date):
 p=path_for(ROOT/'data',date)
 if not p.exists():raise ValueError('requested as-of normalized data is absent')
 rows=[r for r in json.loads(p.read_text()) if r.get('canonical_id') and r.get('transaction_date')==date]
 if not rows:raise ValueError('requested as-of date has no valid mapped normalized data')
 return rows
def css():
 return """:root{--bg:#f4f7fb;--paper:#fff;--ink:#172033;--muted:#607086;--line:#dfe6ee;--navy:#10243d;--blue:#2d6cdf;--blue-soft:#eaf1ff;--green:#17875d;--green-soft:#e9f7f0;--amber:#ad6b00;--amber-soft:#fff4d8;--red:#bf3d42;--red-soft:#fff0f0;--shadow:0 16px 40px rgba(16,36,61,.09);--radius:18px}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif;overflow-x:hidden}a{color:#1d5dc1;text-underline-offset:3px}a:hover{color:#123e86}a:focus-visible,button:focus-visible{outline:3px solid #7aa9ff;outline-offset:3px}.wrap{width:min(1180px,calc(100% - 32px));margin-inline:auto}.skip{position:fixed;left:-9999px;top:8px;z-index:100;background:#fff;padding:8px 14px;border-radius:8px}.skip:focus{left:12px}.hero{color:#fff;background:linear-gradient(120deg,#10243d,#173c62 62%,#176b7a);box-shadow:var(--shadow)}.hero .wrap{padding-block:26px 22px}.hero h1,.page-hero h1{margin:.05em 0;font-size:clamp(2rem,4vw,3.25rem);line-height:1.05;letter-spacing:-.035em}.hero p{margin:.45rem 0 1rem;color:#dbe9f6;font-size:1.05rem}.eyebrow{font-size:.72rem;font-weight:850;letter-spacing:.16em;text-transform:uppercase;color:#a9d9ef}.eyebrow.ink{color:#2d6cdf}.meta{display:flex;flex-wrap:wrap;gap:7px}.meta span,.badge{display:inline-flex;align-items:center;border-radius:999px;padding:4px 9px;font-size:.76rem;font-weight:750}.meta span{border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.1)}.toolbar{position:sticky;top:0;z-index:20;background:rgba(244,247,251,.94);border-bottom:1px solid rgba(16,36,61,.1);backdrop-filter:blur(12px)}.toolbar .inner{width:min(1180px,calc(100% - 32px));margin:auto;display:flex;align-items:center;gap:7px;padding:8px 0;overflow-x:auto;scrollbar-width:thin}.toolbar a,.toolbar button,.filter-group button,.tabs a{flex:0 0 auto;border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:999px;padding:7px 11px;font:inherit;font-size:.79rem;font-weight:750;text-decoration:none;cursor:pointer}.toolbar a:hover,.toolbar button:hover,.filter-group button:hover,.tabs a:hover,.filter-group button[aria-pressed=true]{border-color:#8fb0e8;background:var(--blue-soft);color:#174c9b}main.wrap{padding-block:16px 42px}.section{margin:0 0 18px;padding:22px;background:var(--paper);border:1px solid rgba(16,36,61,.08);border-radius:var(--radius);box-shadow:var(--shadow)}.recommendations{scroll-margin-top:70px}.section h2{margin:.05em 0 .35em;font-size:clamp(1.35rem,2.4vw,1.9rem);line-height:1.2}.section h3{margin:.15em 0}.section-heading,.card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.lead{font-size:1.02rem;color:#3d4e63}.small,.sub,.label{color:var(--muted);font-size:.8rem}.label{font-weight:800;letter-spacing:.05em;text-transform:uppercase}.disclaimer{font-weight:750;color:#37475a}.grid,.recommendation-grid{display:grid;gap:14px}.grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3,.recommendation-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.grid-4{grid-template-columns:repeat(4,minmax(0,1fr))}.card,.recommendation-card{min-width:0;padding:16px;border:1px solid var(--line);border-radius:15px;background:linear-gradient(180deg,#fff,#fbfcff)}.recommendation-card{position:relative;overflow:hidden;border-top:4px solid var(--green)}.recommendation-card.neutral{border-top-color:var(--amber)}.recommendation-card.negative{border-top-color:var(--red)}.score{display:grid;place-items:center;min-width:48px;height:48px;border-radius:14px;background:var(--green-soft);color:var(--green);font-size:1.35rem;font-weight:900}.card-price,.value{font-size:1.32rem;font-weight:850;letter-spacing:-.02em}.verdict-label{margin:.1rem 0;color:var(--green);font-weight:850}.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:12px 0}.metrics div{padding:8px;border-radius:10px;background:#f6f8fb}.metrics dt{color:var(--muted);font-size:.72rem}.metrics dd{margin:0;font-weight:800}.reasons{display:flex;flex-wrap:wrap;gap:5px}.reason{padding:3px 7px;border-radius:999px;background:var(--blue-soft);color:#22529c;font-size:.7rem;font-weight:750}.card-link{display:inline-block;margin-top:8px;font-weight:800}.badge.info{background:var(--blue-soft);color:#22529c}.badge.pos{background:var(--green-soft);color:var(--green)}.badge.neg{background:var(--red-soft);color:var(--red)}.badge.neu{background:#eef1f5;color:#506078}.note,.verdict{padding:14px;border-radius:13px;background:var(--blue-soft)}.note.warn{background:var(--amber-soft);color:#704700}.verdict{display:flex;flex-direction:column;gap:5px}.verdict.positive{background:var(--green-soft);color:#116844}.verdict.negative{background:var(--red-soft);color:#8f2c30}.verdict.neutral{background:var(--amber-soft);color:#714900}.filter-group,.tabs{display:flex;flex-wrap:wrap;gap:6px}.mover-list,.archive-list{margin:.5rem 0;padding-left:1.2rem}.mover-list li{display:flex;justify-content:space-between;gap:12px;padding:4px 0}.table-wrap{max-width:100%;overflow-x:auto;border:1px solid var(--line);border-radius:12px}table{width:100%;border-collapse:collapse;background:#fff;min-width:620px}th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}thead th{background:#f6f8fb;color:#44546a;font-size:.78rem}.num{text-align:right;font-variant-numeric:tabular-nums}.chart{height:210px;padding:12px;background:#f8faff;border:1px solid var(--line);border-radius:12px}.chart svg{width:100%;height:100%}.axis{stroke:#c7d2df;stroke-width:2}.price-line{fill:none;stroke:#2d6cdf;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}.page-hero{background:linear-gradient(120deg,#10243d,#173c62 62%,#176b7a);color:#fff}.page-hero .wrap{padding-block:24px}.page-hero p{margin:.4rem 0 0;color:#dbe9f6}.footer{padding:24px;text-align:center;color:var(--muted)}code{padding:.12em .35em;border-radius:5px;background:#eef2f7;overflow-wrap:anywhere}[hidden]{display:none!important}@media(max-width:900px){.grid-4{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3,.recommendation-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.wrap,.toolbar .inner{width:min(100% - 20px,1180px)}.hero .wrap,.page-hero .wrap{padding-block:20px}.hero h1,.page-hero h1{font-size:2rem}.hero p{font-size:.95rem}.section{padding:16px;border-radius:14px}.section-heading{align-items:flex-start;flex-direction:column}.grid-2,.grid-3,.grid-4,.recommendation-grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.toolbar .inner{padding-block:7px}table{min-width:560px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{body{background:#fff}.toolbar,.filter-group,[data-print]{display:none!important}.hero,.page-hero{background:#fff;color:#172033;box-shadow:none}.hero p,.page-hero p{color:#172033}.section{box-shadow:none;break-inside:avoid}.wrap{width:100%}}"""
def market_status_css():
 return """.market-status{padding:12px 0;border-bottom:1px solid var(--line);background:var(--green-soft);color:#116844}.market-status .wrap{display:flex;align-items:baseline;gap:10px}.market-status strong{font-size:.95rem}.market-status span{font-size:.88rem}.market-status--market_closed,.market-status--incomplete,.market-status--pending{background:var(--amber-soft);color:#704700}.market-status--source_unavailable{background:var(--red-soft);color:#8f2c30}@media(max-width:620px){.market-status .wrap{align-items:flex-start;flex-direction:column;gap:2px}}"""
def js():
 return """(()=>{document.querySelectorAll('[data-print]').forEach(button=>button.addEventListener('click',()=>window.print()));const grid=document.querySelector('[data-season-grid]');if(!grid)return;document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{const selected=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));grid.querySelectorAll('[data-category]').forEach(card=>{card.hidden=selected!=='all'&&card.dataset.category!==selected})}))})();"""
def seasonality_rows(month):
 return load_manual(ROOT/'config/seasonality.manual.json',config(),month)
def traceability_rows(month):
 fixture=json.loads((ROOT/'config/traceability.fixture.json').read_text())
 return filter_traceability(fixture.get('items',fixture.get('records',[])),config(),month+'-01T00:00:00Z')
def persist_context(kind,month):
 stage=pathlib.Path(tempfile.mkdtemp(prefix='tpw-context-',dir=ROOT));sd=stage/'data'
 try:
  shutil.copytree(ROOT/'data',sd)
  if kind=='seasonality':
   rows=seasonality_rows(month);write_json(sd/'seasonality'/(month+'.json'),rows)
  else:
   rows=traceability_rows(month);write_json(sd/'traceability/current.json',rows);write_json(sd/'traceability/monthly'/(month+'.json'),rows)
  swap(sd,ROOT/'data');return len(rows)
 finally:shutil.rmtree(stage,ignore_errors=True)
def build(date):
 rows=load_date(date);configured=config();items={i['canonical_id']:i for i in configured}
 all_rows=[]
 for p in sorted((ROOT/'data/market/daily').rglob('*.json')):
  all_rows.extend(json.loads(p.read_text()))
 all_aggs=aggregate(all_rows);aggs=[r for r in all_aggs if r['transaction_date']==date]
 for row in aggs:row.update({'display_name':items[row['canonical_id']]['display_name'],'category':items[row['canonical_id']]['category']})
 if len(aggs)!=len(configured):raise ValueError('requested as-of date does not cover the configured 20-item watchlist')
 stage=pathlib.Path(tempfile.mkdtemp(prefix='tpw-build-',dir=ROOT))
 try:
  ds=stage/'data';shutil.copytree(ROOT/'data',ds)
  write_json(ds/'aggregates/daily'/date[:4]/date[5:7]/(date+'.json'),aggs)
  meta=ROOT/'data/source-meta'/(date+'.json');status=json.loads(meta.read_text()).get('status','validated') if meta.exists() else 'validated'
  publication=load_resolved_market_status(ROOT/'data',date,status,len(configured));write_json(ds/'market-status/current.json',publication)
  series=build_series(all_aggs,date);season=seasonality_rows(date[:7]);scores=score_all(series,season);advice=generate_advice(scores,date);trace=traceability_rows(date[:7])
  warnings=[]
  if status=='fixture':warnings.append('market data is deterministic prototype fixture')
  warnings.extend(('seasonality uses manual fallback','traceability uses minimized fixture records','advice uses deterministic fallback'))
  quality={'as_of_date':date,'warnings':warnings}
  write_json(ds/'seasonality'/(date[:7]+'.json'),season)
  write_json(ds/'traceability/current.json',trace);write_json(ds/'traceability/monthly'/(date[:7]+'.json'),trace)
  for row in series:write_json(ds/'series'/(row['canonical_id']+'.json'),row)
  write_json(ds/'advice'/date[:4]/date[5:7]/(date+'.json'),advice)
  write_json(ds/'quality'/date[:4]/date[5:7]/(date+'.json'),quality)
  site=stage/'site'
  if (ROOT/'site').exists():shutil.copytree(ROOT/'site',site)
  (site/'assets/css').mkdir(parents=True,exist_ok=True);(site/'assets/js').mkdir(parents=True,exist_ok=True)
  (site/'.nojekyll').write_text('');(site/'assets/css/app.css').write_text(css()+market_status_css(),encoding='utf-8');(site/'assets/js/app.js').write_text(js(),encoding='utf-8')
  build_site(aggs,date,site,status,series=series,scores=scores,seasonality=season,advice=advice,traceability=trace,quality=quality,publication_status=publication)
  reports=stage/'reports'
  if (ROOT/'reports').exists():shutil.copytree(ROOT/'reports',reports)
  rp=reports/'daily'/date[:4]/date[5:7];rp.mkdir(parents=True,exist_ok=True);rp.joinpath(date+'.md').write_text(render_report(aggs,scores,advice,quality,date),encoding='utf-8')
  verify_site(site,date);swap_all([(ds,ROOT/'data'),(site,ROOT/'site'),(reports,ROOT/'reports')])
 finally:shutil.rmtree(stage,ignore_errors=True)
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,t,a):
  if t in ('a','link'):self.links += [v for k,v in a if k=='href']
def verify_site(root=ROOT/'site',date=None):
 files=list(root.rglob('*.html'));assert files,'no generated HTML'; total=0;largest=(0,None)
 index=(root/'index.html')
 if not index.exists() or "id='recommendations'" not in index.read_text():raise ValueError('homepage lacks recommendations section')
 for p in root.rglob('*'):
  if p.is_file():
   size=p.stat().st_size;total+=size
   if size>largest[0]:largest=(size,p)
   if p.suffix.lower() in ('.html','.css','.js','.json','.xml','.txt'):
    text=p.read_text(errors='ignore')
    if any(x.lower() in text.lower() for x in SECRET):raise ValueError('secret/base64 pattern in '+str(p))
 if total>900*1024*1024:raise ValueError('site exceeds 900 MB; largest='+str(largest[1]))
 for p in files:
  text=p.read_text();
  if 'NT$' in text and DISCLAIM not in text:raise ValueError('price page lacks disclaimer: '+str(p))
  parser=Links();parser.feed(text)
  for link in parser.links:
   if link.startswith(('https:','http:','#','mailto:')):continue
   target=(p.parent/link.split('#',1)[0].split('?',1)[0]).resolve()
   if not target.exists() or (root.resolve() not in target.parents and target!=root.resolve()):raise ValueError('broken internal link '+link+' in '+str(p))
 if date:
  current=json.loads((root/'data/current.json').read_text())
  if current['as_of_date']!=date or not current['items']:raise ValueError('empty or mismatched as-of site')
  publication=validate_market_status(current.get('publication_status'))
  if publication.get('resolved_date')!=date:raise ValueError('publication status does not resolve to site as-of date')
  index_text=index.read_text()
  if "data-market-status='"+publication['status']+"'" not in index_text:raise ValueError('homepage market status does not match public JSON')
  if publication['requested_date'] not in index_text:raise ValueError('homepage omits latest market check date')
  if current.get('prototype_complete'):
   required=('season/current.html','trends/daily.html','trends/weekly.html','trends/monthly.html','trends/quarterly.html','traceability/index.html','archive/index.html','methodology.html')
   missing=[path for path in required if not (root/path).exists()]
   ids={row['canonical_id'] for row in current.get('scores',[])}
   missing.extend('produce/'+item+'.html' for item in ids if not (root/'produce'/(item+'.html')).exists())
   missing.extend('traceability/'+item+'.html' for item in ids if not (root/'traceability'/(item+'.html')).exists())
   if missing:raise ValueError('prototype routes missing: '+', '.join(sorted(missing)))
   if len(ids)!=20:raise ValueError('prototype must render the configured 20-item watchlist')
   if current.get('source_status')=='fixture':
    if current.get('eligible_recommendations',0)<3:raise ValueError('fixture must produce at least three eligible recommendations')
    if index.read_text().count("class='recommendation-card")<3:raise ValueError('first prototype surface lacks three recommendation cards')
   if current.get('generation_mode') not in ('deterministic_fallback','ai'):raise ValueError('advice generation mode missing')
def validate_data(date):
 load_date(date)
 required=(ROOT/'data/aggregates/daily'/date[:4]/date[5:7]/(date+'.json'),ROOT/'data/seasonality'/(date[:7]+'.json'),ROOT/'data/traceability/current.json',ROOT/'data/advice'/date[:4]/date[5:7]/(date+'.json'),ROOT/'data/quality'/date[:4]/date[5:7]/(date+'.json'),ROOT/'data/market-status/current.json')
 missing=[str(path.relative_to(ROOT)) for path in required if not path.exists()]
 if missing:raise ValueError('derived data missing: '+', '.join(missing))
 if len(list((ROOT/'data/series').glob('*.json')))!=20:raise ValueError('series data must cover 20 configured items')
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True);s.add_parser('validate-config')
 seed=s.add_parser('seed-prototype');seed.add_argument('--as-of',required=True)
 f=s.add_parser('fetch-market');f.add_argument('--start',required=True);f.add_argument('--end',required=True)
 fs=s.add_parser('fetch-seasonality');fs.add_argument('--month',default=dt.date.today().strftime('%Y-%m'))
 ft=s.add_parser('fetch-traceability');ft.add_argument('--month',default=dt.date.today().strftime('%Y-%m'))
 b=s.add_parser('build');b.add_argument('--as-of',required=True)
 bf=s.add_parser('backfill');bf.add_argument('--days',type=int,default=120);bf.add_argument('--end',default=dt.date.today().isoformat())
 d=s.add_parser('validate-data');d.add_argument('--as-of',required=True)
 ms=s.add_parser('record-market-status');ms.add_argument('--requested-date',required=True);ms.add_argument('--status',choices=('source_unavailable',),required=True)
 v=s.add_parser('verify-site');v.add_argument('--as-of');a=p.parse_args(argv)
 if a.cmd=='validate-config':
  items=config();canonical_map(items);assert sum(x['category']=='fruit' and x.get('enabled') for x in items)>=10 and sum(x['category']=='vegetable' and x.get('enabled') for x in items)>=10;print('config valid: 20 mapped items')
 elif a.cmd=='seed-prototype':
  fixture=json.loads((ROOT/'config/prototype.fixture.json').read_text());raw=generate_market_rows(config(),fixture,a.as_of);start=(dt.date.fromisoformat(a.as_of)-dt.timedelta(days=int(fixture.get('days',35))-1)).isoformat();print('seeded normalized rows:',ingest(raw,start,a.as_of,'fixture'))
 elif a.cmd=='fetch-market':print('persisted normalized rows:',fetch_market(a.start,a.end))
 elif a.cmd=='fetch-seasonality':print('persisted manual fallback rows:',persist_context('seasonality',a.month))
 elif a.cmd=='fetch-traceability':print('persisted minimized fixture rows:',persist_context('traceability',a.month))
 elif a.cmd=='backfill':print('backfill windows:',backfill(a.days,a.end))
 elif a.cmd=='build':build(a.as_of);print('build promoted safely')
 elif a.cmd=='validate-data':validate_data(a.as_of);print('data valid')
 elif a.cmd=='record-market-status':print('market status:',record_unavailable_status(a.requested_date)['status'])
 else:verify_site(date=a.as_of);print('site verified')
