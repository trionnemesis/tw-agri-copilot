import html
import json

from .publication import validate_market_status


DISCLAIM = "批發市場平均行情，非實際零售通路售價。"
TRACE_WARNING = "此為同品項的公開產銷履歷紀錄，非本日市場成交來源證明。"


def _escape(value):
    return html.escape(str(value))


def _number(value, digits=1):
    return "—" if value is None else f"{value:,.{digits}f}"


def _price(value):
    return "—" if value is None else f"NT$ {value:,.2f}/kg"


def _percent(value):
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _pct_class(value):
    if value is None:
        return "neu"
    return "pos" if value < 0 else "neg" if value > 0 else "neu"


def page(title, body, css="assets/css/app.css"):
    return _document(title, f"<main id='main' class='wrap'>{body}</main>", css)


def _document(title, body, css="assets/css/app.css", js=None, description=None):
    script = f"<script defer src='{_escape(js)}'></script>" if js else ""
    meta_description = _escape(description or "Taiwan Produce Watch 台灣蔬果行情原型")
    return (
        "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta name='description' content='{meta_description}'>"
        f"<title>{_escape(title)}</title><link rel='stylesheet' href='{_escape(css)}'>{script}"
        "</head><body><a class='skip' href='#main'>跳至主要內容</a>"
        f"{body}</body></html>"
    )


def _toolbar(prefix=""):
    links = (
        ("首頁", f"{prefix}index.html"),
        ("當季", f"{prefix}season/current.html"),
        ("日趨勢", f"{prefix}trends/daily.html"),
        ("週趨勢", f"{prefix}trends/weekly.html"),
        ("月趨勢", f"{prefix}trends/monthly.html"),
        ("季趨勢", f"{prefix}trends/quarterly.html"),
        ("產銷履歷", f"{prefix}traceability/index.html"),
        ("歷史", f"{prefix}archive/index.html"),
        ("方法", f"{prefix}methodology.html"),
    )
    return "<nav class='toolbar' aria-label='主要導覽'><div class='inner'>" + "".join(
        f"<a href='{href}'>{label}</a>" for label, href in links
    ) + "<button type='button' data-print>列印 / 存 PDF</button></div></nav>"


def _hero(as_of, source_status, in_season_count, recommendation_count, publication_status):
    return (
        "<header class='hero'><div class='wrap'>"
        "<div class='eyebrow'>TAIWAN PRODUCE WATCH</div>"
        "<h1>今天吃什麼？</h1>"
        "<p>台灣當季蔬果 × 每日批發行情 × AI 採買情報</p>"
        "<div class='meta'>"
        f"<span>最近完整交易日：{_escape(as_of)}</span>"
        f"<span>今日資料檢查：{_escape(publication_status['requested_date'])}</span>"
        f"<span>當季品項：{in_season_count}</span>"
        f"<span>推薦品項：{recommendation_count}</span>"
        f"<span>資料狀態：{_escape(source_status)}</span>"
        "</div></div></header>"
    )


def _market_status_notice(status):
    state = status["status"]
    requested = status["requested_date"]
    resolved = status["resolved_date"]
    if state == "complete":
        heading = f"行情已更新至 {resolved}"
        expected = status["expected_watchlist_count"]
        message = f"已檢查 {requested} 的官方行情，{expected} 項觀察清單資料完整。"
    elif state == "market_closed":
        heading = f"{requested} 今日休市"
        message = f"農業部資料已標示休市；目前沿用最近完整交易日 {resolved}，並非網站漏更新。"
    elif state == "incomplete":
        heading = f"{requested} 行情尚未完整"
        message = f"今日資料已檢查，但尚未涵蓋完整觀察清單；目前顯示最近完整交易日 {resolved}。"
    elif state == "pending":
        heading = f"{requested} 尚無完整行情"
        message = f"今日資料已檢查，目前尚無可發布的完整交易行情；先顯示最近完整交易日 {resolved}。"
    else:
        heading = f"{requested} 官方資料暫時無法取得"
        message = f"系統已完成重試並保留 last-known-good；目前顯示最近完整交易日 {resolved}。"
    return (
        f"<aside class='market-status market-status--{_escape(state)}' "
        f"data-market-status='{_escape(state)}' role='status' aria-live='polite'>"
        f"<div class='wrap'><strong>{_escape(heading)}</strong><span>{_escape(message)}</span>"
        "</div></aside>"
    )


def _season_source_notice(rows):
    status = rows[0].get("source_status", "fallback") if rows else "fallback"
    source_url = rows[0].get("source_url", "") if rows else ""
    if status == "live":
        message = "清單已由農糧署『農產品產地產期查詢』抓取並完成欄位與分頁驗證。"
    elif status == "stale":
        message = "本次官方查詢暫時無法取得，清單沿用同月份最近一次通過驗證的資料。"
    else:
        message = "目前使用專案內建產季參考資料；未涵蓋品項不會直接判定為非當季。"
    source = f" <a href='{_escape(source_url)}'>查看官方來源</a>" if source_url else ""
    note_class = "note warn" if status != "live" else "note"
    return f"<p class='{note_class}' data-season-source='{_escape(status)}'>{_escape(message)}{source}</p>"


def _season_page(catalog, series, traceability):
    market_ids = {row["canonical_id"] for row in series}
    trace_ids = {row["canonical_id"] for row in traceability}
    cards = []
    for row in sorted(catalog, key=lambda value: value["display_name"]):
        canonical_id = row.get("canonical_id")
        market_available = canonical_id in market_ids
        trace_available = canonical_id in trace_ids
        detail = (
            f"<a class='card-link' href='../produce/{_escape(canonical_id)}.html'>查看行情詳情 →</a>"
            if canonical_id
            else "<span class='small'>目前不在行情觀察清單</span>"
        )
        cards.append(
            f"<article class='card season-card' data-category='{_escape(row['category'])}' "
            f"data-search-name='{_escape(row['display_name'])}'>"
            f"<div class='label'>{'水果' if row['category']=='fruit' else '蔬菜'}</div>"
            f"<h2>{_escape(row['display_name'])}</h2>"
            f"<p>{row['county_count']} 個產地縣市 · {row.get('variety_count', 0)} 個品種</p>"
            f"<div class='reasons'><span class='reason'>{'有行情資料' if market_available else '無行情資料'}</span>"
            f"<span class='reason'>{'有相關履歷' if trace_available else '無相關履歷'}</span></div>"
            f"<p class='small'>主要產地：{_escape('、'.join(row['counties']) or '—')}</p>{detail}</article>"
        )
    fruit_count = len([row for row in catalog if row["category"] == "fruit"])
    vegetable_count = len(catalog) - fruit_count
    return (
        "<header class='page-hero'><div class='wrap'><div class='eyebrow'>SEASONALITY</div>"
        "<h1>本月當季蔬果</h1><p>農糧署盛產資料 × 行情與履歷狀態</p></div></header>"
        + _toolbar("../")
        + "<main id='main' class='wrap'><section class='section'><div class='section-heading'><div>"
        + f"<h2>完整清單</h2><p class='lead'>共 {len(catalog)} 項：水果 {fruit_count} 項、蔬菜 {vegetable_count} 項。</p></div>"
        + "<div class='filter-group' aria-label='當季品項篩選'><button type='button' data-filter='all' aria-pressed='true'>全部</button>"
        + "<button type='button' data-filter='fruit' aria-pressed='false'>水果</button><button type='button' data-filter='vegetable' aria-pressed='false'>蔬菜</button></div></div>"
        + _season_source_notice(catalog)
        + "<div class='season-controls'><label class='season-search' for='season-search'><span>搜尋蔬果名稱</span>"
        + "<input id='season-search' type='search' data-season-search aria-controls='season-grid' "
        + "aria-describedby='season-result-count' autocomplete='off' placeholder='輸入蔬果名稱，例如：甘藍、木瓜'></label>"
        + f"<p class='season-result-count' id='season-result-count' data-season-result-count role='status' aria-live='polite' aria-atomic='true'>顯示 {len(catalog)} 項</p></div>"
        + f"<div class='grid grid-3' id='season-grid' data-season-grid>{''.join(cards)}</div>"
        + "<p class='note warn season-empty' data-season-empty hidden>找不到符合目前搜尋與分類條件的當季蔬果。</p></section></main>"
    )


REASON_LABELS = {
    "IN_SEASON": "當季",
    "PRICE_AT_OR_BELOW_7D": "不高於 7D",
    "PRICE_AT_OR_BELOW_30D": "不高於 30D",
    "VOLUME_HEALTHY": "量能穩健",
    "COVERAGE_INSUFFICIENT": "天數不足",
    "MARKET_COUNT_INSUFFICIENT": "市場不足",
    "DATA_QUALITY_WARNING": "品質警示",
}


def _recommendation_card(score, item, prefix="", trace_available=False):
    verdict_class = {
        "priority": "positive",
        "consider": "positive",
        "watch": "neutral",
        "hold": "neutral",
        "insufficient": "negative",
        "not_ranked": "negative",
    }[score["verdict"]]
    reasons = "".join(
        f"<span class='reason'>{_escape(REASON_LABELS.get(code, code))}</span>"
        for code in score["reason_codes"]
    )
    trace_badge = "<span class='badge info'>有相關履歷</span>" if trace_available else ""
    return (
        f"<article class='recommendation-card {verdict_class}'>"
        "<div class='card-top'>"
        f"<div><span class='badge info'>{'水果' if item['category']=='fruit' else '蔬菜'}</span> "
        f"<span class='badge pos'>當季</span> {trace_badge}</div>"
        f"<span class='score'>{score['score']}</span></div>"
        f"<h3>{_escape(item['display_name'])}</h3>"
        f"<p class='verdict-label'>{_escape(score['verdict_label'])}</p>"
        f"<div class='card-price'>{_price(score['today_price'])}</div>"
        "<dl class='metrics'>"
        f"<div><dt>前一交易日</dt><dd>{_percent(score['previous_trading_day_change_pct'])}</dd></div>"
        f"<div><dt>vs 7D</dt><dd>{_percent(score['vs_7d_pct'])}</dd></div>"
        f"<div><dt>vs 30D</dt><dd>{_percent(score['vs_30d_pct'])}</dd></div>"
        f"<div><dt>量 vs 7D</dt><dd>{_percent(score['volume_vs_7d_pct'])}</dd></div>"
        "</dl>"
        f"<div class='reasons'>{reasons}</div>"
        f"<p class='small'>資料日期：{_escape(score['as_of_date'])}</p>"
        f"<a class='card-link' href='{prefix}produce/{_escape(score['canonical_id'])}.html'>查看品項詳情 →</a>"
        "</article>"
    )


def _market_table(rows, kind, heading=None):
    selected = [row for row in rows if row["category"] == kind]
    body = "".join(
        "<tr>"
        f"<th scope='row'>{_escape(row['display_name'])}</th>"
        f"<td class='num'>{_price(row['weighted_avg_price_twd_per_kg'])}</td>"
        f"<td class='num'>{_number(row['total_volume_kg'], 0)} kg</td>"
        f"<td class='num'>{row.get('market_count', '—')}</td>"
        "</tr>"
        for row in selected
    ) or "<tr><td colspan='4'>—</td></tr>"
    title = heading or ("水果行情" if kind == "fruit" else "蔬菜行情")
    return (
        f"<section class='section'><h2>{_escape(title)}</h2>"
        f"<p class='disclaimer'>{DISCLAIM}</p><div class='table-wrap'><table>"
        "<thead><tr><th>品項</th><th class='num'>加權平均價</th><th class='num'>交易量</th><th class='num'>市場數</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div></section>"
    )


def _advice_section(advice, items):
    item_map = {item["canonical_id"]: item["display_name"] for item in items}
    priority = "".join(
        f"<li><strong>{_escape(item_map.get(row['canonical_id'], row['canonical_id']))}</strong>：{_escape(row['text'])}</li>"
        for row in advice["priority_items"]
    ) or "<li>本期沒有通過完整 eligibility gate 的正向推薦。</li>"
    watch = "".join(
        f"<li><strong>{_escape(item_map.get(row['canonical_id'], row['canonical_id']))}</strong>：{_escape(row['text'])}</li>"
        for row in advice["watch_items"]
    ) or "<li>目前沒有額外觀察項目。</li>"
    return (
        "<section class='section ai-summary' id='advice'><div class='section-heading'>"
        "<div><div class='eyebrow ink'>DETERMINISTIC ADVICE</div><h2>AI 今日採買情報</h2></div>"
        f"<span class='badge neu'>{_escape(advice['generation_mode'])}</span></div>"
        f"<h3>{_escape(advice['headline'])}</h3><p class='lead'>{_escape(advice['summary'])}</p>"
        "<div class='grid grid-2'><div class='note'><strong>優先理由</strong><ul>"
        f"{priority}</ul></div><div class='note warn'><strong>觀察理由</strong><ul>{watch}</ul></div></div>"
        f"<p class='small'>資料日期：{_escape(advice['as_of_date'])} · 模式：{_escape(advice['generation_mode'])} · prompt：{_escape(advice['prompt_version'])}</p>"
        f"<p class='disclaimer'>{_escape(advice['disclaimer'])}</p></section>"
    )


def _sparkline(points):
    values = [row["price_twd_per_kg"] for row in points if row["price_twd_per_kg"] is not None]
    if len(values) < 2:
        return "<p class='note warn'>趨勢資料不足，請參考下方表格。</p>"
    low, high = min(values), max(values)
    span = high - low or 1
    coordinates = []
    for index, value in enumerate(values):
        x = index / (len(values) - 1) * 700
        y = 180 - (value - low) / span * 150
        coordinates.append(f"{x:.1f},{y:.1f}")
    return (
        "<div class='chart' role='img' aria-label='近期香港價格趨勢折線圖'>"
        "<svg viewBox='0 0 700 200' preserveAspectRatio='none' aria-hidden='true'>"
        "<line x1='0' y1='180' x2='700' y2='180' class='axis'/><polyline points='"
        + " ".join(coordinates)
        + "' class='price-line'/></svg></div>"
    )


def _home(items, scores, series, seasonality, advice, traceability, quality, as_of, source_status, publication_status):
    item_map = {item["canonical_id"]: item for item in items}
    series_map = {row["canonical_id"]: row for row in series}
    trace_ids = {row["canonical_id"] for row in traceability}
    in_season = [row for row in seasonality if row["seasonality_status"] == "in_season"]
    recommendations = [row for row in scores if row["eligible"]][:6]
    cards = "".join(
        _recommendation_card(row, item_map[row["canonical_id"]], trace_available=row["canonical_id"] in trace_ids)
        for row in recommendations
    ) or "<div class='note warn'>資料覆蓋率或品質 gate 尚未通過，本期不產生正向推薦。</div>"
    season_cards = "".join(
        f"<article class='card season-card' data-category='{_escape(row['category'])}'>"
        f"<div class='label'>{'水果' if row['category']=='fruit' else '蔬菜'}</div>"
        f"<h3>{_escape(row['display_name'])}</h3>"
        f"<p>{row['county_count']} 個產地縣市 · {'有' if row['canonical_id'] in series_map else '無'}行情 · {'有' if row['canonical_id'] in trace_ids else '無'}相關履歷</p>"
        f"<a href='produce/{_escape(row['canonical_id'])}.html'>查看詳情 →</a></article>"
        for row in in_season
    )
    movers = [row for row in scores if row["previous_trading_day_change_pct"] is not None]
    cheaper = sorted(movers, key=lambda row: row["previous_trading_day_change_pct"])[:5]
    pricier = sorted(movers, key=lambda row: row["previous_trading_day_change_pct"], reverse=True)[:5]
    def mover_list(rows):
        return "".join(
            f"<li><a href='produce/{_escape(row['canonical_id'])}.html'>{_escape(item_map[row['canonical_id']]['display_name'])}</a>"
            f"<span class='badge {_pct_class(row['previous_trading_day_change_pct'])}'>{_percent(row['previous_trading_day_change_pct'])}</span></li>"
            for row in rows
        ) or "<li>—</li>"
    trend_cards = "".join(
        f"<article class='card'><div class='label'>{_escape(item_map[row['canonical_id']]['display_name'])}</div>"
        f"<div class='value'>{_price(row['today']['price_twd_per_kg'])}</div>"
        f"<div class='sub'>7D {_percent(row['windows']['7d']['today_change_pct'])} · 30D {_percent(row['windows']['30d']['today_change_pct'])}</div>"
        f"<a href='produce/{_escape(row['canonical_id'])}.html'>趨勢與覆蓋率 →</a></article>"
        for row in series[:4]
    )
    warning_text = "、".join(quality["warnings"]) or "無"
    return (
        _hero(as_of, source_status, len(in_season), len(recommendations), publication_status)
        + _market_status_notice(publication_status)
        + _toolbar()
        + "<main id='main' class='wrap'>"
        + "<section class='section recommendations' id='recommendations'><div class='section-heading'><div>"
        + "<div class='eyebrow ink'>BUY SCORE · EVIDENCE FIRST</div><h2>今日推薦採買</h2></div>"
        + f"<span class='badge info'>{len(recommendations)} 項通過 gate</span></div>"
        + f"<p class='disclaimer'>{DISCLAIM}</p><div class='recommendation-grid'>{cards}</div></section>"
        + _advice_section(advice, items)
        + "<section class='section' id='season'><div class='section-heading'><div><div class='eyebrow ink'>SEASONALITY</div><h2>本月當季蔬果</h2></div>"
        + "<div class='filter-group' aria-label='當季品項篩選'><button type='button' data-filter='all' aria-pressed='true'>全部</button><button type='button' data-filter='fruit' aria-pressed='false'>水果</button><button type='button' data-filter='vegetable' aria-pressed='false'>蔬菜</button></div></div>"
        + _season_source_notice(seasonality)
        + f"<div class='grid grid-3' data-season-grid>{season_cards}</div><p><a href='season/current.html'>查看完整當季清單 →</a></p></section>"
        + "<section class='section' id='movers'><h2>今日變便宜／今日變貴</h2><p class='lead'>以各品項前一個有效交易日為基準。</p>"
        + f"<div class='grid grid-2'><div class='verdict positive'><strong>今天變便宜</strong><ul class='mover-list'>{mover_list(cheaper)}</ul></div>"
        + f"<div class='verdict negative'><strong>今天變貴</strong><ul class='mover-list'>{mover_list(pricier)}</ul></div></div></section>"
        + "<section class='section' id='trends'><div class='section-heading'><div><div class='eyebrow ink'>ROLLING ANALYTICS</div><h2>日／週／月／季趨勢</h2></div>"
        + "<div class='tabs'><a href='trends/daily.html'>日</a><a href='trends/weekly.html'>週</a><a href='trends/monthly.html'>月</a><a href='trends/quarterly.html'>季</a></div></div>"
        + f"<div class='grid grid-4'>{trend_cards}</div></section>"
        + "<section class='section' id='origins'><h2>產地／產銷履歷入口</h2>"
        + f"<div class='grid grid-2'><div class='note'><strong>當季主要產地</strong><p>{len(in_season)} 項行情觀察品項具當季資料；產地只作季節背景，不代表當日成交來源。</p><a href='season/current.html'>查看當季與產地 →</a></div>"
        + f"<div class='note warn'><strong>相關產銷履歷</strong><p>{len(traceability)} 筆最小化 prototype fixture。{TRACE_WARNING}</p><a href='traceability/index.html'>查看履歷邊界 →</a></div></div></section>"
        + "<section class='section' id='history'><h2>歷史紀錄</h2><p>每日 HTML、Markdown 與 machine-readable JSON 都保留在 repo 中。</p><a href='archive/index.html'>開啟日期封存 →</a></section>"
        + "<section class='section sources' id='sources'><h2>資料來源、方法與限制</h2>"
        + f"<p class='disclaimer'>{DISCLAIM}</p><p>行情以各市場交易量加權；推薦由 deterministic Buy Score 產生，AI 只能解釋，不能改變數值或 verdict。</p>"
        + f"<p class='small'>資料狀態：{_escape(source_status)} · 品質警示：{_escape(warning_text)}</p><a href='methodology.html'>閱讀完整方法 →</a></section>"
        + "</main><footer class='footer'>Taiwan Produce Watch · side-project prototype</footer>"
    )


def _produce_page(item, series, score, season, trace_rows):
    windows = series["windows"]
    season_source = {"live": "官方資料", "stale": "最近驗證資料", "fallback": "內建參考"}.get(
        season.get("source_status"), "參考資料"
    )
    daily_rows = "".join(
        f"<tr><th scope='row'>{_escape(row['date'])}</th><td class='num'>{_price(row['price_twd_per_kg'])}</td><td class='num'>{_number(row['volume_kg'],0)} kg</td></tr>"
        for row in reversed(series["daily"][-14:])
    )
    trace_html = "".join(
        f"<tr><th scope='row'>{_escape(row['tracecode'])}</th><td>{_escape(row['producer'] or '—')}</td><td>{_escape(row['place'] or '—')}</td><td>{_escape(row['certification_name'] or '—')}</td></tr>"
        for row in trace_rows
    ) or "<tr><td colspan='4'>目前沒有相關紀錄。</td></tr>"
    return (
        "<header class='page-hero'><div class='wrap'><div class='eyebrow'>PRODUCE DETAIL</div>"
        f"<h1>{_escape(item['display_name'])}</h1><p>{'水果' if item['category']=='fruit' else '蔬菜'} · {_escape(score['verdict_label'])}</p></div></header>"
        + _toolbar("../")
        + "<main id='main' class='wrap'>"
        + f"<section class='section'><div class='grid grid-4'><div class='card'><div class='label'>今日</div><div class='value'>{_price(series['today']['price_twd_per_kg'])}</div></div>"
        + f"<div class='card'><div class='label'>7D</div><div class='value'>{_price(windows['7d']['price_twd_per_kg'])}</div><div class='sub'>{windows['7d']['coverage_days']} 日</div></div>"
        + f"<div class='card'><div class='label'>30D</div><div class='value'>{_price(windows['30d']['price_twd_per_kg'])}</div><div class='sub'>{windows['30d']['coverage_days']} 日</div></div>"
        + f"<div class='card'><div class='label'>90D</div><div class='value'>{_price(windows['90d']['price_twd_per_kg'])}</div><div class='sub'>{windows['90d']['coverage_days']} 日</div></div></div>"
        + f"<p class='disclaimer'>{DISCLAIM}</p></section>"
        + f"<section class='section'><h2>Buy Score 與產季</h2><div class='grid grid-2'><div class='verdict {'positive' if score['eligible'] else 'neutral'}'><strong>{score['score']} · {_escape(score['verdict_label'])}</strong>{'、'.join(_escape(REASON_LABELS.get(code,code)) for code in score['reason_codes'])}</div>"
        + f"<div class='verdict neutral'><strong>{_escape(season['seasonality_status'])}</strong>主要產地（{_escape(season_source)}）：{_escape('、'.join(season['counties']) or '—')}</div></div></section>"
        + f"<section class='section'><h2>近 120 日價格趨勢</h2>{_sparkline(series['daily'])}<p class='disclaimer'>{DISCLAIM}</p><div class='table-wrap'><table><thead><tr><th>日期</th><th class='num'>價格</th><th class='num'>交易量</th></tr></thead><tbody>{daily_rows}</tbody></table></div></section>"
        + f"<section class='section'><h2>相關產銷履歷</h2><p class='note warn'>{TRACE_WARNING}</p><div class='table-wrap'><table><thead><tr><th>履歷代碼</th><th>組織</th><th>縣市</th><th>驗證</th></tr></thead><tbody>{trace_html}</tbody></table></div></section>"
        + "</main>"
    )


def _trend_page(label, window_name, items, series):
    item_map = {item["canonical_id"]: item for item in items}
    def render_row(row):
        if window_name == "previous":
            reference = row["previous_trading_day"]
            reference_price = reference["price_twd_per_kg"]
            change = reference["change_pct"]
            coverage = 2 if reference["status"] == "valid" else 1
            status = reference["status"]
        else:
            reference = row["windows"][window_name]
            reference_price = reference["price_twd_per_kg"]
            change = reference["today_change_pct"]
            coverage = reference["coverage_days"]
            status = reference["status"]
        return (
            f"<tr><th scope='row'><a href='../produce/{_escape(row['canonical_id'])}.html'>{_escape(item_map[row['canonical_id']]['display_name'])}</a></th>"
            f"<td class='num'>{_price(row['today']['price_twd_per_kg'])}</td>"
            f"<td class='num'>{_price(reference_price)}</td><td class='num'>{_percent(change)}</td>"
            f"<td class='num'>{coverage}</td><td>{_escape(status)}</td></tr>"
        )
    rows = "".join(render_row(row) for row in series)
    return (
        f"<header class='page-hero'><div class='wrap'><div class='eyebrow'>TREND TABLE</div><h1>{_escape(label)}</h1><p>依日曆 window 計算的交易量加權平均。</p></div></header>"
        + _toolbar("../")
        + f"<main id='main' class='wrap'><section class='section'><h2>{_escape(label)}總表</h2><p class='disclaimer'>{DISCLAIM}</p>"
        + "<div class='table-wrap'><table><thead><tr><th>品項</th><th class='num'>今日</th><th class='num'>區間</th><th class='num'>變化</th><th class='num'>有效日</th><th>狀態</th></tr></thead>"
        + f"<tbody>{rows}</tbody></table></div></section></main>"
    )


def _methodology(source_status, quality, publication_status):
    warnings = "".join(f"<li>{_escape(value)}</li>" for value in quality["warnings"]) or "<li>無</li>"
    status_labels = {
        "complete": "行情完整",
        "market_closed": "今日休市",
        "incomplete": "行情尚未完整",
        "pending": "尚無完整行情",
        "source_unavailable": "官方資料暫時無法取得",
    }
    status_label = status_labels[publication_status["status"]]
    return (
        "<header class='page-hero'><div class='wrap'><div class='eyebrow'>METHODOLOGY</div><h1>資料來源、公式與限制</h1></div></header>"
        + _toolbar()
        + "<main id='main' class='wrap'><section class='section'><h2>價格與 rolling windows</h2>"
        + f"<p>{DISCLAIM}</p><p>單日與區間價格皆使用 <code>sum(price × volume) / sum(volume)</code>；日比較採前一個有有效資料的交易日，7／30／90D 依日曆日回看。</p></section>"
        + "<section class='section'><h2>Buy Score</h2><p>產季、7D／30D 相對價、交易量、資料品質與 7D 波動度皆為 deterministic component。產銷履歷不加分，AI 不改變 score 或 verdict。</p></section>"
        + f"<section class='section'><h2>資料狀態</h2><p>行情來源：{_escape(source_status)}</p><p>每日檢查：{_escape(publication_status['requested_date'])} · 最近完整交易日：{_escape(publication_status['resolved_date'])} · 狀態：{_escape(status_label)}</p><ul>{warnings}</ul><p class='note warn'>各資料集會分別標示官方更新、最近驗證資料或內建參考資料，不得把 fallback 解讀為即時官方快照。</p></section></main>"
    )


def build_site(rows, as_of, root, source_status="validated", *, series=None, scores=None, seasonality=None, season_catalog=None, advice=None, traceability=None, quality=None, publication_status=None):
    if not rows:
        raise ValueError("requested as-of date has no valid mapped aggregates")
    series = series or []
    scores = scores or []
    seasonality = seasonality or []
    season_catalog = season_catalog or [
        {
            "schema_version": "1.0", "month": row["month"], "canonical_id": row["canonical_id"],
            "display_name": row["display_name"], "source_display_names": [row["display_name"]],
            "category": row["category"], "counties": row["counties"], "county_count": row["county_count"],
            "district_count": 0, "varieties": [], "variety_count": 0, "source_url": row["source_url"],
            "source_status": row["source_status"], "fetched_at": row["verified_at"],
        }
        for row in seasonality if row["seasonality_status"] == "in_season"
    ]
    traceability = traceability or []
    quality = quality or {"warnings": []}
    publication_status = validate_market_status(publication_status or {
        "schema_version": "1.0", "requested_date": as_of, "resolved_date": as_of,
        "status": "complete", "source_status": source_status,
        "expected_watchlist_count": len(rows), "covered_watchlist_count": len(rows),
        "observed_record_count": len(rows),
    })
    if publication_status.get("resolved_date") != as_of:
        raise ValueError("publication status resolved_date must match site as_of date")
    items = [
        {"canonical_id": row["canonical_id"], "display_name": row["display_name"], "category": row["category"]}
        for row in rows
    ]
    advice = advice or {
        "as_of_date": as_of,
        "headline": "資料基礎已建立",
        "summary": "目前尚無完整 analytics evidence，因此使用 deterministic placeholder。",
        "priority_items": [],
        "watch_items": [],
        "disclaimer": DISCLAIM,
        "generation_mode": "deterministic_fallback",
        "prompt_version": "tpw-advice-v1",
    }
    (root / "assets/css").mkdir(parents=True, exist_ok=True)
    (root / "assets/js").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "daily" / as_of[:4] / as_of[5:7]).mkdir(parents=True, exist_ok=True)
    (root / "archive").mkdir(exist_ok=True)
    (root / "produce").mkdir(exist_ok=True)
    (root / "trends").mkdir(exist_ok=True)
    (root / "season").mkdir(exist_ok=True)
    (root / "traceability").mkdir(exist_ok=True)
    complete = bool(series and scores and seasonality)
    if complete:
        home = _home(items, scores, series, seasonality, advice, traceability, quality, as_of, source_status, publication_status)
    else:
        home = _hero(as_of, source_status, 0, 0, publication_status) + _market_status_notice(publication_status) + "<nav class='toolbar' aria-label='主要導覽'><div class='inner'><a href='archive/index.html'>歷史</a><a href='methodology.html'>方法</a></div></nav>" + "<main id='main' class='wrap'><section class='section' id='recommendations'><h2>今日推薦採買</h2><p>資料不足，暫不判定。</p></section>" + _market_table(rows, "fruit") + _market_table(rows, "vegetable") + "</main>"
    (root / "index.html").write_text(_document("Taiwan Produce Watch", home, "assets/css/app.css", "assets/js/app.js"), encoding="utf-8")
    daily_body = _toolbar("../../../") + f"<main id='main' class='wrap'><section class='section'><h1>每日行情 {as_of}</h1><p class='disclaimer'>{DISCLAIM}</p></section>"
    if complete:
        item_map = {item["canonical_id"]: item for item in items}
        trace_ids = {row["canonical_id"] for row in traceability}
        daily_cards = "".join(_recommendation_card(row, item_map[row["canonical_id"]], "../../../", row["canonical_id"] in trace_ids) for row in [score for score in scores if score["eligible"]][:3])
        daily_body += f"<section class='section' id='recommendations'><h2>Top recommendations</h2><div class='recommendation-grid'>{daily_cards}</div></section>" + _advice_section(advice, items)
    daily_body += _market_table(rows, "fruit") + _market_table(rows, "vegetable") + "</main>"
    (root / "daily" / as_of[:4] / as_of[5:7] / f"{as_of}.html").write_text(_document(f"每日行情 {as_of}", daily_body, "../../../assets/css/app.css", "../../../assets/js/app.js"), encoding="utf-8")
    if complete:
        series_map = {row["canonical_id"]: row for row in series}
        score_map = {row["canonical_id"]: row for row in scores}
        season_map = {row["canonical_id"]: row for row in seasonality}
        for item in items:
            related = [row for row in traceability if row["canonical_id"] == item["canonical_id"]]
            body = _produce_page(item, series_map[item["canonical_id"]], score_map[item["canonical_id"]], season_map[item["canonical_id"]], related)
            (root / "produce" / f"{item['canonical_id']}.html").write_text(_document(f"{item['display_name']}行情", body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        trend_specs = (("daily", "每日與前一交易日", "previous"), ("weekly", "近 7 日趨勢", "7d"), ("monthly", "近 30 日趨勢", "30d"), ("quarterly", "近 90 日趨勢", "90d"))
        for filename, label, window in trend_specs:
            body = _trend_page(label, window, items, series)
            (root / "trends" / f"{filename}.html").write_text(_document(label, body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        season_body = _season_page(season_catalog, series, traceability)
        (root / "season/current.html").write_text(_document("本月當季蔬果", season_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        grouped = {}
        for row in traceability:
            grouped.setdefault(row["canonical_id"], []).append(row)
        trace_cards = "".join(f"<article class='card'><div class='label'>相關紀錄 {len(grouped.get(item['canonical_id'], []))}</div><h3>{_escape(item['display_name'])}</h3><a href='{_escape(item['canonical_id'])}.html'>查看最小化欄位 →</a></article>" for item in items if grouped.get(item["canonical_id"])) or "<p>目前沒有相關紀錄。</p>"
        trace_index = "<header class='page-hero'><div class='wrap'><div class='eyebrow'>TRACEABILITY</div><h1>相關產銷履歷</h1></div></header>" + _toolbar("../") + f"<main id='main' class='wrap'><section class='section'><p class='note warn'>{TRACE_WARNING}</p><div class='grid grid-3'>{trace_cards}</div></section></main>"
        (root / "traceability/index.html").write_text(_document("相關產銷履歷", trace_index, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        for item in items:
            related = grouped.get(item["canonical_id"], [])
            table_rows = "".join(f"<tr><th scope='row'>{_escape(row['tracecode'])}</th><td>{_escape(row['producer'] or '—')}</td><td>{_escape(row['place'] or '—')}</td><td>{_escape(row['pack_date'] or '—')}</td><td>{_escape(row['certification_name'] or '—')}</td></tr>" for row in related) or "<tr><td colspan='5'>目前沒有相關紀錄。</td></tr>"
            trace_body = f"<header class='page-hero'><div class='wrap'><div class='eyebrow'>TRACEABILITY DETAIL</div><h1>{_escape(item['display_name'])}</h1></div></header>" + _toolbar("../") + f"<main id='main' class='wrap'><section class='section'><p class='note warn'>{TRACE_WARNING}</p><div class='table-wrap'><table><thead><tr><th>履歷代碼</th><th>組織</th><th>縣市</th><th>包裝日</th><th>驗證</th></tr></thead><tbody>{table_rows}</tbody></table></div></section></main>"
            (root / "traceability" / f"{item['canonical_id']}.html").write_text(_document(f"{item['display_name']}相關履歷", trace_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
    (root / "methodology.html").write_text(_document("方法說明", _methodology(source_status, quality, publication_status), "assets/css/app.css", "assets/js/app.js"), encoding="utf-8")
    links = "".join(f"<li><a href='../daily/{path.parent.parent.name}/{path.parent.name}/{path.stem}.html'>{path.stem}</a></li>" for path in sorted((root / "daily").rglob("*.html"), reverse=True))
    archive_body = "<header class='page-hero'><div class='wrap'><div class='eyebrow'>ARCHIVE</div><h1>歷史日期</h1></div></header>" + _toolbar("../") + f"<main id='main' class='wrap'><section class='section'><ul class='archive-list'>{links}</ul></section></main>"
    (root / "archive/index.html").write_text(_document("歷史封存", archive_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
    (root / "data/current.json").write_text(json.dumps({"as_of_date": as_of, "source_status": source_status, "publication_status": publication_status, "generation_mode": advice["generation_mode"], "prototype_complete": complete, "eligible_recommendations": len([row for row in scores if row.get("eligible")]), "items": rows, "scores": scores, "seasonality": seasonality, "season_catalog": season_catalog, "advice": advice, "traceability": traceability, "quality": quality}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def render_report(rows, scores, advice, quality, as_of):
    item_map = {row["canonical_id"]: row for row in rows}
    recommendations = [row for row in scores if row["eligible"]][:5]
    watch = [row for row in scores if row["verdict"] in ("hold", "insufficient")][:5]
    def score_lines(selected):
        return "\n".join(f"- {item_map[row['canonical_id']]['display_name']}: {row['score']} / {row['verdict_label']}" for row in selected) or "- —"
    def market_lines(kind):
        return "\n".join(f"- {row['display_name']}: {_price(row['weighted_avg_price_twd_per_kg'])}, {_number(row['total_volume_kg'],0)} kg" for row in rows if row["category"] == kind) or "- —"
    warnings = "\n".join(f"- {value}" for value in quality["warnings"]) or "- 無"
    return (
        f"# 每日行情 {as_of}\n\n{DISCLAIM}\n\n## Top recommendations\n\n{score_lines(recommendations)}\n\n"
        f"## Watch items\n\n{score_lines(watch)}\n\n## 今日採買情報\n\n{advice['headline']}\n\n{advice['summary']}\n\n"
        f"模式：{advice['generation_mode']}\n\n## 水果行情\n\n{market_lines('fruit')}\n\n## 蔬菜行情\n\n{market_lines('vegetable')}\n\n"
        f"## Data quality\n\n{warnings}\n\n## Sources and boundaries\n\n- 農業部農產品交易行情 Dataset 8066\n- 產季來源狀態與履歷資料邊界保存於公開 JSON\n- {TRACE_WARNING}\n\n{DISCLAIM}\n"
    )
