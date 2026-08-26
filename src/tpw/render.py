import html,json
DISCLAIM="批發市場平均行情，非實際零售通路售價。"
def page(title,body,css="assets/css/app.css"):
 return "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>"+html.escape(title)+"</title><link rel='stylesheet' href='"+css+"'></head><body><a class='skip' href='#main'>跳至主要內容</a><main id='main' class='wrap'>"+body+"</main></body></html>"
def table(rows,kind):
 rs=[r for r in rows if r['category']==kind]
 def render_row(row):
  price='—' if row['weighted_avg_price_twd_per_kg'] is None else 'NT$ %.2f/kg'%row['weighted_avg_price_twd_per_kg']
  return "<tr><th scope='row'>%s</th><td>%s</td><td>%.0f kg</td></tr>"%(html.escape(row['display_name']),price,row['total_volume_kg'])
 body=''.join(render_row(r) for r in rs) or '<tr><td colspan=3>—</td></tr>'
 return "<section><h2>%s行情</h2><p class='disclaimer'>%s</p><table><thead><tr><th>品項</th><th>加權平均價</th><th>交易量</th></tr></thead><tbody>%s</tbody></table></section>"%('水果' if kind=='fruit' else '蔬菜',DISCLAIM,body)
def build_site(rows,as_of,root,source_status='validated'):
 if not rows: raise ValueError('requested as-of date has no valid mapped aggregates')
 nav="<nav aria-label='主要導覽'><a href='methodology.html'>方法說明</a><a href='archive/index.html'>歷史封存</a></nav>"
 hero="<header class='hero'><p>TAIWAN PRODUCE WATCH</p><h1>台灣蔬果批發行情</h1><p>資料日期：%s</p><p>來源：農業部農產品交易行情 Dataset 8066；資料狀態：%s</p></header>"%(html.escape(as_of),html.escape(source_status))
 placeholder="<section id='recommendations'><h2>今日推薦採買</h2><p>PR 1 尚未導入產季與 deterministic Buy Score；因此不產生推薦或分數。</p></section>"
 (root/'index.html').write_text(page('Taiwan Produce Watch',nav+hero+placeholder+table(rows,'fruit')+table(rows,'vegetable')+"<section><h2>方法與限制</h2><p>以 sum(price × volume) / sum(volume) 計算。%s</p></section>"%DISCLAIM),encoding='utf-8')
 d=root/'daily'/as_of[:4]/as_of[5:7];d.mkdir(parents=True,exist_ok=True); (d/(as_of+'.html')).write_text(page('每日行情 '+as_of,"<nav aria-label='主要導覽'><a href='../../../index.html'>首頁</a><a href='../../../methodology.html'>方法說明</a></nav><h1>每日行情 %s</h1>"%as_of+table(rows,'fruit')+table(rows,'vegetable'),'../../../assets/css/app.css'),encoding='utf-8')
 (root/'methodology.html').write_text(page('方法說明',"<nav aria-label='主要導覽'><a href='index.html'>首頁</a></nav><h1>方法說明</h1><p>%s</p><p>全市場價格為 sum(price × volume) / sum(volume)。</p>"%DISCLAIM),encoding='utf-8')
 (root/'archive').mkdir(exist_ok=True); links=''.join("<li><a href='../daily/%s/%s/%s.html'>%s</a></li>"%(p.parent.parent.name,p.parent.name,p.stem,p.stem) for p in sorted((root/'daily').rglob('*.html'))); (root/'archive/index.html').write_text(page('歷史封存',"<nav aria-label='主要導覽'><a href='../index.html'>首頁</a></nav><h1>歷史封存</h1><ul>"+links+'</ul>','../assets/css/app.css'),encoding='utf-8')
 (root/'data').mkdir(exist_ok=True);(root/'data/current.json').write_text(json.dumps({'as_of_date':as_of,'source_status':source_status,'generation_mode':'deterministic','items':rows},ensure_ascii=False,sort_keys=True,separators=(',',':')),encoding='utf-8')
