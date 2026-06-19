"""Report -> 文本/卡片 渲染。

PushPlus、Server酱用 Markdown 字符串；飞书用交互卡片（lark_md）。
两者共用同一套要点文案，保证多渠道内容一致。
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from ..analyzer import TOPIC_LABELS
from ..models import MoverAlert, NewsItem, Report
from .message import Message

# 情绪 -> emoji，让结论一眼可读
_SENTIMENT_EMOJI = {
    "bullish": "🟢 偏多",
    "bearish": "🔴 偏空",
    "neutral": "⚪ 中性",
    "mixed": "🟡 分化",
}

_CST = timezone(timedelta(hours=8))   # 报告时间统一按北京时间展示


def _now_cst() -> str:
    return datetime.now(timezone.utc).astimezone(_CST).strftime("%Y-%m-%d %H:%M")


def _fmt_time(report: Report) -> str:
    return report.generated_at.astimezone(_CST).strftime("%Y-%m-%d %H:%M")


def render_markdown(report: Report, show_stats: bool = True) -> str:
    """生成通用 Markdown（PushPlus / Server酱通用）。"""
    parts: list[str] = []
    parts.append(f"# {report.title}")
    parts.append(f"*{_fmt_time(report)} (北京时间)*")

    if report.overview:
        parts.append(f"\n> {report.overview}")

    for a in report.analyses:
        label = TOPIC_LABELS.get(a.topic, a.topic)
        senti = _SENTIMENT_EMOJI.get(a.sentiment, a.sentiment)
        parts.append(f"\n## {label} · {senti}")
        if a.headline:
            parts.append(f"**{a.headline}**")
        for b in a.bullets:
            parts.append(f"- {b}")
        if a.tickers:
            parts.append(f"\n相关标的: `{'` `'.join(a.tickers)}`")

    if report.calendar:
        parts.append("\n## 📅 近期财报")
        parts.extend(f"- {c}" for c in report.calendar)

    if show_stats and report.stats:
        total = sum(report.stats.values())
        detail = " | ".join(f"{k}:{v}" for k, v in report.stats.items())
        parts.append(f"\n---\n_共分析 {total} 条 ({detail})_")

    return "\n".join(parts)


def render_feishu_card(report: Report, show_stats: bool = True) -> dict:
    """生成飞书交互卡片 payload 的 card 部分。"""
    elements: list[dict] = []

    if report.overview:
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"📌 {report.overview}"}}
        )
        elements.append({"tag": "hr"})

    for a in report.analyses:
        label = TOPIC_LABELS.get(a.topic, a.topic)
        senti = _SENTIMENT_EMOJI.get(a.sentiment, a.sentiment)
        lines = [f"**{label}** · {senti}"]
        if a.headline:
            lines.append(a.headline)
        lines.extend(f"• {b}" for b in a.bullets)
        if a.tickers:
            lines.append(f"相关标的: {' '.join(a.tickers)}")
        elements.append(
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}
        )
        elements.append({"tag": "hr"})

    if report.calendar:
        cal = "**📅 近期财报**\n" + "\n".join(f"• {c}" for c in report.calendar)
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": cal}})
        elements.append({"tag": "hr"})

    footer = _fmt_time(report) + " (北京时间)"
    if show_stats and report.stats:
        footer += f" · 共 {sum(report.stats.values())} 条"
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": footer}]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": report.title},
            "template": "blue",
        },
        "elements": elements,
    }


def build_daily_message(report: Report, show_stats: bool = True) -> Message:
    """每日简报 -> Message。"""
    return Message(
        title=report.title,
        markdown=render_markdown(report, show_stats),
        feishu_card=render_feishu_card(report, show_stats),
    )


# ---------------- 盘中异动速报 ----------------

_MOVER_TITLE = "🚨 美股异动速报"


def _mover_line(a: MoverAlert) -> str:
    arrow = "📈" if a.change_pct >= 0 else "📉"
    return f"{arrow} **{a.symbol}** {a.change_pct:+.1f}% @ {a.price:g} — {a.reason}"


def render_movers_markdown(alerts: list[MoverAlert]) -> str:
    parts = [f"# {_MOVER_TITLE}", f"*{_now_cst()} (北京时间)*", ""]
    parts.extend(_mover_line(a) for a in alerts)
    parts.append("\n---\n_仅信息提醒，非投资建议；免费行情约 15 分钟延迟_")
    return "\n".join(parts)


def render_movers_feishu_card(alerts: list[MoverAlert]) -> dict:
    up = sum(1 for a in alerts if a.change_pct >= 0)
    elements: list[dict] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(_mover_line(a) for a in alerts)},
        },
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"{_now_cst()} 北京时间 · {len(alerts)} 只异动（涨 {up} / 跌 {len(alerts) - up}）· 非投资建议",
                }
            ],
        },
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": _MOVER_TITLE},
            "template": "red",
        },
        "elements": elements,
    }


def build_movers_message(alerts: list[MoverAlert]) -> Message:
    """异动告警列表 -> Message。"""
    return Message(
        title=_MOVER_TITLE,
        markdown=render_movers_markdown(alerts),
        feishu_card=render_movers_feishu_card(alerts),
    )


# ---------------- 重大事件速报（SEC 8-K）----------------

_EVENTS_TITLE = "⚡ 美股重大事件 (SEC 8-K)"


def _event_time(n: NewsItem) -> str:
    return n.published_at.astimezone(_CST).strftime("%m-%d %H:%M") if n.published_at else ""


def render_events_markdown(items: list[NewsItem]) -> str:
    parts = [f"# {_EVENTS_TITLE}", f"*{_now_cst()} (北京时间)*", ""]
    parts.extend(f"⚡ [{n.title}]({n.url}) {_event_time(n)}" for n in items)
    parts.append("\n---\n_8-K 为公司向 SEC 申报的重大事件；仅信息提醒，非投资建议_")
    return "\n".join(parts)


def render_events_feishu_card(items: list[NewsItem]) -> dict:
    body = "\n".join(f"⚡ [{n.title}]({n.url}) {_event_time(n)}" for n in items)
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": body}},
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": f"{_now_cst()} 北京时间 · {len(items)} 起 · 非投资建议"}
            ],
        },
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": _EVENTS_TITLE}, "template": "orange"},
        "elements": elements,
    }


def build_events_message(items: list[NewsItem]) -> Message:
    return Message(
        title=_EVENTS_TITLE,
        markdown=render_events_markdown(items),
        feishu_card=render_events_feishu_card(items),
    )
