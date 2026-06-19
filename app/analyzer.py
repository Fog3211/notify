"""AI 分析层：把分组后的新闻喂给 LLM，产出结构化结论。

一次调用覆盖全部主题：既省 token，也让模型能给出跨主题的全局综述。
要求模型返回 JSON，再稳健解析成 Report。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from .config import Settings
from .llm.base import LLMClient, LLMError
from .models import NewsItem, Report, TopicAnalysis

log = logging.getLogger("analyzer")

_SYSTEM = (
    "你是一名资深的科技与美股投研分析师，覆盖 AI、半导体、存储、CPO（光模块/共封装光学）"
    "以及美股科技与宏观财经。你的任务是把当天的新闻提炼成可执行的投研简报：抓主线、"
    "判断对相关标的的影响与情绪，去掉营销稿与无信息量的噪音。只输出 JSON，不要多余文字。"
)

# 主题中文名，用于提示与渲染
TOPIC_LABELS = {
    "events": "⚡ 重大事件",
    "ai": "AI / 大模型",
    "us_tech": "美股科技",
    "finance": "宏观财经",
    "semiconductor": "半导体 / 存储 / CPO",
}


def _build_user_prompt(
    items_by_topic: dict[str, list[NewsItem]], tickers: list[str]
) -> str:
    lines: list[str] = []
    lines.append(f"今日关注标的（供判断影响时参考）：{', '.join(tickers)}")
    lines.append("")
    lines.append("以下是按主题分组的今日新闻（标题 + 摘要）：")
    for topic, items in items_by_topic.items():
        label = TOPIC_LABELS.get(topic, topic)
        lines.append(f"\n## 主题: {topic} ({label}) —— {len(items)} 条")
        for i, it in enumerate(items, 1):
            lines.append(f"{i}. {it.title}")
            if it.summary:
                lines.append(f"   摘要: {it.summary}")
            lines.append(f"   来源: {it.source} | {it.url}")

    schema = {
        "overview": "一段话总览今日最值得关注的 2-3 条主线（中文）",
        "topics": [
            {
                "topic": "上面给出的 topic 标识之一",
                "headline": "该主题今日最关键的一句话结论（中文）",
                "bullets": ["3-5 条要点，每条含事件+影响判断（中文）"],
                "sentiment": "bullish | bearish | neutral | mixed 之一",
                "tickers": ["受影响的相关标的代码，可空"],
            }
        ],
    }
    lines.append("\n请严格按如下 JSON 结构输出（仅输出 JSON）：")
    lines.append(json.dumps(schema, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """从模型输出中稳健提取 JSON：去 ```fence```，再截取首尾花括号。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型输出中未找到 JSON 对象")
    return json.loads(text[start : end + 1])


def analyze(
    settings: Settings,
    llm: LLMClient,
    items_by_topic: dict[str, list[NewsItem]],
) -> Report:
    stats = {topic: len(items) for topic, items in items_by_topic.items()}
    user_prompt = _build_user_prompt(items_by_topic, settings.all_tickers())

    raw = llm.chat(_SYSTEM, user_prompt)
    data = _extract_json(raw)

    analyses: list[TopicAnalysis] = []
    for entry in data.get("topics", []):
        topic = entry.get("topic", "").strip()
        if not topic:
            continue
        analyses.append(
            TopicAnalysis(
                topic=topic,
                headline=entry.get("headline", "").strip(),
                bullets=[b.strip() for b in entry.get("bullets", []) if b.strip()],
                sentiment=entry.get("sentiment", "neutral").strip() or "neutral",
                tickers=[t.strip() for t in entry.get("tickers", []) if t.strip()],
            )
        )

    return Report(
        title=settings.report.title,
        generated_at=datetime.now(timezone.utc),
        analyses=analyses,
        overview=data.get("overview", "").strip(),
        stats=stats,
    )


def safe_analyze(
    settings: Settings,
    llm: LLMClient,
    items_by_topic: dict[str, list[NewsItem]],
) -> Report | None:
    """analyze 的容错包装：LLM 或解析失败时返回 None，由管道决定是否中止。"""
    try:
        return analyze(settings, llm, items_by_topic)
    except (LLMError, ValueError, KeyError, json.JSONDecodeError) as exc:
        log.error("AI 分析失败：%s", exc)
        return None
