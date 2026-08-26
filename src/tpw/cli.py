import argparse,datetime as dt,hashlib,json,os,pathlib,shutil,tempfile
from html.parser import HTMLParser
from .model import canonical_map,normalize,upsert
from .market import fetch
from .analytics import aggregate
from .render import build_site,DISCLAIM
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
 mapping=canonical_map(config()); lo,hi=dt.date.fromisoformat(start),dt.date.fromisoformat(end);rows=[normalize(r,mapping,fetched_at) for r in raw];rows=[r for r in rows if r['canonical_id']]
 if not rows:raise ValueError('no configured watchlist rows')
 if any(not lo<=dt.date.fromisoformat(r['transaction_date'])<=hi for r in rows):raise ValueError('upstream record outside requested date range')
 stage=pathlib.Path(tempfile.mkdtemp(prefix='tpw-ingest-',dir=ROOT));sd=stage/'data'
 try:
  if (ROOT/'data').exists():shutil.copytree(ROOT/'data',sd)
  for date in sorted({r['transaction_date'] for r in rows}):
   p=path_for(sd,date); old=json.loads(p.read_text()) if p.exists() else [];write_json(p,upsert(old+[r for r in rows if r['transaction_date']==date]))
  meta_path=sd/'source-meta'/(end+'.json'); meta={'source_id':'moa_market_8066','source_url':'https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx','requested_start':start,'requested_end':end,'fetched_at':fetched_at,'http_status':200,'record_count':len(rows),'content_hash':'sha256:'+hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'adapter_version':'1.0','status':'fixture' if fetched_at=='fixture' else 'success'}
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
def load_date(date):
 p=path_for(ROOT/'data',date)
 if not p.exists():raise ValueError('requested as-of normalized data is absent')
 rows=[r for r in json.loads(p.read_text()) if r.get('canonical_id') and r.get('transaction_date')==date]
 if not rows:raise ValueError('requested as-of date has no valid mapped normalized data')
 return rows
def css():return "body{margin:0;background:#f4f7fb;color:#172033;font:16px system-ui}.wrap{max-width:1180px;margin:auto;padding:20px}.hero{padding:28px;background:linear-gradient(130deg,#12263f,#2d6cdf);color:white;border-radius:18px}nav{display:flex;gap:1rem;padding:.5rem 0}a:focus{outline:3px solid #2d6cdf}table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:.6rem;border:1px solid #dfe6ee;text-align:left}.disclaimer{font-weight:700}.skip{position:absolute;left:-999px}.skip:focus{left:1rem;top:1rem}@media(max-width:620px){.wrap{padding:12px}}@media print{.hero{background:white;color:#172033}nav{display:none}}"
def build(date):
 rows=load_date(date); aggs=aggregate(rows);items={i['canonical_id']:i for i in config()}
 for r in aggs:r.update({'display_name':items[r['canonical_id']]['display_name'],'category':items[r['canonical_id']]['category']})
 stage=pathlib.Path(tempfile.mkdtemp(prefix='tpw-build-',dir=ROOT))
 try:
  ds=stage/'data';shutil.copytree(ROOT/'data',ds);write_json(ds/'aggregates/daily'/date[:4]/date[5:7]/(date+'.json'),aggs)
  site=stage/'site';
  if (ROOT/'site').exists():shutil.copytree(ROOT/'site',site)
  meta=ROOT/'data/source-meta'/(date+'.json'); status=json.loads(meta.read_text()).get('status','validated') if meta.exists() else 'validated'
  (site/'assets/css').mkdir(parents=True,exist_ok=True);(site/'.nojekyll').write_text('');(site/'assets/css/app.css').write_text(css());build_site(aggs,date,site,status)
  reports=stage/'reports';
  if (ROOT/'reports').exists():shutil.copytree(ROOT/'reports',reports)
  rp=reports/'daily'/date[:4]/date[5:7];rp.mkdir(parents=True,exist_ok=True);rp.joinpath(date+'.md').write_text('# 每日行情 %s\n\n%s\n\n資料來源：農業部農產品交易行情 Dataset 8066。方法：交易量加權平均。\n\n## 水果\n\n%s\n\n## 蔬菜\n\n%s\n\nPR 1 不產生推薦。\n'%(date,DISCLAIM,'\n'.join('- %s: NT$ %.2f/kg'%(r['display_name'],r['weighted_avg_price_twd_per_kg']) for r in aggs if r['category']=='fruit') or '- —','\n'.join('- %s: NT$ %.2f/kg'%(r['display_name'],r['weighted_avg_price_twd_per_kg']) for r in aggs if r['category']=='vegetable') or '- —'))
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
  if p.is_file():total+=p.stat().st_size;largest=max(largest,(p.stat().st_size,p))
 if total>900*1024*1024:raise ValueError('site exceeds 900 MB; largest='+str(largest[1]))
 for p in files:
  text=p.read_text();
  if any(x.lower() in text.lower() for x in SECRET):raise ValueError('secret/base64 pattern in '+str(p))
  if 'NT$' in text and DISCLAIM not in text:raise ValueError('price page lacks disclaimer: '+str(p))
  parser=Links();parser.feed(text)
  for link in parser.links:
   if link.startswith(('https:','http:','#','mailto:')):continue
   target=(p.parent/link.split('#',1)[0].split('?',1)[0]).resolve()
   if not target.exists() or (root.resolve() not in target.parents and target!=root.resolve()):raise ValueError('broken internal link '+link+' in '+str(p))
 if date:
  current=json.loads((root/'data/current.json').read_text())
  if current['as_of_date']!=date or not current['items']:raise ValueError('empty or mismatched as-of site')
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True);s.add_parser('validate-config');f=s.add_parser('fetch-market');f.add_argument('--start',required=True);f.add_argument('--end',required=True);b=s.add_parser('build');b.add_argument('--as-of',required=True);bf=s.add_parser('backfill');bf.add_argument('--days',type=int,default=120);bf.add_argument('--end',default=dt.date.today().isoformat());d=s.add_parser('validate-data');d.add_argument('--as-of',required=True);v=s.add_parser('verify-site');v.add_argument('--as-of');a=p.parse_args(argv)
 if a.cmd=='validate-config':
  items=config();canonical_map(items);assert sum(x['category']=='fruit' and x.get('enabled') for x in items)>=10 and sum(x['category']=='vegetable' and x.get('enabled') for x in items)>=10;print('config valid: 20 mapped items')
 elif a.cmd=='fetch-market':print('persisted normalized rows:',fetch_market(a.start,a.end))
 elif a.cmd=='backfill':print('backfill windows:',backfill(a.days,a.end))
 elif a.cmd=='build':build(a.as_of);print('build promoted safely')
 elif a.cmd=='validate-data':assert load_date(a.as_of);print('data valid')
 else:verify_site(date=a.as_of);print('site verified')
