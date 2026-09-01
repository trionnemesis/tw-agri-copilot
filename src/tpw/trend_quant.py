import datetime as dt
import html
import json
import math
import pathlib
import re


STYLE_ATTR = "data-trend-quant-style='v1'"
PRICE_TREND_CSS = """
/* quantitative-price-trends-v1 */
.trend-quant-summary .grid{margin-top:12px}.trend-quant-summary .card{padding:13px}.trend-quant-summary .value{font-size:1.08rem}.trend-quant-summary .sub{margin-top:4px}.quantitative-chart{height:auto;min-height:300px;overflow-x:auto;padding:10px}.quantitative-chart svg{display:block;width:100%;min-width:640px;height:auto;aspect-ratio:760/280}.chart-grid{stroke:#e1e8f0;stroke-width:1}.chart-axis{stroke:#9ba9ba;stroke-width:1.2}.chart-line{fill:none;stroke:var(--blue);stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.chart-ref{stroke-width:1.5;stroke-dasharray:6 5}.chart-ref-7d{stroke:var(--green)}.chart-ref-30d{stroke:var(--amber)}.chart-point{stroke:#fff;stroke-width:2}.chart-point-latest{fill:var(--blue)}.chart-point-high{fill:var(--red)}.chart-point-low{fill:var(--green)}.chart-tick,.chart-label,.chart-ref-label{fill:#53647a;font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif;font-size:11px}.chart-label{font-weight:800;fill:#26364b}.chart-ref-label{font-weight:750}.chart-label,.chart-ref-label{paint-order:stroke;stroke:var(--surface,#f7f9fc);stroke-width:3px;stroke-linejoin:round}.trend-chart-note{margin:.55rem 0 0;color:var(--muted);font-size:.82rem}.trend-stat-insufficient{color:var(--amber);font-weight:800}@media(max-width:620px){.quantitative-chart{margin-inline:-4px}.trend-quant-summary .grid-4{grid-template-columns:1fr 1fr}}@media print{.quantitative-chart{overflow:visible}.quantitative-chart svg{min-width:0}.trend-quant-summary .card{break-inside:avoid}}
"""


def _number(value, digits=1):
    return "—" if value is None else f"{value:,.{digits}f}"


def _price(value):
    return "—" if value is None else f"NT$ {value:,.2f}/kg"


def _percent(value):
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _volatility(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def _status_label(value):
    return "資料完整" if value == "valid" else "資料不足"


def _metric_card(label, value, sub=""):
    sub_html = f"<div class='sub'>{html.escape(str(sub))}</div>" if sub else ""
    return (
        "<div class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>{sub_html}</div>"
    )


def _summary_html(series):
    windows = series["windows"]
    previous = series["previous_trading_day"]
    cards = [
        _metric_card("最新價", _price(series["today"]["price_twd_per_kg"]), series["as_of_date"]),
        _metric_card(
            "前一交易日",
            _percent(previous["change_pct"]),
            previous["date"] or _status_label(previous["status"]),
        ),
        _metric_card(
            "相對 7D",
            _percent(windows["7d"]["today_change_pct"]),
            f"均價 {_price(windows['7d']['price_twd_per_kg'])}",
        ),
        _metric_card(
            "相對 30D",
            _percent(windows["30d"]["today_change_pct"]),
            f"均價 {_price(windows['30d']['price_twd_per_kg'])}",
        ),
        _metric_card(
            "7D 波動度 CV",
            _volatility(series.get("volatility_7d_cv")),
            _status_label(series.get("volatility_7d_status")),
        ),
        _metric_card("今日交易量", f"{_number(series['today']['volume_kg'], 0)} kg"),
        _metric_card(
            "交易量 vs 7D",
            _percent(windows["7d"]["today_volume_change_pct"]),
            f"7D 日均 {_number(windows['7d']['avg_daily_volume_kg'], 0)} kg",
        ),
        _metric_card("市場數", series["today"]["market_count"]),
        _metric_card(
            "7D 有效日",
            f"{windows['7d']['coverage_days']} 日",
            _status_label(windows["7d"]["status"]),
        ),
        _metric_card(
            "30D 有效日",
            f"{windows['30d']['coverage_days']} 日",
            _status_label(windows["30d"]["status"]),
        ),
        _metric_card(
            "90D 有效日",
            f"{windows['90d']['coverage_days']} 日",
            _status_label(windows["90d"]["status"]),
        ),
    ]
    return (
        "<section class='section trend-quant-summary' data-trend-quant='v1'>"
        "<div class='section-heading'><div><div class='eyebrow ink'>QUANTITATIVE TREND</div>"
        "<h2>價格量化摘要</h2></div><span class='badge info'>deterministic</span></div>"
        "<p class='lead'>同一份行情序列直接計算；數字優先，方向文字只作輔助。</p>"
        f"<div class='grid grid-4'>{''.join(cards)}</div></section>"
    )


def _valid_points(series):
    points = []
    for row in series.get("daily", []):
        price = row.get("price_twd_per_kg")
        volume = row.get("volume_kg")
        if price is None or volume is None or volume <= 0:
            continue
        points.append(
            {
                "date": row["date"],
                "day": dt.date.fromisoformat(row["date"]),
                "price": float(price),
            }
        )
    return points


def _nice_axis(low, high, target_ticks=5):
    if not math.isfinite(low) or not math.isfinite(high):
        raise ValueError("price axis requires finite values")
    if high < low:
        low, high = high, low
    if math.isclose(low, high):
        padding = max(abs(low) * 0.05, 1.0)
        low -= padding
        high += padding
    span = high - low
    raw_step = span / max(target_ticks - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude
    if normalized <= 1:
        nice = 1
    elif normalized <= 2:
        nice = 2
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10
    step = nice * magnitude
    axis_low = math.floor(low / step) * step
    axis_high = math.ceil(high / step) * step
    ticks = []
    value = axis_low
    limit = 0
    while value <= axis_high + step * 0.25 and limit < 20:
        ticks.append(round(value, 8))
        value += step
        limit += 1
    return axis_low, axis_high, ticks


def _x_ticks(points, count=5):
    if not points:
        return []
    if len(points) <= count:
        return points
    indexes = sorted(
        {
            round(index * (len(points) - 1) / (count - 1))
            for index in range(count)
        }
    )
    return [points[index] for index in indexes]


def _spread_label_positions(labels, min_y, max_y, min_gap=18.0):
    """Return deterministic non-overlapping label baselines within the chart bounds."""
    if not labels:
        return {}
    if max_y < min_y:
        min_y, max_y = max_y, min_y

    ordered = sorted(
        enumerate(labels),
        key=lambda item: (float(item[1]["desired_y"]), item[0]),
    )
    if len(ordered) == 1:
        _, label = ordered[0]
        return {label["key"]: min(max(float(label["desired_y"]), min_y), max_y)}

    available = max_y - min_y
    gap = min(float(min_gap), available / (len(ordered) - 1))
    positions = []
    for _, label in ordered:
        desired = min(max(float(label["desired_y"]), min_y), max_y)
        y = desired if not positions else max(desired, positions[-1] + gap)
        positions.append(y)

    overflow = positions[-1] - max_y
    if overflow > 0:
        positions = [y - overflow for y in positions]
    if positions[0] < min_y:
        positions[0] = min_y
        for index in range(1, len(positions)):
            positions[index] = max(positions[index], positions[index - 1] + gap)

    return {
        label["key"]: positions[position_index]
        for position_index, (_, label) in enumerate(ordered)
    }


def _annotation_html(annotation, y):
    return (
        f"<text x='{annotation['x']:.1f}' y='{y:.1f}' text-anchor='{annotation['anchor']}' "
        f"class='{annotation['css_class']}' data-chart-label='{annotation['key']}'>"
        f"{annotation['text']}</text>"
    )


def _chart_html(series):
    points = _valid_points(series)
    if len(points) < 2:
        return (
            "<div class='chart quantitative-chart' data-trend-chart='v1'>"
            "<p class='note warn'>有效價格觀測不足 2 日，暫不繪製折線；請參考下方表格。</p></div>"
        )

    width, height = 760.0, 280.0
    left, right, top, bottom = 68.0, 24.0, 24.0, 48.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    prices = [point["price"] for point in points]
    observed_low, observed_high = min(prices), max(prices)
    padding = max((observed_high - observed_low) * 0.08, observed_high * 0.01, 0.5)
    axis_low, axis_high, y_ticks = _nice_axis(
        max(0.0, observed_low - padding), observed_high + padding
    )
    y_span = axis_high - axis_low or 1.0
    first_day, last_day = points[0]["day"], points[-1]["day"]
    day_span = max((last_day - first_day).days, 1)

    def x_for(point):
        return left + ((point["day"] - first_day).days / day_span) * plot_width

    def y_for(price):
        return top + (axis_high - price) / y_span * plot_height

    grid = []
    for value in y_ticks:
        y = y_for(value)
        grid.append(
            f"<line x1='{left:.1f}' y1='{y:.1f}' x2='{width-right:.1f}' y2='{y:.1f}' class='chart-grid'/>"
            f"<text x='{left-9:.1f}' y='{y+4:.1f}' text-anchor='end' class='chart-tick'>NT$ {value:g}</text>"
        )
    x_axis = [
        f"<line x1='{left:.1f}' y1='{height-bottom:.1f}' x2='{width-right:.1f}' y2='{height-bottom:.1f}' class='chart-axis'/>"
    ]
    for point in _x_ticks(points):
        x = x_for(point)
        x_axis.append(
            f"<line x1='{x:.1f}' y1='{height-bottom:.1f}' x2='{x:.1f}' y2='{height-bottom+5:.1f}' class='chart-axis'/>"
            f"<text x='{x:.1f}' y='{height-bottom+20:.1f}' text-anchor='middle' class='chart-tick'>{html.escape(point['date'][5:])}</text>"
        )

    line_points = " ".join(
        f"{x_for(point):.1f},{y_for(point['price']):.1f}" for point in points
    )

    references = []
    annotations = []
    for window_name, css_class, label in (
        ("7d", "chart-ref-7d", "7D 均價"),
        ("30d", "chart-ref-30d", "30D 均價"),
    ):
        value = series["windows"][window_name].get("price_twd_per_kg")
        if value is None or not (axis_low <= value <= axis_high):
            continue
        y = y_for(float(value))
        references.append(
            f"<line x1='{left:.1f}' y1='{y:.1f}' x2='{width-right:.1f}' y2='{y:.1f}' class='chart-ref {css_class}'/>"
        )
        annotations.append(
            {
                "key": window_name,
                "x": width - right - 2,
                "desired_y": y - 5,
                "anchor": "end",
                "css_class": "chart-ref-label",
                "text": f"{label} {_price(value)}",
            }
        )

    point_by_date = {point["date"]: point for point in points}
    markers = []
    latest = points[-1]
    latest_y = y_for(latest["price"])
    markers.append(
        f"<circle cx='{x_for(latest):.1f}' cy='{latest_y:.1f}' r='5' class='chart-point chart-point-latest'/>"
    )
    annotations.append(
        {
            "key": "latest",
            "x": x_for(latest) - 8,
            "desired_y": max(top + 12, latest_y - 10),
            "anchor": "end",
            "css_class": "chart-label",
            "text": f"最新 {_price(latest['price'])}",
        }
    )

    range_30d = series.get("range_stats", {}).get("30d", {})
    for key, css_class, label in (
        ("max", "chart-point-high", "30D 高點"),
        ("min", "chart-point-low", "30D 低點"),
    ):
        date_value = range_30d.get(f"{key}_date")
        price_value = range_30d.get(f"{key}_price_twd_per_kg")
        point = point_by_date.get(date_value)
        if point is None or price_value is None:
            continue
        point_x = x_for(point)
        y = y_for(float(price_value))
        desired_y = max(top + 12, y - 10) if key == "max" else min(height - bottom - 8, y + 18)
        if point_x < left + 140:
            text_x, anchor = point_x + 8, "start"
        elif point_x > width - right - 140:
            text_x, anchor = point_x - 8, "end"
        else:
            text_x, anchor = point_x, "middle"
        markers.append(
            f"<circle cx='{point_x:.1f}' cy='{y:.1f}' r='4.5' class='chart-point {css_class}'/>"
        )
        annotations.append(
            {
                "key": "high" if key == "max" else "low",
                "x": text_x,
                "desired_y": desired_y,
                "anchor": anchor,
                "css_class": "chart-label",
                "text": f"{label} {_price(price_value)} · {html.escape(date_value[5:])}",
            }
        )

    label_positions = _spread_label_positions(
        annotations,
        min_y=top + 12,
        max_y=height - bottom - 8,
    )
    annotation_markup = [
        _annotation_html(annotation, label_positions[annotation["key"]])
        for annotation in annotations
    ]

    status_note = _status_label(range_30d.get("status"))
    accessible = (
        f"最多 120 日價格趨勢，實際 {len(points)} 個有效交易日。"
        f"最新 {_price(latest['price'])}。"
        f"7D 均價 {_price(series['windows']['7d']['price_twd_per_kg'])}，"
        f"30D 均價 {_price(series['windows']['30d']['price_twd_per_kg'])}。"
        f"30D 高低點統計狀態：{status_note}。"
    )
    aria = html.escape(accessible, quote=True)
    insufficient_class = "trend-stat-insufficient" if range_30d.get("status") != "valid" else ""
    return (
        f"<div class='chart quantitative-chart' data-trend-chart='v1' role='img' aria-label='{aria}'>"
        f"<svg viewBox='0 0 {int(width)} {int(height)}' aria-hidden='true' focusable='false'>"
        + "".join(grid)
        + "".join(x_axis)
        + "".join(references)
        + f"<polyline points='{line_points}' class='chart-line'/>"
        + "".join(markers)
        + "".join(annotation_markup)
        + "</svg>"
        + f"<p class='sr-only'>{html.escape(accessible)}</p></div>"
        + f"<p class='trend-chart-note'>價格軸依實際觀測範圍產生刻度，不強制從 0 起算；休市與缺資料不補 0。30D 高低點：<span class='{insufficient_class}'>{status_note}</span>。</p>"
    )


def _replace_product_html(source, series):
    source = re.sub(
        r"<style data-trend-quant-style='v1'>.*?</style>",
        "",
        source,
        flags=re.S,
    )
    if "</head>" not in source:
        raise ValueError("produce page head marker is missing")
    source = source.replace(
        "</head>",
        f"<style {STYLE_ATTR}>{PRICE_TREND_CSS.strip()}</style></head>",
        1,
    )
    source = re.sub(
        r"<section class='section trend-quant-summary' data-trend-quant='v1'>.*?</section>",
        "",
        source,
        flags=re.S,
    )
    summary = _summary_html(series)
    buy_score_marker = "<section class='section'><h2>Buy Score 與產季</h2>"
    if buy_score_marker not in source:
        raise ValueError("produce page Buy Score section marker is missing")
    source = source.replace(buy_score_marker, summary + buy_score_marker, 1)

    valid_count = len(_valid_points(series))
    new_prefix = (
        "<section class='section trend-quant-chart' data-trend-quant='v1'>"
        f"<h2>最多 120 日價格趨勢 · 實際 {valid_count} 個有效交易日</h2>"
        + _chart_html(series)
        + "<p class='disclaimer'>批發市場平均行情，非實際零售通路售價。</p>"
    )
    old_pattern = (
        r"<section class='section'><h2>近 120 日價格趨勢</h2>.*?"
        r"<p class='disclaimer'>批發市場平均行情，非實際零售通路售價。</p>"
    )
    enhanced_pattern = (
        r"<section class='section trend-quant-chart' data-trend-quant='v1'><h2>.*?</h2>.*?"
        r"<p class='disclaimer'>批發市場平均行情，非實際零售通路售價。</p>"
    )
    source, count = re.subn(old_pattern, new_prefix, source, count=1, flags=re.S)
    if count == 0:
        source, count = re.subn(
            enhanced_pattern, new_prefix, source, count=1, flags=re.S
        )
    if count != 1:
        raise ValueError("produce page price trend section marker is missing")
    return source


def enhance_price_trends(root=None):
    root = pathlib.Path.cwd() if root is None else pathlib.Path(root)
    series_root = root / "data/series"
    produce_root = root / "site/produce"
    if not series_root.exists() or not produce_root.exists():
        raise ValueError("price trend enhancement requires built series and produce pages")

    enhanced = 0
    for series_path in sorted(series_root.glob("*.json")):
        series = json.loads(series_path.read_text(encoding="utf-8"))
        if not isinstance(series.get("range_stats"), dict):
            raise ValueError(f"series range_stats missing: {series_path.name}")
        page_path = produce_root / f"{series_path.stem}.html"
        if not page_path.exists():
            continue
        source = page_path.read_text(encoding="utf-8")
        page_path.write_text(_replace_product_html(source, series), encoding="utf-8")
        enhanced += 1
    if enhanced == 0:
        raise ValueError("no produce pages matched price series")
    return enhanced
