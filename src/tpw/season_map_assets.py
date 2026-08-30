def season_map_css():
    return """
.sr-only{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
.season-map-layout{display:grid;grid-template-columns:minmax(280px,.82fr) minmax(0,1.35fr);align-items:start;gap:18px}
.season-map-map-panel{position:sticky;top:68px}
.county-select-label{display:flex;flex-direction:column;gap:5px;margin:10px 0 14px;color:#37475a;font-size:.82rem;font-weight:800}
.county-select-label select{width:100%;min-height:44px;padding:9px 38px 9px 11px;border:1px solid var(--line);border-radius:12px;background:var(--paper);color:var(--ink);font:inherit}
.county-select-label select:focus-visible{outline:3px solid #7aa9ff;outline-offset:3px}
.taiwan-map{display:grid;place-items:center;min-height:380px;padding:12px;border:1px solid var(--line);border-radius:16px;background:linear-gradient(180deg,#f8fbff,#eef6fb)}
.taiwan-map svg{display:block;width:100%;height:auto;max-height:650px;overflow:visible}
.taiwan-map [data-county-link]{touch-action:manipulation}
.taiwan-map [data-county-path]{fill:#eaf1ff;stroke:#2d6cdf;stroke-width:1.5;vector-effect:non-scaling-stroke;transition:fill .16s ease,stroke-width .16s ease,filter .16s ease}
.taiwan-map [data-region$='-inset'] [data-county-path]{pointer-events:bounding-box}
.taiwan-map [data-county-link]:hover [data-county-path],.taiwan-map [data-county-link]:focus [data-county-path]{fill:#d7e5ff;stroke-width:2.5}
.taiwan-map [data-county-link]:focus-visible{outline:none}
.taiwan-map [data-county-link]:focus-visible [data-county-path]{filter:drop-shadow(0 0 2px #10243d);stroke:#10243d;stroke-width:3}
.taiwan-map [data-county-link][aria-current=true] [data-county-path]{fill:#cdeedd;stroke:#10243d;stroke-width:4;stroke-dasharray:8 4;filter:drop-shadow(0 2px 2px rgba(16,36,61,.28))}
.season-map-results{min-width:0}
.county-detail{scroll-margin-top:78px}
.county-detail-block{margin-top:20px;padding-top:18px;border-top:1px solid var(--line)}
.county-detail-block h3,.county-produce-group h4,.official-market-card h4,.season-map-produce-card h4{margin:.1rem 0 .35rem}
.county-produce-group+.county-produce-group{margin-top:18px}
.county-empty{grid-column:1/-1;margin:0}
.county-source-status{margin:.3rem 0 .75rem}
.semantic-warning{font-weight:700}
.official-market-card .badge{margin-top:4px}
.season-map-produce-card{padding:13px}
.season-map-produce-card .season-card-title{margin-bottom:0}
@media(max-width:900px){.season-map-layout{grid-template-columns:1fr}.season-map-map-panel{position:static}.taiwan-map svg{max-height:580px}}
@media(max-width:620px){.taiwan-map{min-height:300px;padding:8px}.taiwan-map svg{max-height:500px}.county-market-grid{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.taiwan-map [data-county-path]{transition:none}}
@media(forced-colors:active){.taiwan-map [data-county-path]{fill:Canvas;stroke:CanvasText}.taiwan-map [data-county-link][aria-current=true] [data-county-path]{fill:Highlight;stroke:HighlightText;stroke-width:4}}
@media print{.season-map-layout{display:block}.season-map-map-panel,.county-unselected{display:none!important}[data-county-section]{display:block!important}.county-detail{box-shadow:none;break-inside:auto}.county-detail-block,.official-market-card,.season-map-produce-card{break-inside:avoid}.official-market-card a[href^='https://']::after{content:' (' attr(href) ')';font-size:.75rem;font-weight:400;overflow-wrap:anywhere}}
""".strip()


def season_map_js():
    return """
(()=>{document.querySelectorAll('[data-season-map-root]').forEach(root=>{const sections=Array.from(root.querySelectorAll('[data-county-section]'));const countyBySlug=new Map(sections.map(section=>[section.dataset.countySection,section]));const links=Array.from(root.querySelectorAll('[data-county-link]'));const select=root.querySelector('[data-county-select]');const empty=root.querySelector('[data-county-unselected]');const live=root.querySelector('[data-county-live]');const currentUrl=()=>window.location.pathname+window.location.search+window.location.hash;const readSlug=()=>{if(!window.URL||!window.URLSearchParams)return null;const value=new window.URL(window.location.href).searchParams.get('county');return countyBySlug.has(value)?value:null};const writeUrl=(slug,method)=>{if(!window.URL||!window.history||typeof window.history[method]!=='function')return;const url=new window.URL(window.location.href);if(slug)url.searchParams.set('county',slug);else url.searchParams.delete('county');const next=url.pathname+url.search+url.hash;if(next!==currentUrl())window.history[method](window.history.state,'',next)};const apply=(requested,{historyMethod=null,focusResult=false}={})=>{const slug=countyBySlug.has(requested)?requested:null;sections.forEach(section=>{section.hidden=section.dataset.countySection!==slug});links.forEach(link=>{if(link.dataset.countyLink===slug)link.setAttribute('aria-current','true');else link.removeAttribute('aria-current')});if(select)select.value=slug||'';if(empty)empty.hidden=Boolean(slug);if(!slug){if(live)live.textContent='尚未選取縣市';if(historyMethod)writeUrl(null,historyMethod);return}const section=countyBySlug.get(slug);const name=section.dataset.countyName||slug;const markets=Number(section.dataset.marketCount||0);const produce=Number(section.dataset.produceCount||0);if(live)live.textContent=`已選取${name}，${markets} 個已驗證市場，${produce} 項本月產期品項`;if(historyMethod)writeUrl(slug,historyMethod);if(focusResult){const heading=section.querySelector('[data-county-heading]');if(heading){heading.focus({preventScroll:true});const reduced=typeof window.matchMedia==='function'&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;heading.scrollIntoView({behavior:reduced?'auto':'smooth',block:'start'})}}};root.dataset.enhanced='true';apply(readSlug());links.forEach(link=>link.addEventListener('click',event=>{event.preventDefault();apply(link.dataset.countyLink,{historyMethod:'pushState',focusResult:true})}));if(select)select.addEventListener('change',()=>apply(select.value,{historyMethod:'pushState',focusResult:Boolean(select.value)}));window.addEventListener('popstate',()=>apply(readSlug()))})})();
""".strip() + "\n"
