"""异动 AI 归因：把当日异动个股与近期新闻关联，给每只一句话「为什么涨/跌」。

一次 LLM 调用覆盖全部异动（省 token）。找不到相关新闻就标「未见明确催化」，
不臆造原因。无 LLM key 时本步骤不会被调用（pipeline 层判断）。
"""

from __future__ import annotations

import logging

from ..analyzer import _extract_json
from ..llm.base import LLMClient, LLMError
from ..models import MoverAlert, NewsItem

log = logging.getLogger("attribution")

_SYSTEM = (
    "你是美股投研助手。给你今日异动个股和近期新闻标题，请为每只个股用一句简短中文说明"
    "最可能的驱动因素，能对应到某条新闻就点出，找不到就写「未见明确催化」。不要臆造、"
    "不要给买卖建议。只输出 JSON。"
)


def _build_prompt(alerts: list[MoverAlert], news: list[NewsItem]) -> str:
    movers = "\n".join(f"{a.symbol} {a.change_pct:+.1f}%" for a in alerts)
    headlines = "\n".join(f"- {n.title}" for n in news[:60])
    return (
        f"今日异动个股：\n{movers}\n\n"
        f"近期新闻标题：\n{headlines}\n\n"
        '输出 JSON，键为股票代码，值为一句话原因，例如 '
        '{"NVDA": "财报超预期，数据中心营收创新高"}'
    )


def attribute(llm: LLMClient, alerts: list[MoverAlert], news: list[NewsItem]) -> dict[str, str]:
    """返回 {symbol: 一句话原因}。失败时返回空 dict（调用方保留规则文案）。"""
    if not alerts:
        return {}
    try:
        raw = llm.chat(_SYSTEM, _build_prompt(alerts, news))
        data = _extract_json(raw)
        return {str(k).upper(): str(v).strip() for k, v in data.items() if str(v).strip()}
    except (LLMError, ValueError, KeyError) as exc:
        log.warning("异动 AI 归因失败，保留规则文案：%s", exc)
        return {}


def apply(alerts: list[MoverAlert], reasons: dict[str, str]) -> None:
    """把 AI 归因并入每条告警的 reason（原地修改）。"""
    for a in alerts:
        ai = reasons.get(a.symbol.upper())
        if ai and "未见明确催化" not in ai:
            a.reason = f"{a.reason}｜{ai}"
