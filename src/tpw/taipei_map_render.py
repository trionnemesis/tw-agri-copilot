"""Static Taipei map page and its small, page-specific progressive enhancement."""
from datetime import date
from html import escape
from pathlib import Path
import math
import json
import copy


def e(value):
    return escape(str(value if value is not None else '—'), quote=True)


def number(value, digits=2):
    return '—' if value is None else f'{value:,.{digits}f}'


def _find(rows, code, crop):
    return next((r for r in rows if r.get('market_code') == code and r.get('product_code_raw') == crop), {})


def _day(series, as_of):
    return next((d for d in series.get('days', []) if d.get('date') == as_of), {})


def _chart(doc, crop, window, field, title, unit):
    count = int(window[:-1]); lines = []; vals = []
    for code in ('109', '104'):
        days = _find(doc.get('series', []), code, crop).get('days', [])[-count:]
        lines.append((code, days))
        vals.extend(d[field] for d in days if d.get(field) is not None and d.get('observation_status') == 'observed')
    maximum = max(vals, default=0); ceiling = maximum * 1.1 or 1
    parts = [f"<svg class='chart' viewBox='0 0 720 240' role='img' aria-label='{e(title)}，{e(unit)}'><line x1='55' y1='200' x2='700' y2='200' stroke='#777'/><line x1='55' y1='20' x2='55' y2='200' stroke='#777'/>", f"<text x='4' y='25'>{number(ceiling, 1)}</text><text x='35' y='204'>0</text>"]
    for code, days in lines:
        points = []
        def flush():
            if len(points) > 1:
                parts.append(f"<polyline class='line m{code}' points='{' '.join(points)}'/>")
            points.clear()
        for index, d in enumerate(days):
            v = d.get(field)
            if v is None or d.get('observation_status') != 'observed':
                flush(); continue
            x = 55 + index * 645 / max(count - 1, 1); y = 200 - v / ceiling * 180
            points.append(f'{x:.2f},{y:.2f}')
            parts.append(f"<circle class='dot m{code}' cx='{x:.2f}' cy='{y:.2f}' r='3'><title>{e(code)} {e(d.get('date'))}: {number(v)} {e(unit)}</title></circle>")
        flush()
    dates = [d.get('date') for _, days in lines for d in days]
    if dates: parts.append(f"<text x='55' y='225'>{e(min(dates))}</text><text x='700' y='225' text-anchor='end'>{e(max(dates))}</text>")
    return ''.join(parts) + '</svg>'


def _content(doc, crop='LA2', market='all', window='30d'):
    asof = doc.get('as_of_date'); markets = doc.get('geography', {}).get('markets', [])
    comparison = next((c for c in doc.get('comparisons', []) if c.get('product_code_raw') == crop), {})
    cards = []
    for code, name in (('109', '臺北一'), ('104', '臺北二')):
        s = _find(doc.get('series', []), code, crop); d = _day(s, asof)
        stat = _find(doc.get('statistics', []), code, crop); w = stat.get('windows', {}).get(window, {})
        geo = next((m for m in markets if m.get('market_code') == code), {})
        prev = stat.get('previous_observation', {})
        cards.append(f"<article class='market-card' id='market-{code}' tabindex='-1' data-market='{code}'><h3>{name}（{code}）</h3><p>截至日價格 <strong>{number(d.get('price_twd_per_kg'))} 元/kg</strong> · 成交量 {number(d.get('volume_kg'), 0)} kg</p><p>觀測：{e(d.get('observation_status', '未觀測到此代碼'))}；日曆：{e(d.get('calendar_status', '未知'))}{'；休市成交衝突' if d.get('calendar_conflict') else ''}</p><p>{e(window)} 量加權價 {number(w.get('price_twd_per_kg'))} 元/kg；成交量 {number(w.get('total_volume_kg'), 0)} kg；有效 {e(w.get('coverage_days', 0))}／最低 {e(w.get('minimum_days', '—'))} 日（{e(w.get('status', 'insufficient'))}）</p><p>最新有效觀測 {e(prev.get('latest_date'))}；較前次有效觀測 {e(prev.get('date'))}（間隔 {e(prev.get('interval_days'))} 日）：{number(prev.get('change_pct'))}%</p><p>位置：{e(geo.get('location_status', 'unverified'))} · {e(geo.get('location_role', '位置待確認'))}；核對日 {e(geo.get('verified_at'))}。{e(geo.get('location_note', ''))}</p></article>")
    rows = []
    for code in ('109', '104'):
        for d in _find(doc.get('series', []), code, crop).get('days', [])[-int(window[:-1]):]:
            rows.append(f"<tr><td>{e(d.get('date'))}</td><td>{e(code)}</td><td>{number(d.get('price_twd_per_kg'))}</td><td>{number(d.get('volume_kg'),0)}</td><td>{e(d.get('observation_status'))}</td><td>{e(d.get('calendar_status'))}{'（衝突）' if d.get('calendar_conflict') else ''}</td></tr>")
    gap = f"同日價差（臺北二 − 臺北一）：{number(comparison.get('absolute_gap'))} 元/kg；臺北二相對臺北一 {number(comparison.get('relative_gap_pct'))}%（{e(comparison.get('comparison_status', 'not_comparable'))}）"
    return ("<div class='market-grid'>" + ''.join(cards) + '</div>' + f"<p>{gap}。同作物代碼比較，未控制等級與批次差異。</p>" + f"<section><h2>價格趨勢（元/kg）</h2><p>臺北一：實線　臺北二：虛線；缺資料處斷線。</p>{_chart(doc,crop,window,'price_twd_per_kg','價格趨勢','元/kg')}</section>" + f"<section><h2>成交量趨勢（kg）</h2>{_chart(doc,crop,window,'volume_kg','成交量趨勢','kg')}</section>" + "<section><h2>每日觀測與品質</h2><div class='table-wrap' tabindex='0' aria-label='每日觀測表，可水平捲動'><table><thead><tr><th>日期</th><th>市場</th><th>價格 元/kg</th><th>量 kg</th><th>觀測狀態</th><th>日曆狀態</th></tr></thead><tbody>" + ''.join(rows) + '</tbody></table></div></section>')


def render_taipei_map(doc, svg_text=''):
    failed = doc.get('analysis_status') == 'failed'
    requested, asof = doc.get('requested_date'), doc.get('as_of_date')
    try: lag = (date.fromisoformat(requested) - date.fromisoformat(asof)).days
    except (TypeError, ValueError): lag = '—'
    geo = doc.get('geography') or {}; markets = geo.get('markets', [])
    verified = sum(m.get('location_status') == 'verified' and m.get('display_x') is not None for m in markets)
    options = ''.join(f"<option value='{e(i['canonical_id'])}'{' selected' if i['canonical_id']=='cabbage' else ''}>{e(i['display_name'])}</option>" for i in doc.get('items', []))
    default = next((i for i in doc.get('items', []) if i.get('canonical_id') == 'cabbage'), {})
    crops = ''.join(f"<option value='{e(c['product_code_raw'])}'{' selected' if c['product_code_raw']=='LA2' else ''}>{e(c['product_code_raw'])} · {e(c['product_name_raw'])}</option>" for c in default.get('crops', []))
    map_html = svg_text if not failed else ''
    # SVG is independently validated before entering the renderer. Markers use its exact transform.
    obs = [d for row in doc.get('series', []) if row.get('product_code_raw') == 'LA2' for d in row.get('days', [])[-30:] if d.get('observation_status') == 'observed' and d.get('price_twd_per_kg') is not None and d.get('volume_kg') is not None]
    prices = [d['price_twd_per_kg'] for d in obs]; volumes = [d['volume_kg'] for d in obs]
    def marker_attrs(m):
        d = _day(_find(doc.get('series', []), m['market_code'], 'LA2'), asof)
        price, volume = d.get('price_twd_per_kg'), d.get('volume_kg')
        if d.get('observation_status') != 'observed' or price is None or volume is None or not volumes or max(volumes) <= 0:
            return "r='7' fill='white' data-available='false'"
        ratio = (price - min(prices)) / (max(prices) - min(prices)) if max(prices) != min(prices) else .5
        red = round(51 + ratio * 155); green = round(133 - ratio * 70)
        return f"r='{25 * math.sqrt(volume / max(volumes)):.3f}' fill='rgb({red},{green},75)' data-available='true' data-volume='{volume}' data-price='{price}'"
    markers = ''.join(f"<a class='map-marker' data-code='{e(m['market_code'])}' href='#market-{e(m['market_code'])}' aria-label='{e(m.get('official_name'))}（{e(m['market_code'])}）'><circle class='data-circle' cx='{m['display_x']}' cy='{m['display_y']}' {marker_attrs(m)}/><circle class='hit' cx='{m['display_x']}' cy='{m['display_y']}' r='20'/><text x='{m['display_x']}' y='{float(m['display_y'])-24}'>{e(m.get('official_name'))}</text></a>" for m in markets if m.get('location_status') == 'verified' and m.get('display_x') is not None and m.get('display_y') is not None)
    labels = [('北投區',274.3,199.9),('士林區',325.3,253.6),('內湖區',474.8,405.5),('中山區',349,405),('大同區',268.2,462.4),('松山區',391.7,474.7),('南港區',561,538.7),('中正區',287.9,567.1),('信義區',427.5,567.3),('萬華區',227.1,566.5),('大安區',350.5,575),('文山區',435.8,687.9)]
    labels_svg = ''.join(f"<text class='district-label' x='{x}' y='{y}'>{name}</text>" for name,x,y in labels)
    if '</svg>' in map_html: map_html = map_html.replace('</svg>', labels_svg + markers + '</svg>')
    comparisons = ''.join(f"<tr><td>{e(c.get('canonical_id'))}</td><td>{e(c.get('product_code_raw'))}</td><td>{number(c.get('price_109'))}</td><td>{number(c.get('price_104'))}</td><td>{number(c.get('volume_109'),0)}</td><td>{number(c.get('volume_104'),0)}</td><td>{number(c.get('absolute_gap'))}</td><td>{number(c.get('relative_gap_pct'))}</td><td>{e(c.get('comparison_status'))}</td></tr>" for c in doc.get('comparisons', []))
    status = f"資料截至 {e(asof)}；更新請求日 {e(requested)}；落後 {e(lag)} 日。發布狀態：{e(doc.get('publication_status'))}；分析狀態：{e(doc.get('analysis_status'))}。已驗證點位 {verified}／2。"
    if doc.get('publication_status') == 'source_unavailable': status += f' {e(requested)} 更新來源不可用。'
    if doc.get('data_mode') == 'fixture': status += ' 合成測試資料。'
    body = f"<header class='page-hero'><div class='wrap'><div class='eyebrow'>TAIPEI CITY · WHOLESALE</div><h1>臺北批發行情地圖</h1><p>目前收錄的兩個果菜批發市場與觀察清單</p></div></header><nav class='wrap'><a href='../index.html'>首頁</a> · <a href='index.html'>臺北描述統計</a></nav><main id='main' class='wrap'><section class='section'><h2>資料狀態</h2><p class='note warn' id='map-status'>{status}</p><p>批發市場行情供歷史與市場觀測參考，非零售報價。地圖表示市場所在地，非農產品產地；行政區底圖不代表各區價格。不同批次與等級仍會影響價格。</p></section>"
    if failed:
        body += f"<section class='section'><h2>地圖分析無法使用</h2><p>{e(doc.get('failure_reason'))}</p></section>"
    else:
        body += f"<section class='section'><h2>選擇觀測口徑</h2><p id='control-status' aria-live='polite'>互動控制載入前停用；下方為預設甘藍 LA2、30 日。</p><div class='controls'><label>品項<select id='item' disabled>{options}</select></label><label>原始作物代碼／來源名稱<select id='crop' disabled>{crops}</select></label><label>市場焦點<select id='market' disabled><option value='all'>全部</option><option value='109'>臺北一</option><option value='104'>臺北二</option></select></label><label>期間<select id='window' disabled><option value='7d'>7 日</option><option value='30d' selected>30 日</option><option value='90d'>90 日</option></select></label></div><div class='map-layout'><div><h2>市場所在地</h2><div class='map' id='map'>{map_html or '<p>區界不可用</p>'}</div><p id='legend'>價格色域：{number(min(prices)) if prices else '無資料'} 至 {number(max(prices)) if prices else '無資料'} 元/kg；圓面積對應量，參考最大值 {number(max(volumes), 0) if volumes else '無資料'} kg。市場位置未確認者不畫點；空心表示無有效觀測。行政區底色僅供定位。</p></div><div id='dynamic'>{_content(doc)}</div></div></section><section class='section'><h2>所有原始代碼截至日比較</h2><div class='table-wrap' tabindex='0' aria-label='截至日比較表，可水平捲動'><table><thead><tr><th>品項</th><th>代碼</th><th>臺北一 元/kg</th><th>臺北二 元/kg</th><th>臺北一 kg</th><th>臺北二 kg</th><th>價差 元/kg</th><th>臺北二相對臺北一 %</th><th>比較狀態</th></tr></thead><tbody>{comparisons}</tbody></table></div></section>"
    quality = doc.get('quality') or {}
    records = quality.get('by_date_market', [])
    counts = {key: sum(row.get(key, 0) for row in records) for key in ('observed', 'fixture', 'provenance_unknown', 'invalid')}
    reasons = {}
    for row in records:
        for reason, count in row.get('reasons', {}).items(): reasons[reason] = reasons.get(reason, 0) + count
    reason_text = '、'.join(f'{e(k)}：{v}' for k, v in sorted(reasons.items())) or '無'
    if not failed: body += f"<section class='section'><h2>資料品質</h2><p>來源列：observed {counts['observed']}、fixture {counts['fixture']}、provenance_unknown {counts['provenance_unknown']}、invalid {counts['invalid']}。排除與處理原因：{reason_text}。有效觀測日（任一品項）：104 {e(quality.get('valid_days_by_market', {}).get('104', 0))} 日、109 {e(quality.get('valid_days_by_market', {}).get('109', 0))} 日；休市成交衝突 {e(quality.get('calendar_conflicts', 0))}。</p></section>"
    body += "<section class='section'><h2>方法與來源</h2><p>7／30／90 日為截至日（含）往前的日曆窗口；量加權價 = 價格乘成交量之和／成交量之和。最低有效日數分別為 3／10／30，並非統計顯著性。缺列不代表沒有交易，不補零或插值。</p><p>來源：<a href='https://data.gov.tw/dataset/8066'>農業部農產品交易行情 8066</a>；<a href='https://data.taipei/dataset/detail?id=1601ef3a-c253-4988-b047-943d9e786143'>臺北市區界圖</a>；<a href='https://data.taipei/dataset/detail?id=4a50dd4a-b09c-47c8-9374-fc04a9e59cc9'>臺北市批發市場</a>。來源資料依臺北市政府資料開放授權條款使用。</p><p>來源資格及排除數、輸入雜湊與地理證據可見 JSON；此為 normalized snapshot 與 ingestion metadata，非逐列原始資料重播。</p><p>下載：<a href='../data/taipei/map.json'>JSON</a> · <a href='../data/taipei/map-observations.csv'>觀測 CSV</a></p></section></main>"
    return "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>臺北批發行情地圖</title><link rel='stylesheet' href='../assets/css/app.css'><link rel='stylesheet' href='../assets/css/taipei-map.css'><script defer src='../assets/js/taipei-map.js'></script></head><body><a class='skip' href='#main'>跳至主要內容</a>" + body + '</body></html>'


def map_js():
    return (Path(__file__).parent / 'assets' / 'taipei-map.js').read_text(encoding='utf-8')


def map_css():
    return (Path(__file__).parent / 'assets' / 'taipei-map.css').read_text(encoding='utf-8')


def map_initial_json(doc):
    """All crop choices with a 30-day grid; full 90-day data loads on demand."""
    initial = copy.deepcopy(doc)
    # Provenance and quality remain in the downloadable full document and SSR.
    initial.pop('inputs', None)
    initial.pop('quality', None)
    for series in initial.get('series', []):
        series['days'] = series['days'][-30:]
    return json.dumps(initial, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
