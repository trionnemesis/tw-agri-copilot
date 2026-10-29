/* Progressive enhancement: payload is loaded and checked before any state is changed. */
(() => {
  'use strict';
  const ids = ['item', 'crop', 'market', 'window'];
  const controls = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
  if (!controls.item) return;
  const status = document.getElementById('control-status');
  const dynamic = document.getElementById('dynamic');
  const legend = document.getElementById('legend');
  const defaults = {item:'cabbage', crop:'LA2', market:'all', window:'30d'};
  const esc = v => String(v ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (v, digits=2) => v == null ? '—' : Number(v).toLocaleString('en-US', {minimumFractionDigits:digits, maximumFractionDigits:digits});
  let data, state = {...defaults};
  const find = (rows, code, crop) => rows.find(r => r.market_code === code && r.product_code_raw === crop) || {};
  const day = (series, date) => (series.days || []).find(d => d.date === date) || {};
  function chart(crop, window, field, title, unit) {
    const count = parseInt(window, 10), sets = ['109','104'].map(code => [code, (find(data.series,code,crop).days || []).slice(-count)]);
    const vals = sets.flatMap(([,days]) => days.filter(d => d.observation_status === 'observed' && d[field] != null).map(d => d[field]));
    const ceiling = vals.length ? Math.max(...vals)*1.1 || 1 : 1;
    let out = `<svg class="chart" viewBox="0 0 720 240" role="img" aria-label="${esc(title)}，${esc(unit)}"><line x1="55" y1="200" x2="700" y2="200" stroke="#777"/><line x1="55" y1="20" x2="55" y2="200" stroke="#777"/><text x="4" y="25">${num(ceiling,1)}</text><text x="35" y="204">0</text>`;
    for (const [code, days] of sets) {
      let points = [];
      const flush = () => { if (points.length > 1) out += `<polyline class="line m${code}" points="${points.join(' ')}"/>`; points = []; };
      days.forEach((d,i) => { const v=d[field]; if (v == null || d.observation_status !== 'observed') { flush(); return; }
        const x=55+i*645/Math.max(count-1,1), y=200-v/ceiling*180; points.push(`${x.toFixed(2)},${y.toFixed(2)}`);
        out += `<circle class="dot m${code}" cx="${x}" cy="${y}" r="3"><title>${esc(code)} ${esc(d.date)}: ${num(v)} ${esc(unit)}</title></circle>`;
      }); flush();
    }
    const dates=sets.flatMap(([,days])=>days.map(d=>d.date)).sort();
    if(dates.length) out += `<text x="55" y="225">${esc(dates[0])}</text><text x="700" y="225" text-anchor="end">${esc(dates[dates.length-1])}</text>`;
    return out + '</svg>';
  }
  function draw(s) {
    const cards=['109','104'].map(code => {
      const d=day(find(data.series,code,s.crop),data.as_of_date), stat=find(data.statistics,code,s.crop), w=(stat.windows || {})[s.window] || {}, geo=(data.geography.markets || []).find(m=>m.market_code===code)||{};
      const prev=stat.previous_observation || {};
      return `<article class="market-card ${s.market !== 'all' && s.market !== code ? 'unfocused' : ''}" id="market-${code}" tabindex="-1" data-market="${code}"><h3>${code==='109'?'臺北一':'臺北二'}（${code}）</h3><p>截至日價格 <strong>${num(d.price_twd_per_kg)} 元/kg</strong> · 成交量 ${num(d.volume_kg,0)} kg</p><p>觀測：${esc(d.observation_status || '未觀測到此代碼')}；日曆：${esc(d.calendar_status || '未知')}${d.calendar_conflict?'；休市成交衝突':''}</p><p>${esc(s.window)} 量加權價 ${num(w.price_twd_per_kg)} 元/kg；成交量 ${num(w.total_volume_kg,0)} kg；有效 ${esc(w.coverage_days ?? 0)}／最低 ${esc(w.minimum_days)} 日（${esc(w.status || 'insufficient')} ${esc(w.insufficient_reason || '')}）</p><p>最新有效觀測 ${esc(prev.latest_date)}；較前次有效觀測 ${esc(prev.date)}（間隔 ${esc(prev.interval_days)} 日）：${num(prev.change_pct)}%</p><p>位置：${esc(geo.location_status || 'unverified')} · ${esc(geo.location_role || '位置待確認')}；核對日 ${esc(geo.verified_at)}。${esc(geo.location_note || '')}</p></article>`;
    }).join('');
    const c=data.comparisons.find(c=>c.product_code_raw===s.crop && c.canonical_id===s.item)||{};
    const rows=['109','104'].flatMap(code=>(find(data.series,code,s.crop).days||[]).slice(-parseInt(s.window,10)).map(d=>`<tr><td>${esc(d.date)}</td><td>${code}</td><td>${num(d.price_twd_per_kg)}</td><td>${num(d.volume_kg,0)}</td><td>${esc(d.observation_status)}</td><td>${esc(d.calendar_status)}${d.calendar_conflict?'（衝突）':''}</td></tr>`)).join('');
    dynamic.innerHTML=`<div class="market-grid">${cards}</div><p>同日價差（臺北二 − 臺北一）：${num(c.absolute_gap)} 元/kg；臺北二相對臺北一 ${num(c.relative_gap_pct)}%（${esc(c.comparison_status || 'not_comparable')}）。同作物代碼比較，未控制等級與批次差異。</p><section><h2>價格趨勢（元/kg）</h2><p>臺北一：實線　臺北二：虛線；缺資料處斷線。</p>${chart(s.crop,s.window,'price_twd_per_kg','價格趨勢','元/kg')}</section><section><h2>成交量趨勢（kg）</h2>${chart(s.crop,s.window,'volume_kg','成交量趨勢','kg')}</section><section><h2>每日觀測與品質</h2><div class="table-wrap" tabindex="0" aria-label="每日觀測表，可水平捲動"><table><thead><tr><th>日期</th><th>市場</th><th>價格 元/kg</th><th>量 kg</th><th>觀測狀態</th><th>日曆狀態</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
    const obs=data.series.filter(r=>r.canonical_id===s.item && r.product_code_raw===s.crop).flatMap(r=>r.days.slice(-parseInt(s.window,10))).filter(d=>d.observation_status==='observed' && d.price_twd_per_kg != null && d.volume_kg != null);
    const prices=obs.map(d=>d.price_twd_per_kg), volumes=obs.map(d=>d.volume_kg), lo=Math.min(...prices), hi=Math.max(...prices), vmax=Math.max(...volumes);
    document.querySelectorAll('.map-marker').forEach(a=>{const d=day(find(data.series,a.dataset.code,s.crop),data.as_of_date), circle=a.querySelector('.data-circle'); const ok=d.observation_status==='observed' && d.price_twd_per_kg!=null && d.volume_kg!=null && vmax>0;
      circle.setAttribute('r',ok ? 25*Math.sqrt(d.volume_kg/vmax):7); circle.dataset.available=String(ok); if(ok){const q=hi===lo?.5:(d.price_twd_per_kg-lo)/(hi-lo);circle.setAttribute('fill',`rgb(${Math.round(51+155*q)},${Math.round(133-70*q)},75)`);circle.dataset.volume=d.volume_kg;circle.dataset.price=d.price_twd_per_kg;}else{circle.setAttribute('fill','white');delete circle.dataset.volume;delete circle.dataset.price;} a.classList.toggle('unfocused',s.market!=='all' && s.market!==a.dataset.code);
    });
    legend.textContent=`價格色域：${prices.length?num(lo):'無資料'} 至 ${prices.length?num(hi):'無資料'} 元/kg；圓面積對應量，參考最大值 ${volumes.length?num(vmax,0):'無資料'} kg。市場位置未確認者不畫點；空心表示無有效觀測。行政區底色僅供定位。`;
  }
  function normalize(input) {
    const item=data.items.find(i=>i.canonical_id===input.item), valid=item && item.crops.some(c=>c.product_code_raw===input.crop) && ['all','104','109'].includes(input.market) && ['7d','30d','90d'].includes(input.window);
    return valid ? {state:input,invalid:false} : {state:{...defaults},invalid:true};
  }
  function fromURL() { const q=new URLSearchParams(location.search); return normalize(Object.fromEntries(ids.map(id=>[id,q.get(id) || defaults[id]]))); }
  function commit(next, push, notice='') {
    const result=normalize(next); next=result.state;
    const item=data.items.find(i=>i.canonical_id===next.item);
    controls.crop.innerHTML=item.crops.map(c=>`<option value="${esc(c.product_code_raw)}">${esc(c.product_code_raw)} · ${esc(c.product_name_raw)}</option>`).join('');
    ids.forEach(id=>controls[id].value=next[id]); draw(next);
    if(push && ids.some(id=>next[id]!==state[id])) { const u=new URL(location.href); ids.forEach(id=>u.searchParams.set(id,next[id])); history.pushState(null,'',u); }
    state={...next}; status.textContent=result.invalid?'網址或選擇無效，已回到預設甘藍 LA2、全部市場、30 日。':notice || `已選 ${item.display_name} ${next.crop}，${next.window}，市場焦點 ${next.market}。`;
  }
  let generation=0, fullData=null;
  function check(d, minDays) {
    const finite = v => v === null || (typeof v === 'number' && Number.isFinite(v));
    const obj = v => v && typeof v === 'object' && !Array.isArray(v);
    if (!obj(d) || !Array.isArray(d.items) || !Array.isArray(d.series) || !Array.isArray(d.statistics) || !Array.isArray(d.comparisons) || !obj(d.geography) || !Array.isArray(d.geography.markets) || typeof d.as_of_date !== 'string') throw Error('資料格式無效');
    if (!d.items.every(i=>obj(i) && typeof i.canonical_id==='string' && typeof i.display_name==='string' && Array.isArray(i.crops) && i.crops.length && i.crops.every(c=>obj(c) && typeof c.product_code_raw==='string' && typeof c.product_name_raw==='string')) || !d.items.some(i=>i.canonical_id==='cabbage' && i.crops.some(c=>c.product_code_raw==='LA2'))) throw Error('品項格式無效');
    if (!d.series.every(r=>obj(r) && typeof r.market_code==='string' && typeof r.canonical_id==='string' && typeof r.product_code_raw==='string' && Array.isArray(r.days) && r.days.length>=minDays && r.days.every(x=>obj(x) && typeof x.date==='string' && typeof x.observation_status==='string' && typeof x.calendar_status==='string' && finite(x.price_twd_per_kg) && finite(x.volume_kg)))) throw Error('序列格式無效');
    if (!d.statistics.every(r=>obj(r) && obj(r.windows) && ['7d','30d','90d'].every(k=>obj(r.windows[k])) && obj(r.previous_observation)) || !d.comparisons.every(obj) || !d.geography.markets.every(obj)) throw Error('統計格式無效');
    const crops=d.items.flatMap(i=>i.crops.map(c=>[i.canonical_id,c.product_code_raw]));
    const key=(item,crop,market)=>`${item}\u0000${crop}\u0000${market}`;
    const expected=new Set(crops.flatMap(([item,crop])=>['104','109'].map(m=>key(item,crop,m))));
    if(expected.size!==crops.length*2 || d.series.length!==expected.size || d.statistics.length!==expected.size || d.comparisons.length!==crops.length) throw Error('資料筆數無效');
    for(const rows of [d.series,d.statistics]) { const seen=new Set(); for(const r of rows) {const k=key(r.canonical_id,r.product_code_raw,r.market_code); if(!expected.has(k)||seen.has(k))throw Error('資料識別無效');seen.add(k);} }
    const seenComparisons=new Set(); for(const c of d.comparisons) {const k=key(c.canonical_id,c.product_code_raw,'104'); if(!expected.has(k)||seenComparisons.has(k)||c.date!==d.as_of_date || !['comparable','not_comparable'].includes(c.comparison_status) || !['price_104','price_109','volume_104','volume_109','absolute_gap','relative_gap_pct'].every(k=>finite(c[k]))) throw Error('比較格式無效');seenComparisons.add(k);}
    for(const r of d.series) {if(r.days.length!==minDays || r.days[r.days.length-1].date!==d.as_of_date)throw Error('日期範圍無效'); for(let i=0;i<r.days.length;i++){const day=r.days[i], date=Date.parse(day.date+'T00:00:00Z'); if(!Number.isFinite(date) || (i && date-Date.parse(r.days[i-1].date+'T00:00:00Z')!==86400000) || (day.observation_status==='observed' && (!(day.price_twd_per_kg>0)||!(day.volume_kg>0))))throw Error('日期格點無效');}}
    for(const r of d.statistics) for(const name of ['7d','30d','90d']) {const w=r.windows[name]; if(!finite(w.price_twd_per_kg)||!finite(w.total_volume_kg)||!Number.isInteger(w.coverage_days)||!Number.isInteger(w.minimum_days)||!['valid','insufficient'].includes(w.status))throw Error('統計值無效');}
    return d;
  }
  const load = (url, days) => fetch(url).then(r=>{if(!r.ok) throw Error('HTTP '+r.status); return r.json();}).then(d=>check(d,days));
  async function choose(next, push, notice='') {
    const ticket=++generation;
    ids.forEach(id=>controls[id].value=state[id]);
    const normalized=normalize(next);
    next=normalized.state;
    try {
      if(next.window==='90d' && !fullData) { const fetched=await load('../data/taipei/map.json',90); if(ticket!==generation)return; fullData=fetched; }
      if(ticket!==generation)return;
      if(fullData) data=fullData;
      commit(next,push,normalized.invalid?'網址或選擇無效，已回到預設。':notice);
    } catch (_) {
      if(ticket!==generation)return;
      ids.forEach(id=>controls[id].value=state[id]);
      const u=new URL(location.href); ids.forEach(id=>u.searchParams.set(id,state[id])); history.replaceState(null,'',u);
      status.textContent='互動資料載入失敗，保留先前完整選擇；請稍後重試。';
    }
  }
  load('../data/taipei/map-ui.json',30).then(async d=>{
    data=d; const initial=fromURL();
    await choose(initial.state,false,initial.invalid?'網址參數無效，已回到預設甘藍 LA2、全部市場、30 日。':'互動已啟用。');
    ids.forEach(id=>controls[id].disabled=false);
    ids.forEach(id=>controls[id].addEventListener('change',()=>{const next={...state,[id]:controls[id].value}; if(id==='item'){const item=data.items.find(i=>i.canonical_id===next.item); next.crop=item.crops[0].product_code_raw;} choose(next,true);}));
    document.querySelectorAll('.map-marker').forEach(a=>a.addEventListener('click',ev=>{ev.preventDefault();choose({...state,market:a.dataset.code},true).then(()=>document.getElementById('market-'+a.dataset.code).focus({preventScroll:true}));}));
    addEventListener('popstate',()=>{const v=fromURL();choose(v.state,false,v.invalid?'網址參數無效，已回到預設。':'已還原網址選擇。');});
  }).catch(()=>{status.textContent='互動資料載入失敗，保留預設靜態內容；請稍後重新載入。';});
})();
