"""Report -> 文本/卡片 渲染。

PushPlus、Server酱用 Markdown 字符串；飞书用交互卡片（lark_md）。
两者共用同一套要点文案，保证多渠道内容一致。
"""

from __future__ import annotations

from datetime import timezone, timedelta

from ..analyzer import TOPIC_LABELS
from ..models import Report

# 情绪 -> emoji，让结论一眼可读
_SENTIMENT_EMOJI = {
    "bullish": "🟢 偏多",
    "bearish": "🔴 偏空",
    "neutral": "⚪ 中性",
    "mixed": "🟡 分化",
}

_CST = timezone(timedelta(hours=8))   # 报告时间统一按北京时间展示


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
