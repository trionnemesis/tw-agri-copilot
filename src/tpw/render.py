import html
import json

from . import __version__
from .categories import category_label, default_category_registry
from .produce_icons import read_produce_icon_sprite, resolve_produce_icon
from .publication import validate_market_status


DISCLAIM = "批發市場平均行情，非實際零售通路售價。"
TRACE_WARNING = "此為同品項的公開產銷履歷紀錄，非本日市場成交來源證明。"
EVENT_WARNING = "H44 市場事件與 7556 履歷批次、8066 批發行情是不同資料集；只作來源情境，不納入行情彙總或 Buy Score。"


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


def _toolbar(prefix="", include_season_map=False):
    links = [
        ("首頁", f"{prefix}index.html"),
        ("當季", f"{prefix}season/current.html"),
    ]
    if include_season_map:
        links.append(("產季地圖", f"{prefix}season/map.html"))
    links.extend((
        ("日趨勢", f"{prefix}trends/daily.html"),
        ("週趨勢", f"{prefix}trends/weekly.html"),
        ("月趨勢", f"{prefix}trends/monthly.html"),
        ("季趨勢", f"{prefix}trends/quarterly.html"),
        ("產銷履歷", f"{prefix}traceability/index.html"),
        ("歷史", f"{prefix}archive/index.html"),
        ("方法", f"{prefix}methodology.html"),
    ))
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
    calendar = status.get("calendar") or {}
    schedule_status = calendar.get("schedule_status", "unknown")
    market_names = "、".join(
        market.get("market_name", market.get("market_code", ""))
        for market in calendar.get("markets", [])
    )
    evidence_link = ""
    document_url = calendar.get("document_url")
    if schedule_status != "unknown" and isinstance(document_url, str) and document_url.startswith("https://www.tapmc.com.tw/"):
        evidence_link = (
            f" <a href='{_escape(document_url)}' rel='noopener noreferrer'>"
            "查看官方休市日程</a>"
        )
    if state == "complete":
        heading = f"行情已更新至 {resolved}"
        expected = status["expected_watchlist_count"]
        message = f"已檢查 {requested} 的官方行情，{expected} 項觀察清單資料完整。"
        if schedule_status == "scheduled_closed":
            message += f" {market_names}同日為官方公告休市（{calendar['reason']}）。"
    elif state == "market_closed":
        if schedule_status == "scheduled_closed":
            heading = f"{requested} {market_names}官方公告休市"
            message = (
                f"{calendar['reason']}；日曆版本 {calendar['calendar_version']}。"
                f"目前沿用最近完整交易日 {resolved}，並非網站漏更新。"
            )
        else:
            heading = f"{requested} 行情來源回報休市"
            message = (
                f"農業部 feed 回報休市，但尚無此年度經驗證的官方日曆 fixture；"
                f"目前沿用最近完整交易日 {resolved}。"
            )
    elif state == "calendar_feed_discrepancy":
        heading = f"{requested} 日曆與行情來源不一致"
        message = (
            f"{market_names}官方日曆為休市，但 feed 出現交易資料；已保留兩方證據，"
            f"不自動丟棄行情，最近完整交易日為 {resolved}。"
        )
    elif state == "incomplete":
        heading = f"{requested} 行情尚未完整"
        message = f"今日資料已檢查，但尚未涵蓋完整觀察清單；目前顯示最近完整交易日 {resolved}。"
        if schedule_status == "scheduled_closed":
            message += f" {market_names}同日為官方公告休市（{calendar['reason']}）。"
    elif state == "pending":
        heading = f"{requested} 尚無完整行情"
        if schedule_status in ("expected_open", "exceptional_open"):
            open_label = "特殊開市" if schedule_status == "exceptional_open" else "預期開市"
            message = (
                f"官方日曆顯示{market_names}{open_label}，但 feed 尚無可發布的完整交易行情；"
                f"不可標示休市，先顯示最近完整交易日 {resolved}。"
            )
        else:
            message = f"今日資料已檢查，目前尚無可發布的完整交易行情；先顯示最近完整交易日 {resolved}。"
    else:
        heading = f"{requested} 官方資料暫時無法取得"
        message = f"系統已完成重試並保留 last-known-good；目前顯示最近完整交易日 {resolved}，不把來源失敗誤標為休市。"
    return (
        f"<aside class='market-status market-status--{_escape(state)}' "
        f"data-market-status='{_escape(state)}' data-calendar-status='{_escape(schedule_status)}' "
        "role='status' aria-live='polite'>"
        f"<div class='wrap'><strong>{_escape(heading)}</strong><span>{_escape(message)}{evidence_link}</span>"
        "</div></aside>"
    )


def _season_source_message(status):
    if status == "live":
        return "清單已由農糧署『農產品產地產期查詢』抓取並完成欄位與分頁驗證。"
    if status == "stale":
        return "本次官方查詢暫時無法取得，清單沿用同月份最近一次通過驗證的資料。"
    return "目前使用專案內建產季參考資料；未涵蓋品項不會直接判定為非當季。"


def _season_source_link(source_url):
    return f" <a href='{_escape(source_url)}'>查看官方來源</a>" if source_url else ""


def _single_season_source_notice(status, source_url):
    note_class = "note warn" if status != "live" else "note"
    return (
        f"<p class='{note_class}' data-season-source='{_escape(status)}'>"
        f"{_escape(_season_source_message(status))}{_season_source_link(source_url)}</p>"
    )


def _season_source_notice(rows, registry=None):
    """One notice per distinct (source_status, source_url) group in rows.

    A homogeneous catalog (today: every watchlist call site, and any build with no extension
    rows) always has exactly one group and renders byte-identically to the single, unlabelled
    notice this used to unconditionally emit. A heterogeneous merged catalog (Issue #44 Part B:
    AFA fruit/vegetable rows at one status, an extension category's rows at another) must not
    describe every row using only the first row's status/source -- that would tell users an
    extension category's stale/fallback data is live AFA data. Groups are ordered by the
    registry rank of the lowest-ranked category in each group, never by comparing source_url text.
    """
    if not rows:
        return _single_season_source_notice("fallback", "")
    groups = {}
    order = []
    for row in rows:
        key = (row.get("source_status", "fallback"), row.get("source_url", ""))
        member = groups.setdefault(key, set())
        if not member:
            order.append(key)
        member.add(row.get("category"))
    if len(groups) == 1:
        return _single_season_source_notice(*order[0])
    registry = registry or default_category_registry()
    registry_rank = {category.id: index for index, category in enumerate(registry.categories)}
    fallback_rank = len(registry_rank)
    def anchor_rank(key):
        return min((registry_rank.get(category_id, fallback_rank) for category_id in groups[key]), default=fallback_rank)
    notices = []
    for key in sorted(order, key=anchor_rank):
        status, source_url = key
        categories_in_group = sorted(groups[key], key=lambda category_id: registry_rank.get(category_id, fallback_rank))
        labels = "、".join(category_label(category_id, registry) for category_id in categories_in_group)
        note_class = "note warn" if status != "live" else "note"
        categories_attr = ",".join(categories_in_group)
        notices.append(
            f"<p class='{note_class}' data-season-source='{_escape(status)}' "
            f"data-season-source-categories='{_escape(categories_attr)}'>"
            f"{_escape(labels)}：{_escape(_season_source_message(status))}{_season_source_link(source_url)}</p>"
        )
    return "".join(notices)


def _traceability_source_notice(profile):
    status = profile.get("source_status", "fixture")
    if status == "live":
        message = "已由農業部 7556 產銷履歷資料集更新，並完成欄位、分頁、去重與隱私最小化驗證。"
    elif status == "stale":
        message = "本次官方資料暫時無法取得，目前沿用最近一次通過驗證的農業部 7556 資料。"
    else:
        message = "目前顯示可重建的示範資料；正式排程會改用農業部 7556，示範筆數不代表全臺覆蓋。"
    source_url = profile.get("source_url", "")
    source = f" <a href='{_escape(source_url)}' rel='noopener noreferrer'>查看官方資料集</a>" if source_url else ""
    note_class = "note" if status == "live" else "note warn"
    return f"<p class='{note_class}' data-traceability-source='{_escape(status)}'>{_escape(message)}{source}</p>"


def _traceability_event_source_notice(profile):
    status = profile.get("source_status", "fixture")
    if status == "live":
        message = "已由農業部 H44 更新，並完成欄位、日期、分頁、去重與數值驗證。"
    elif status == "stale":
        message = "本次 H44 暫時無法取得，目前沿用最近一次通過驗證的同來源市場事件。"
    else:
        message = "目前顯示可重建的 H44 欄位示範資料；示範金額與交易量不是即時行情。"
    source_url = profile.get("source_url", "")
    source = f" <a href='{_escape(source_url)}' rel='noopener noreferrer'>查看官方 H44 資料集</a>" if source_url else ""
    note_class = "note" if status == "live" else "note warn"
    return f"<p class='{note_class}' data-traceability-event-source='{_escape(status)}'>{_escape(message)}{source}</p>"


def _traceability_event_table(rows, colspan=7):
    body = "".join(
        f"<tr><th scope='row'>{_escape(row['transaction_date'])}</th>"
        f"<td>{_escape(row['market_name'])}（{_escape(row['market_code'])}）</td>"
        f"<td>{_escape(row['crop_name_raw'])}（{_escape(row['crop_code'])}）</td>"
        f"<td class='num'>NT$ {_number(row['transaction_amount_twd'],0)}</td>"
        f"<td class='num'>{_number(row['transaction_volume_kg'],1)} kg</td>"
        f"<td>{_escape(row['traceability_class_code'])}</td>"
        f"<td><span class='badge neu'>僅證據</span></td></tr>"
        for row in rows
    ) or f"<tr><td colspan='{colspan}'>目前沒有相符的 H44 市場事件。</td></tr>"
    return (
        "<div class='table-wrap'><table><thead><tr><th>交易日期</th><th>市場</th><th>作物</th>"
        "<th class='num'>交易金額</th><th class='num'>交易量</th><th>溯源代號</th><th>用途</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _season_semantics_section(registry, prefix=""):
    """The 'no official season registry' explainer, shared by the season and map pages.

    Empty when every registered category has an official season registry -- there is
    nothing to explain and nothing to render; today (Issue #44 BC-2 / BC-3) livestock
    and aquaculture always populate this.
    """
    no_official = registry.no_official()
    if not no_official:
        return ""
    cards = "".join(
        f"<div class='card'><h3>{_escape(category.label)}</h3>"
        f"<p>{_escape(category.note)}</p>"
        "<p class='small'><span class='badge neu'>unknown</span> "
        f"<a href='{prefix}methodology.html#season-semantics'>查看方法頁說明 →</a></p></div>"
        for category in no_official
    )
    return (
        "<section class='section' id='season-semantics' data-season-semantics>"
        "<h2>產季語意與類別</h2>"
        "<p class='lead'>以下類別目前沒有官方產地產期登錄；本站一律標示 unknown，不判定當季或非當季。</p>"
        f"<div class='grid grid-2'>{cards}</div></section>"
    )


def _season_page(catalog, series, traceability, include_season_map=False, registry=None):
    registry = registry or default_category_registry()
    market_ids = {row["canonical_id"] for row in series}
    trace_ids = {row["canonical_id"] for row in traceability}
    cards = []
    for row in sorted(catalog, key=lambda value: value["display_name"]):
        icon = resolve_produce_icon(row["category"], row["display_name"], registry)
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
            f"<div class='label'>{_escape(category_label(row['category'], registry))}</div>"
            f"<div class='season-card-title'><svg class='produce-icon produce-icon--{_escape(row['category'])}' "
            f"aria-hidden='true' focusable='false' data-icon-fidelity='{_escape(icon.fidelity)}'>"
            f"<use href='../assets/icons/produce.svg#{_escape(icon.symbol_id)}'></use></svg>"
            f"<h2>{_escape(row['display_name'])}</h2></div>"
            f"<p>{row['county_count']} 個產地縣市 · {row.get('variety_count', 0)} 個品種</p>"
            f"<div class='reasons'><span class='reason'>{'有行情資料' if market_available else '無行情資料'}</span>"
            f"<span class='reason'>{'有相關履歷' if trace_available else '無相關履歷'}</span></div>"
            f"<p class='small'>主要產地：{_escape('、'.join(row['counties']) or '—')}</p>{detail}</article>"
        )
    category_counts = {}
    for row in catalog:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    summary = "、".join(
        f"{_escape(category.label)} {category_counts[category.id]} 項"
        for category in registry.categories
        if category_counts.get(category.id)
    )
    # SPEC section 11.7 pins the fixed all/fruit/vegetable buttons above; every other category
    # (never market_watchlist, by the categories.py registry contract) gets a button only when
    # this month's catalog actually has rows for it.
    extra_filter_buttons = "".join(
        f"<button type='button' data-filter='{_escape(category.id)}' aria-pressed='false'>{_escape(category.label)}</button>"
        for category in registry.categories
        if not category.market_watchlist and category_counts.get(category.id)
    )
    return (
        "<header class='page-hero'><div class='wrap'><div class='eyebrow'>SEASONALITY</div>"
        "<h1>本月當季蔬果</h1><p>農糧署盛產資料 × 行情與履歷狀態</p></div></header>"
        + _toolbar("../", include_season_map)
        + "<main id='main' class='wrap'><section class='section'><div class='section-heading'><div>"
        + f"<h2>完整清單</h2><p class='lead'>共 {len(catalog)} 項：{summary}。</p></div>"
        + "<div class='filter-group' aria-label='當季品項篩選'><button type='button' data-filter='all' aria-pressed='true'>全部</button>"
        + "<button type='button' data-filter='fruit' aria-pressed='false'>水果</button><button type='button' data-filter='vegetable' aria-pressed='false'>蔬菜</button>"
        + extra_filter_buttons
        + "</div></div>"
        + _season_source_notice(catalog, registry)
        + ("<p><a class='card-link' href='map.html'>用產季地圖依縣市查看 →</a></p>" if include_season_map else "")
        + "<div class='season-controls'><label class='season-search' for='season-search'><span>搜尋蔬果名稱</span>"
        + "<input id='season-search' type='search' data-season-search aria-controls='season-grid' "
        + "aria-describedby='season-result-count' autocomplete='off' placeholder='輸入蔬果名稱，例如：甘藍、木瓜'></label>"
        + f"<p class='season-result-count' id='season-result-count' data-season-result-count role='status' aria-live='polite' aria-atomic='true'>顯示 {len(catalog)} 項</p></div>"
        + f"<div class='grid grid-3' id='season-grid' data-season-grid>{''.join(cards)}</div>"
        + "<p class='note warn season-empty' data-season-empty hidden>找不到符合目前搜尋與分類條件的當季蔬果。</p></section>"
        + _season_semantics_section(registry, prefix="../")
        + "</main>"
    )


def _season_map_produce_card(row, registry=None):
    registry = registry or default_category_registry()
    icon = resolve_produce_icon(row["category"], row["display_name"], registry)
    return (
        f"<article class='card season-map-produce-card' data-category='{_escape(row['category'])}'>"
        f"<div class='label'>{_escape(category_label(row['category'], registry))}</div>"
        f"<div class='season-card-title'><svg class='produce-icon produce-icon--{_escape(row['category'])}' "
        f"aria-hidden='true' focusable='false' data-icon-fidelity='{_escape(icon.fidelity)}'>"
        f"<use href='../assets/icons/produce.svg#{_escape(icon.symbol_id)}'></use></svg>"
        f"<h4>{_escape(row['display_name'])}</h4></div></article>"
    )


def _season_map_market_card(row):
    coverage_labels = {
        "observed": "8066 feed 可對應",
        "not_observed": "8066 feed 尚未觀察",
        "unknown": "8066 feed 對應狀態未知",
    }
    coverage = coverage_labels.get(row.get("feed_coverage_status"), "8066 feed 對應狀態未知")
    return (
        "<article class='card official-market-card'>"
        f"<div class='label'>市場代號 {_escape(row['market_code'])}</div>"
        f"<h4>{_escape(row['feed_market_name'])}</h4>"
        f"<p>{_escape(row['official_name'])}</p>"
        f"<span class='badge neu'>{_escape(coverage)}</span>"
        f"<p><a class='card-link' href='{_escape(row['evidence_url'])}' rel='noopener noreferrer'>查看市場官方證據 →</a></p>"
        "</article>"
    )


def _season_map_county_section(county, payload, registry=None):
    registry = registry or default_category_registry()
    produce = county["local_seasonal_produce"]
    markets = county["official_markets"]
    market_cards = "".join(_season_map_market_card(row) for row in markets)
    if not market_cards:
        market_cards = (
            "<p class='note warn county-empty' data-market-empty>"
            "目前專案 registry 尚未收錄此縣市已完成官方證據驗證的果菜批發市場。</p>"
        )
    produce_groups = []
    for category in registry.categories:
        category_produce = [row for row in produce if row["category"] == category.id]
        if not category_produce:
            continue
        produce_groups.append(
            f"<div class='county-produce-group'><h4>{_escape(category.label)}</h4><div class='grid grid-3'>"
            + "".join(_season_map_produce_card(row, registry) for row in category_produce)
            + "</div></div>"
        )
    produce_body = "".join(produce_groups)
    if not produce_body:
        produce_body = (
            f"<p class='note warn county-empty' data-produce-empty>農糧署本月產期資料未列出"
            f"{_escape(county['display_name'])}的水果／蔬菜。</p>"
        )
    no_official = registry.no_official()
    if no_official:
        unknown_labels = "、".join(category.label for category in no_official)
        produce_body += (
            f"<p class='small' data-season-semantics-unknown>{_escape(unknown_labels)}："
            "無官方產地產期登錄，本站不判定當季或非當季（unknown）。</p>"
        )
    seasonality_sources = payload["inputs"]["seasonality_sources"]
    source_spans = "、".join(
        f"<span data-season-source='{_escape(entry['source_status'])}'>{_escape(category.label)}：{_escape(entry['source_status'])}</span>"
        for category in registry.categories
        for entry in [seasonality_sources.get(category.id)]
        if entry is not None
    )
    return (
        f"<section class='section county-detail' id='county-{_escape(county['slug'])}' "
        f"data-county-section='{_escape(county['slug'])}' data-county-name='{_escape(county['display_name'])}' "
        f"data-market-count='{len(markets)}' data-produce-count='{len(produce)}' "
        f"aria-labelledby='county-{_escape(county['slug'])}-heading'>"
        "<div class='section-heading'><div>"
        f"<div class='eyebrow ink'>COUNTY SEASONALITY</div><h2 id='county-{_escape(county['slug'])}-heading' "
        f"data-county-heading tabindex='-1'>{_escape(county['display_name'])}</h2>"
        f"<p class='lead'>{_escape(payload['as_of_month'])} 官方產期資料</p></div>"
        f"<span class='badge info'>本月列出 {len(produce)} 項</span></div>"
        f"<p class='small county-source-status'>產期來源狀態：{source_spans} · "
        f"行情最近完整交易日：{_escape(payload['resolved_market_date'])}</p>"
        "<p class='note warn semantic-warning'>「產地產期」與「批發市場成交」是不同資料語意。"
        "市場位於該縣市，不代表成交品項產自該縣市。</p>"
        "<section class='county-detail-block' aria-labelledby='county-"
        f"{_escape(county['slug'])}-markets'><h3 id='county-{_escape(county['slug'])}-markets'>官方果菜批發市場</h3>"
        "<p class='small'>只列逐筆保存官方證據的市場 metadata；不代表 registry 已涵蓋該縣市所有市場，也不代表當日有成交資料。</p>"
        f"<div class='grid grid-2 county-market-grid'>{market_cards}</div></section>"
        "<section class='county-detail-block' aria-labelledby='county-"
        f"{_escape(county['slug'])}-produce'><h3 id='county-{_escape(county['slug'])}-produce'>本月當地盛產</h3>"
        "<p class='small'>只依農糧署月份 catalog 的縣市 exact match 列出；項目數不是產量、面積或市場供應量。</p>"
        f"{produce_body}</section></section>"
    )


def _season_map_page(payload, county_svg, catalog, registry=None):
    registry = registry or default_category_registry()
    counties = payload["counties"]
    options = "".join(
        f"<option value='{_escape(county['slug'])}'>{_escape(county['display_name'])}</option>"
        for county in counties
    )
    sections = "".join(_season_map_county_section(county, payload, registry) for county in counties)
    degraded = ""
    if payload.get("unmapped_source_counties"):
        degraded = (
            "<p class='note warn' data-map-degraded>產期來源含有尚未建立 exact registry mapping 的縣市："
            + _escape("、".join(payload["unmapped_source_counties"]))
            + "。地圖不補猜；完整月份清單仍保留在當季頁。</p>"
        )
    no_official = registry.no_official()
    semantics_notice = ""
    if no_official:
        unknown_labels = "、".join(category.label for category in no_official)
        semantics_notice = (
            f"<p class='note warn' data-season-semantics-notice>{_escape(unknown_labels)}"
            "目前沒有官方產地產期登錄；地圖上這些類別一律標示 unknown，不判定當季或非當季。"
            " <a href='../methodology.html#season-semantics'>查看方法頁說明 →</a></p>"
        )
    return (
        "<header class='page-hero'><div class='wrap'><div class='eyebrow'>COUNTY SEASON MAP</div>"
        "<h1>臺灣產季地圖</h1><p>官方縣市產期 × 已驗證果菜批發市場</p></div></header>"
        + _toolbar("../", True)
        + "<main id='main' class='wrap'><section class='section season-map-intro'><div class='section-heading'><div>"
        + f"<h2>{_escape(payload['as_of_month'])} 縣市導覽</h2>"
        + "<p class='lead'>點選地圖、使用鍵盤或從下拉選單選擇縣市。滑鼠 hover 只提供提示，不會提交選取。</p></div>"
        + f"<span class='badge info'>22 縣市</span></div>{_season_source_notice(catalog, registry)}"
        + semantics_notice
        + "<p class='note warn semantic-warning'>「產地產期」與「批發市場成交」是不同資料語意。"
        + "市場位於該縣市，不代表成交品項產自該縣市。</p>"
        + "<p class='small map-attribution'>資料來源：內政部國土測繪中心 2025「"
        + "<a href='https://data.gov.tw/dataset/7442' rel='noopener noreferrer'>直轄市、縣市界線（TWD97經緯度；COUNTY_MOI_1140318）</a>」；"
        + "依<a href='https://data.gov.tw/license' rel='noopener noreferrer'>政府資料開放授權條款第1版</a>使用。"
        + "本 SVG 為簡化及 inset 排版衍生物。</p>"
        + degraded
        + "</section><div class='season-map-layout' data-season-map-root>"
        + "<section class='section season-map-map-panel' aria-labelledby='map-picker-heading'><h2 id='map-picker-heading'>選擇縣市</h2>"
        + "<label class='county-select-label' for='county-select'><span>縣市</span>"
        + f"<select id='county-select' data-county-select><option value=''>尚未選取</option>{options}</select></label>"
        + "<div class='taiwan-map' data-county-map>" + county_svg + "</div>"
        + "<noscript><p class='note'>JavaScript 未啟用時，仍可用地圖連結跳到下方 22 個縣市資料。</p></noscript></section>"
        + "<div class='season-map-results'><p class='note county-unselected' data-county-unselected hidden>"
        + "尚未選取縣市。請使用地圖或縣市選單查看資料。</p>"
        + "<p class='sr-only' data-county-live role='status' aria-live='polite' aria-atomic='true'>尚未選取縣市</p>"
        + f"<div data-county-details>{sections}</div></div></div></main>"
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


def _recommendation_card(score, item, prefix="", trace_available=False, registry=None):
    registry = registry or default_category_registry()
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
        f"<div><span class='badge info'>{_escape(category_label(item['category'], registry))}</span> "
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


def _market_table(rows, kind, heading=None, registry=None):
    registry = registry or default_category_registry()
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
    title = heading or (category_label(kind, registry) + "行情")
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


def _home(items, scores, series, seasonality, advice, traceability, traceability_status, traceability_events, traceability_event_status, quality, as_of, source_status, publication_status, include_season_map=False, registry=None):
    registry = registry or default_category_registry()
    item_map = {item["canonical_id"]: item for item in items}
    series_map = {row["canonical_id"]: row for row in series}
    trace_ids = {row["canonical_id"] for row in traceability if row.get("certification_status") == "active"}
    in_season = [row for row in seasonality if row["seasonality_status"] == "in_season"]
    recommendations = [row for row in scores if row["eligible"]][:6]
    cards = "".join(
        _recommendation_card(row, item_map[row["canonical_id"]], trace_available=row["canonical_id"] in trace_ids, registry=registry)
        for row in recommendations
    ) or "<div class='note warn'>資料覆蓋率或品質 gate 尚未通過，本期不產生正向推薦。</div>"
    season_cards = "".join(
        f"<article class='card season-card' data-category='{_escape(row['category'])}'>"
        f"<div class='label'>{_escape(category_label(row['category'], registry))}</div>"
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
        + _toolbar(include_season_map=include_season_map)
        + "<main id='main' class='wrap'>"
        + "<section class='section recommendations' id='recommendations'><div class='section-heading'><div>"
        + "<div class='eyebrow ink'>BUY SCORE · EVIDENCE FIRST</div><h2>今日推薦採買</h2></div>"
        + f"<span class='badge info'>{len(recommendations)} 項通過 gate</span></div>"
        + f"<p class='disclaimer'>{DISCLAIM}</p><div class='recommendation-grid'>{cards}</div></section>"
        + _advice_section(advice, items)
        + "<section class='section' id='season'><div class='section-heading'><div><div class='eyebrow ink'>SEASONALITY</div><h2>本月當季蔬果</h2></div>"
        + "<div class='filter-group' aria-label='當季品項篩選'><button type='button' data-filter='all' aria-pressed='true'>全部</button><button type='button' data-filter='fruit' aria-pressed='false'>水果</button><button type='button' data-filter='vegetable' aria-pressed='false'>蔬菜</button></div></div>"
        + _season_source_notice(seasonality, registry)
        + f"<div class='grid grid-3' data-season-grid>{season_cards}</div><p><a href='season/current.html'>查看完整當季清單 →</a></p></section>"
        + "<section class='section' id='movers'><h2>今日變便宜／今日變貴</h2><p class='lead'>以各品項前一個有效交易日為基準。</p>"
        + f"<div class='grid grid-2'><div class='verdict positive'><strong>今天變便宜</strong><ul class='mover-list'>{mover_list(cheaper)}</ul></div>"
        + f"<div class='verdict negative'><strong>今天變貴</strong><ul class='mover-list'>{mover_list(pricier)}</ul></div></div></section>"
        + "<section class='section' id='trends'><div class='section-heading'><div><div class='eyebrow ink'>ROLLING ANALYTICS</div><h2>日／週／月／季趨勢</h2></div>"
        + "<div class='tabs'><a href='trends/daily.html'>日</a><a href='trends/weekly.html'>週</a><a href='trends/monthly.html'>月</a><a href='trends/quarterly.html'>季</a></div></div>"
        + f"<div class='grid grid-4'>{trend_cards}</div></section>"
        + "<section class='section' id='origins'><h2>產地／產銷履歷入口</h2>"
        + f"<div class='grid grid-3'><div class='note'><strong>當季主要產地</strong><p>{len(in_season)} 項行情觀察品項具當季資料；產地只作季節背景，不代表當日成交來源。</p><a href='season/current.html'>查看當季與產地 →</a></div>"
        + f"<div class='note warn'><strong>7556 相關產銷履歷</strong><p>{traceability_status.get('active_record_count', 0)} 筆有效履歷批次、{traceability_status.get('operator_count', 0)} 個驗證經營者。{TRACE_WARNING}</p><a href='traceability/index.html'>查看履歷邊界 →</a></div>"
        + f"<div class='note warn'><strong>H44 市場事件</strong><p>{len(traceability_events)} 筆獨立市場事件、{traceability_event_status.get('market_count', 0)} 個市場。{EVENT_WARNING}</p><a href='traceability/market-events.html'>查看事件證據 →</a></div></div></section>"
        + "<section class='section' id='history'><h2>歷史紀錄</h2><p>每日 HTML、Markdown 與 machine-readable JSON 都保留在 repo 中。</p><a href='archive/index.html'>開啟日期封存 →</a></section>"
        + "<section class='section sources' id='sources'><h2>資料來源、方法與限制</h2>"
        + f"<p class='disclaimer'>{DISCLAIM}</p><p>行情以各市場交易量加權；推薦由 deterministic Buy Score 產生，AI 只能解釋，不能改變數值或 verdict。</p>"
        + f"<p class='small'>資料狀態：{_escape(source_status)} · 品質警示：{_escape(warning_text)}</p><a href='methodology.html'>閱讀完整方法 →</a></section>"
        + f"</main><footer class='footer'>Taiwan Produce Watch · side-project prototype · v{__version__}</footer>"
    )


def _produce_page(item, series, score, season, trace_rows, traceability_events, include_season_map=False, registry=None):
    registry = registry or default_category_registry()
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
        f"<h1>{_escape(item['display_name'])}</h1><p>{_escape(category_label(item['category'], registry))} · {_escape(score['verdict_label'])}</p></div></header>"
        + _toolbar("../", include_season_map)
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
        + f"<section class='section'><h2>H44 市場事件</h2><p class='note warn'>{EVENT_WARNING}</p><p class='disclaimer'>{DISCLAIM}</p>{_traceability_event_table(traceability_events)}</section>"
        + "</main>"
    )


def _trend_page(label, window_name, items, series, include_season_map=False):
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
        + _toolbar("../", include_season_map)
        + f"<main id='main' class='wrap'><section class='section'><h2>{_escape(label)}總表</h2><p class='disclaimer'>{DISCLAIM}</p>"
        + "<div class='table-wrap'><table><thead><tr><th>品項</th><th class='num'>今日</th><th class='num'>區間</th><th class='num'>變化</th><th class='num'>有效日</th><th>狀態</th></tr></thead>"
        + f"<tbody>{rows}</tbody></table></div></section></main>"
    )


def _category_semantics_row(category):
    semantics_label = "有官方登錄" if category.season_semantics == "official_season_registry" else "無官方登錄"
    if category.season_source:
        source_cell = f"<a href='{_escape(category.season_source['source_url'])}' rel='noopener noreferrer'>查看來源 →</a>"
    else:
        source_cell = "—"
    return (
        "<tr>"
        f"<th scope='row'>{_escape(category.label)}</th>"
        f"<td>{_escape(semantics_label)}</td>"
        f"<td>{source_cell}</td>"
        f"<td>{_escape(category.note)}</td>"
        "</tr>"
    )


def _methodology(source_status, quality, publication_status, include_season_map=False, registry=None):
    registry = registry or default_category_registry()
    warnings = "".join(f"<li>{_escape(value)}</li>" for value in quality["warnings"]) or "<li>無</li>"
    status_labels = {
        "complete": "行情完整",
        "market_closed": "今日休市",
        "incomplete": "行情尚未完整",
        "pending": "尚無完整行情",
        "source_unavailable": "官方資料暫時無法取得",
        "calendar_feed_discrepancy": "日曆與行情來源不一致",
    }
    status_label = status_labels[publication_status["status"]]
    calendar = publication_status.get("calendar") or {}
    if not calendar or calendar.get("schedule_status") == "unknown":
        calendar_line = "<p>市場日曆：unknown（不宣稱官方休市）</p>"
    else:
        market_names = "、".join(market["market_name"] for market in calendar["markets"])
        calendar_line = (
            f"<p>市場日曆：{_escape(market_names)} · {_escape(calendar['calendar_date'])} · "
            f"{_escape(calendar['schedule_status'])} · 版本 {_escape(calendar['calendar_version'])} · "
            f"<a href='{_escape(calendar['document_url'])}' rel='noopener noreferrer'>官方來源</a></p>"
        )
    map_section = (
        "<section class='section'><h2>產季地圖來源與語意</h2>"
        "<p>資料來源：內政部國土測繪中心 2025「"
        "<a href='https://data.gov.tw/dataset/7442' rel='noopener noreferrer'>直轄市、縣市界線（TWD97經緯度；COUNTY_MOI_1140318）</a>」；"
        "依<a href='https://data.gov.tw/license' rel='noopener noreferrer'>政府資料開放授權條款第1版</a>使用。"
        "本 SVG 為 build-time 簡化及 inset 排版衍生物，並隨站點發布；瀏覽器不載入外部地圖服務。</p>"
        "<p>縣市盛產品項只依農糧署月份 catalog 的縣市 exact match；官方果菜批發市場只來自逐筆保存第一方證據的 verified-entries-only registry。"
        " <a href='https://www.afa.gov.tw/cht/index.php?code=list&amp;ids=1103' rel='noopener noreferrer'>查看官方產期來源</a> · "
        "<a href='https://www.tapmc.com.tw/Pages/ContactUs' rel='noopener noreferrer'>查看臺北市場官方證據</a></p>"
        "<p class='note warn'>「產地產期」與「批發市場成交」是不同資料語意。市場位於該縣市，不代表成交品項產自該縣市；地圖上的品項數也不是產量、面積或供應量。</p></section>"
        if include_season_map else ""
    )
    category_section = (
        "<section class='section' id='season-semantics'><h2>產季語意與類別</h2>"
        "<p>每個蔬果類別都登錄於 config/produce-categories.json；沒有官方產期登錄的類別，"
        "當季頁與產季地圖一律標示 unknown，不判定當季或非當季。</p>"
        "<div class='table-wrap'><table><thead><tr><th>類別</th><th>語意</th><th>來源</th><th>說明</th></tr></thead>"
        f"<tbody>{''.join(_category_semantics_row(category) for category in registry.categories)}</tbody></table></div></section>"
    )
    return (
        "<header class='page-hero'><div class='wrap'><div class='eyebrow'>METHODOLOGY</div><h1>資料來源、公式與限制</h1></div></header>"
        + _toolbar(include_season_map=include_season_map)
        + "<main id='main' class='wrap'><section class='section'><h2>價格與 rolling windows</h2>"
        + f"<p>{DISCLAIM}</p><p>單日與區間價格皆使用 <code>sum(price × volume) / sum(volume)</code>；日比較採前一個有有效資料的交易日，7／30／90D 依日曆日回看。</p></section>"
        + "<section class='section'><h2>Buy Score</h2><p>產季、7D／30D 相對價、交易量、資料品質與 7D 波動度皆為 deterministic component。7556 產銷履歷與 H44 市場事件都不加分，AI 不改變 score 或 verdict。</p><p>H44 的交易金額與交易量只保留在獨立事件層，不與 8066 行情合併，也不由溯源代號推論 7556 履歷批次。</p></section>"
        + f"<section class='section'><h2>資料狀態</h2><p>行情來源：{_escape(source_status)}</p><p>每日檢查：{_escape(publication_status['requested_date'])} · 最近完整交易日：{_escape(publication_status['resolved_date'])} · 狀態：{_escape(status_label)} · 全體 feed：{_escape(publication_status.get('feed_status', 'not_checked'))} · 日曆市場 feed：{_escape(publication_status.get('calendar_feed_status', 'not_checked'))}</p>{calendar_line}<ul>{warnings}</ul><p class='note warn'>各資料集會分別標示官方更新、最近驗證資料或內建參考資料，不得把 fallback 解讀為即時官方快照。</p></section>"
        + category_section
        + map_section + "</main>"
    )


def build_site(rows, as_of, root, source_status="validated", *, series=None, scores=None, seasonality=None, season_catalog=None, advice=None, traceability=None, traceability_status=None, traceability_events=None, traceability_event_status=None, quality=None, publication_status=None, season_map_payload=None, county_svg=None, category_registry=None):
    if not rows:
        raise ValueError("requested as-of date has no valid mapped aggregates")
    # tpw.cli always passes an explicit category_registry (loaded once per command from its
    # own ROOT); the default here only serves callers with no root to load one from, such as
    # legacy direct-call tests that build a page from hand-written rows.
    registry = category_registry or default_category_registry()
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
    traceability_status = traceability_status or {
        "source_status": "fixture",
        "source_url": "",
        "as_of_date": as_of,
        "retrieved_at": "fixture",
        "active_record_count": sum(row.get("certification_status") == "active" for row in traceability),
        "published_record_count": len(traceability),
        "operator_count": len({row.get("org_id") for row in traceability if row.get("org_id")}),
        "mapped_item_count": len({row.get("canonical_id") for row in traceability}),
    }
    traceability_events = traceability_events or []
    traceability_event_status = traceability_event_status or {
        "source_status": "fixture",
        "source_url": "",
        "requested_date": as_of,
        "retrieved_at": "fixture",
        "published_record_count": len(traceability_events),
        "mapped_item_count": len({row.get("canonical_id") for row in traceability_events}),
        "market_count": len({row.get("market_code") for row in traceability_events}),
        "eligible_for_market_aggregate": False,
        "affects_buy_score": False,
    }
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
    (root / "assets/icons").mkdir(parents=True, exist_ok=True)
    (root / "assets/icons/produce.svg").write_bytes(read_produce_icon_sprite(registry=registry))
    (root / "data").mkdir(exist_ok=True)
    if (season_map_payload is None) != (county_svg is None):
        raise ValueError("season map payload and county SVG must be provided together")
    (root / "daily" / as_of[:4] / as_of[5:7]).mkdir(parents=True, exist_ok=True)
    (root / "archive").mkdir(exist_ok=True)
    (root / "produce").mkdir(exist_ok=True)
    (root / "trends").mkdir(exist_ok=True)
    (root / "season").mkdir(exist_ok=True)
    (root / "traceability").mkdir(exist_ok=True)
    complete = bool(series and scores and seasonality)
    include_season_map = season_map_payload is not None
    if complete:
        home = _home(items, scores, series, seasonality, advice, traceability, traceability_status, traceability_events, traceability_event_status, quality, as_of, source_status, publication_status, include_season_map, registry)
    else:
        home = _hero(as_of, source_status, 0, 0, publication_status) + _market_status_notice(publication_status) + "<nav class='toolbar' aria-label='主要導覽'><div class='inner'><a href='archive/index.html'>歷史</a><a href='methodology.html'>方法</a></div></nav>" + "<main id='main' class='wrap'><section class='section' id='recommendations'><h2>今日推薦採買</h2><p>資料不足，暫不判定。</p></section>" + _market_table(rows, "fruit", registry=registry) + _market_table(rows, "vegetable", registry=registry) + "</main>"
    (root / "index.html").write_text(_document("Taiwan Produce Watch", home, "assets/css/app.css", "assets/js/app.js"), encoding="utf-8")
    daily_body = _toolbar("../../../", include_season_map) + f"<main id='main' class='wrap'><section class='section'><h1>每日行情 {as_of}</h1><p class='disclaimer'>{DISCLAIM}</p></section>"
    if complete:
        item_map = {item["canonical_id"]: item for item in items}
        trace_ids = {row["canonical_id"] for row in traceability if row.get("certification_status") == "active"}
        daily_cards = "".join(_recommendation_card(row, item_map[row["canonical_id"]], "../../../", row["canonical_id"] in trace_ids, registry) for row in [score for score in scores if score["eligible"]][:3])
        daily_body += f"<section class='section' id='recommendations'><h2>Top recommendations</h2><div class='recommendation-grid'>{daily_cards}</div></section>" + _advice_section(advice, items)
    daily_body += _market_table(rows, "fruit", registry=registry) + _market_table(rows, "vegetable", registry=registry) + "</main>"
    (root / "daily" / as_of[:4] / as_of[5:7] / f"{as_of}.html").write_text(_document(f"每日行情 {as_of}", daily_body, "../../../assets/css/app.css", "../../../assets/js/app.js"), encoding="utf-8")
    if complete:
        series_map = {row["canonical_id"]: row for row in series}
        score_map = {row["canonical_id"]: row for row in scores}
        season_map = {row["canonical_id"]: row for row in seasonality}
        for item in items:
            related = [row for row in traceability if row["canonical_id"] == item["canonical_id"]]
            related_events = [row for row in traceability_events if row["canonical_id"] == item["canonical_id"]]
            body = _produce_page(item, series_map[item["canonical_id"]], score_map[item["canonical_id"]], season_map[item["canonical_id"]], related, related_events, include_season_map, registry)
            (root / "produce" / f"{item['canonical_id']}.html").write_text(_document(f"{item['display_name']}行情", body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        trend_specs = (("daily", "每日與前一交易日", "previous"), ("weekly", "近 7 日趨勢", "7d"), ("monthly", "近 30 日趨勢", "30d"), ("quarterly", "近 90 日趨勢", "90d"))
        for filename, label, window in trend_specs:
            body = _trend_page(label, window, items, series, include_season_map)
            (root / "trends" / f"{filename}.html").write_text(_document(label, body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        season_body = _season_page(season_catalog, series, traceability, include_season_map, registry)
        (root / "season/current.html").write_text(_document("本月當季蔬果", season_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        if season_map_payload is not None:
            svg_text = county_svg.decode("utf-8") if isinstance(county_svg, bytes) else str(county_svg)
            map_body = _season_map_page(season_map_payload, svg_text, season_catalog, registry)
            (root / "season/map.html").write_text(_document("臺灣產季地圖", map_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
            (root / "data/season-map").mkdir(parents=True, exist_ok=True)
            (root / "data/season-map/current.json").write_text(
                json.dumps(season_map_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
        grouped = {}
        for row in traceability:
            grouped.setdefault(row["canonical_id"], []).append(row)
        event_grouped = {}
        for row in traceability_events:
            event_grouped.setdefault(row["canonical_id"], []).append(row)
        trace_cards = "".join(f"<article class='card'><div class='label'>有效履歷批次 {len([row for row in grouped.get(item['canonical_id'], []) if row.get('certification_status')=='active'])}</div><h3>{_escape(item['display_name'])}</h3><a href='{_escape(item['canonical_id'])}.html'>查看最小化欄位 →</a></article>" for item in items if grouped.get(item["canonical_id"])) or "<p>目前沒有相關紀錄。</p>"
        trace_summary = f"<div class='grid grid-3'><div class='card'><div class='label'>有效履歷批次</div><div class='value'>{traceability_status.get('active_record_count',0)}</div></div><div class='card'><div class='label'>驗證經營者</div><div class='value'>{traceability_status.get('operator_count',0)}</div></div><div class='card'><div class='label'>涵蓋觀察品項</div><div class='value'>{traceability_status.get('mapped_item_count',0)}</div></div></div>"
        trace_index = "<header class='page-hero'><div class='wrap'><div class='eyebrow'>TRACEABILITY</div><h1>相關產銷履歷</h1><p>官方驗證資格與批次，不與每日批發行情混算</p></div></header>" + _toolbar("../", include_season_map) + f"<main id='main' class='wrap'><section class='section'><p class='note warn'>{TRACE_WARNING}</p>{_traceability_source_notice(traceability_status)}{trace_summary}<p class='small'>資料基準日：{_escape(traceability_status.get('as_of_date','—'))} · 來源擷取：{_escape(traceability_status.get('retrieved_at','—'))}</p><p><a href='market-events.html'>另看 H44 獨立市場事件 →</a></p><div class='grid grid-3'>{trace_cards}</div></section></main>"
        (root / "traceability/index.html").write_text(_document("相關產銷履歷", trace_index, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        event_cards = "".join(
            f"<article class='card'><div class='label'>H44 市場事件 {len(event_grouped.get(item['canonical_id'], []))}</div>"
            f"<h3>{_escape(item['display_name'])}</h3><a href='{_escape(item['canonical_id'])}.html'>分開查看履歷與事件 →</a></article>"
            for item in items if event_grouped.get(item["canonical_id"])
        ) or "<p>目前沒有相符的 H44 市場事件。</p>"
        event_summary = f"<div class='grid grid-3'><div class='card'><div class='label'>市場事件</div><div class='value'>{traceability_event_status.get('published_record_count',len(traceability_events))}</div></div><div class='card'><div class='label'>市場數</div><div class='value'>{traceability_event_status.get('market_count',0)}</div></div><div class='card'><div class='label'>涵蓋觀察品項</div><div class='value'>{traceability_event_status.get('mapped_item_count',0)}</div></div></div>"
        event_body = "<header class='page-hero'><div class='wrap'><div class='eyebrow'>H44 MARKET EVENTS</div><h1>可溯源市場交易事件</h1><p>日期／市場事件證據，與 registry lot 及 8066 行情分層</p></div></header>" + _toolbar("../", include_season_map) + f"<main id='main' class='wrap'><section class='section'><p class='note warn'>{EVENT_WARNING}</p><p class='disclaimer'>{DISCLAIM}</p>{_traceability_event_source_notice(traceability_event_status)}{event_summary}<p class='small'>事件日期：{_escape(traceability_event_status.get('requested_date','—'))} · 來源擷取：{_escape(traceability_event_status.get('retrieved_at','—'))}</p>{_traceability_event_table(traceability_events)}<h2>依觀察品項</h2><div class='grid grid-3'>{event_cards}</div></section></main>"
        (root / "traceability/market-events.html").write_text(_document("H44 可溯源市場交易事件", event_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
        for item in items:
            related = grouped.get(item["canonical_id"], [])
            table_rows = "".join(f"<tr><th scope='row'>{_escape(row['tracecode'])}</th><td>{_escape(row['producer'] or '—')}</td><td>{_escape(row['place'] or '—')}</td><td>{_escape(row['pack_date'] or '—')}</td><td>{_escape(row['certification_name'] or '—')}</td><td>{_escape(row['valid_date'] or '—')}</td><td><span class='badge {'pos' if row.get('certification_status')=='active' else 'neg' if row.get('certification_status')=='expired' else 'neu'}'>{_escape({'active':'有效','expired':'已到期','unknown':'未提供有效日'}.get(row.get('certification_status'),'未知'))}</span></td></tr>" for row in related) or "<tr><td colspan='7'>目前沒有相關紀錄。</td></tr>"
            related_events = event_grouped.get(item["canonical_id"], [])
            trace_body = f"<header class='page-hero'><div class='wrap'><div class='eyebrow'>TRACEABILITY DETAIL</div><h1>{_escape(item['display_name'])}</h1></div></header>" + _toolbar("../", include_season_map) + f"<main id='main' class='wrap'><section class='section'><h2>7556 履歷批次</h2><p class='note warn'>{TRACE_WARNING}</p>{_traceability_source_notice(traceability_status)}<div class='table-wrap'><table><thead><tr><th>履歷代碼</th><th>組織</th><th>縣市</th><th>包裝日</th><th>驗證機構</th><th>有效至</th><th>狀態</th></tr></thead><tbody>{table_rows}</tbody></table></div></section><section class='section'><h2>H44 市場事件</h2><p class='note warn'>{EVENT_WARNING}</p><p class='disclaimer'>{DISCLAIM}</p>{_traceability_event_source_notice(traceability_event_status)}{_traceability_event_table(related_events)}</section></main>"
            (root / "traceability" / f"{item['canonical_id']}.html").write_text(_document(f"{item['display_name']}相關履歷", trace_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
    (root / "methodology.html").write_text(_document("方法說明", _methodology(source_status, quality, publication_status, include_season_map, registry), "assets/css/app.css", "assets/js/app.js"), encoding="utf-8")
    links = "".join(f"<li><a href='../daily/{path.parent.parent.name}/{path.parent.name}/{path.stem}.html'>{path.stem}</a></li>" for path in sorted((root / "daily").rglob("*.html"), reverse=True))
    archive_body = "<header class='page-hero'><div class='wrap'><div class='eyebrow'>ARCHIVE</div><h1>歷史日期</h1></div></header>" + _toolbar("../", include_season_map) + f"<main id='main' class='wrap'><section class='section'><ul class='archive-list'>{links}</ul></section></main>"
    (root / "archive/index.html").write_text(_document("歷史封存", archive_body, "../assets/css/app.css", "../assets/js/app.js"), encoding="utf-8")
    (root / "data/current.json").write_text(json.dumps({"as_of_date": as_of, "source_status": source_status, "publication_status": publication_status, "generation_mode": advice["generation_mode"], "prototype_complete": complete, "eligible_recommendations": len([row for row in scores if row.get("eligible")]), "items": rows, "scores": scores, "seasonality": seasonality, "season_catalog": season_catalog, "advice": advice, "traceability": traceability, "traceability_status": traceability_status, "traceability_events": traceability_events, "traceability_event_status": traceability_event_status, "quality": quality}, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def render_report(rows, scores, advice, quality, as_of, registry=None):
    registry = registry or default_category_registry()
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
        f"模式：{advice['generation_mode']}\n\n## {category_label('fruit', registry)}行情\n\n{market_lines('fruit')}\n\n## {category_label('vegetable', registry)}行情\n\n{market_lines('vegetable')}\n\n"
        f"## Data quality\n\n{warnings}\n\n## Sources and boundaries\n\n- 農業部農產品交易行情 Dataset 8066\n- 產季來源狀態與履歷資料邊界保存於公開 JSON\n- {TRACE_WARNING}\n\n{DISCLAIM}\n"
    )
