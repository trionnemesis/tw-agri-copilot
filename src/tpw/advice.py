import hashlib
import json


PROMPT_VERSION = "tpw-advice-v1"
DISCLAIMER = "批發市場平均行情，非實際零售通路售價。"
BANNED_CLAIMS = ("保證划算", "一定便宜", "療效", "治療", "本日成交來自")


class AdviceMode(str):
    """Keep the machine mode code stable while rendering a user-facing label in HTML/report text."""

    LABELS = {
        "deterministic_fallback": "規則分析模式",
        "ai": "AI 摘要模式",
    }

    def __str__(self):
        code = super().__str__()
        return self.LABELS.get(code, code)


def _mode(code):
    return AdviceMode(code)


def provider_input(scores, as_of_date):
    allowed = (
        "canonical_id",
        "score",
        "verdict",
        "seasonality_status",
        "today_price",
        "previous_trading_day_change_pct",
        "vs_7d_pct",
        "vs_30d_pct",
        "volume_vs_7d_pct",
        "market_count",
        "coverage",
        "reason_codes",
    )
    selected = [
        {key: row[key] for key in allowed}
        for row in scores
        if row["verdict"] in ("priority", "consider", "hold", "insufficient")
    ][:8]
    return {
        "schema_version": "1.0",
        "language": "zh-Hant",
        "as_of_date": as_of_date,
        "disclaimer": DISCLAIMER,
        "items": selected,
    }


def _input_hash(value):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()


def _reason_text(row):
    labels = {
        "IN_SEASON": "當季",
        "PRICE_AT_OR_BELOW_7D": "價格不高於 7 日均價",
        "PRICE_AT_OR_BELOW_30D": "價格不高於 30 日均價",
        "VOLUME_HEALTHY": "交易量相對穩健",
        "COVERAGE_INSUFFICIENT": "資料天數不足",
        "MARKET_COUNT_INSUFFICIENT": "有效市場數不足",
        "DATA_QUALITY_WARNING": "存在資料品質警示",
    }
    reasons = "、".join(labels.get(code, code) for code in row["reason_codes"])
    return f"{row['verdict_label']}：{reasons or '依決定性規則判定'}。"


def fallback_advice(scores, as_of_date, fallback_reason="未使用生成式 AI"):
    evidence = provider_input(scores, as_of_date)
    priority = [row for row in scores if row["verdict"] in ("priority", "consider")][:5]
    watch = [row for row in scores if row["verdict"] in ("hold", "insufficient")][:3]
    return {
        "schema_version": "1.0",
        "language": "zh-Hant",
        "as_of_date": as_of_date,
        "headline": f"{as_of_date} 當季採買觀察｜規則分析模式",
        "summary": (
            f"本期依產季、批發價格、交易量與資料覆蓋率，由可重現的規則引擎自動產生採買判定；"
            f"共有 {len(priority)} 項列入優先或可考慮清單。"
            f"目前採用規則分析模式（{fallback_reason}），不由生成式 AI 修改 Buy Score 或 verdict；"
            f"此區塊會隨每日 09:00 與 18:00（Asia/Taipei）資料更新同步重算。"
        ),
        "priority_items": [
            {"canonical_id": row["canonical_id"], "text": _reason_text(row)}
            for row in priority
        ],
        "watch_items": [
            {"canonical_id": row["canonical_id"], "text": _reason_text(row)}
            for row in watch
        ],
        "disclaimer": DISCLAIMER,
        "model": "deterministic-template",
        "prompt_version": PROMPT_VERSION,
        "input_hash": _input_hash(evidence),
        "generated_at": as_of_date + "T00:00:00Z",
        "generation_mode": _mode("deterministic_fallback"),
    }


def validate_advice(payload, scores, as_of_date):
    required = {
        "schema_version",
        "language",
        "as_of_date",
        "headline",
        "summary",
        "priority_items",
        "watch_items",
        "disclaimer",
        "model",
        "prompt_version",
        "input_hash",
        "generated_at",
    }
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise ValueError("advice output schema is incomplete")
    if payload["language"] != "zh-Hant" or payload["as_of_date"] != as_of_date:
        raise ValueError("advice language or date mismatch")
    if DISCLAIMER not in payload["disclaimer"]:
        raise ValueError("advice disclaimer missing")
    combined = payload["headline"] + payload["summary"] + payload["disclaimer"]
    combined += "".join(item.get("text", "") for item in payload["priority_items"] + payload["watch_items"])
    if any(claim in combined for claim in BANNED_CLAIMS):
        raise ValueError("advice contains a prohibited claim")
    if len(combined) > 1200:
        raise ValueError("advice exceeds length limit")
    valid_ids = {row["canonical_id"] for row in scores}
    for key in ("priority_items", "watch_items"):
        if not isinstance(payload[key], list):
            raise ValueError("advice item collection must be a list")
        if any(item.get("canonical_id") not in valid_ids or not item.get("text") for item in payload[key]):
            raise ValueError("advice references invalid evidence")
    return payload


def generate_advice(scores, as_of_date, enabled=False, provider=None):
    if not enabled or provider is None:
        return fallback_advice(scores, as_of_date)
    evidence = provider_input(scores, as_of_date)
    try:
        payload = provider(evidence)
        payload["generation_mode"] = _mode("ai")
        payload["input_hash"] = _input_hash(evidence)
        return validate_advice(payload, scores, as_of_date)
    except Exception as error:
        return fallback_advice(scores, as_of_date, f"AI 輸出不可用（{type(error).__name__}）")
