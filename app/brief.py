"""按需即时查询：拉某只美股的最新行情 + 近期新闻/公告(8-K) + AI 一句话点评。

服务「大事件发生后我想立刻查」的诉求 —— `python -m app brief NVDA` 随时跑。
不依赖盘中调度，单只标的、即时返回。
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from .collectors.finnhub import company_news
from .collectors.sec import recent_8k
from .config import Settings
from .http import make_client
from .llm.base import LLMError
from .llm.factory import build_llm
from .market.provider import fetch_quotes
from .models import NewsItem, Quote
from .notifiers.message import Message

_CST = timezone(timedelta(hours=8))


def gather(settings: Settings, ticker: str) -> tuple[Quote | None, list[NewsItem]]:
    """并发拉取单只标的的行情、公司新闻、近三周 8-K。"""
    with make_client() as client:
        quote = next(iter(fetch_quotes(settings, [ticker], client)), None)
        news = company_news(client, settings, ticker, days=7)
        try:
            events = recent_8k(client, settings, [ticker], days=21)
        except Exception:
            events = []   # SEC 故障不应拖垮 brief
    items = events + news
    items.sort(key=lambda n: (n.published_at is not None, n.published_at), reverse=True)
    return quote, items[:15]


def ai_take(settings: Settings, ticker: str, quote: Quote | None, items: list[NewsItem]) -> str:
    """基于行情与新闻给一句话点评；无 LLM key 或失败时返回空串。"""
    try:
        llm = build_llm(settings)
    except LLMError:
        return ""
    price = "N/A"
    if quote:
        price = f"{quote.price:g}"
        if quote.change_pct is not None:
            price += f"（日内 {quote.change_pct:+.1f}%）"
    headlines = "\n".join(f"- {n.title}" for n in items[:15]) or "（暂无）"
    system = (
        "你是美股投研助手。基于给定行情与新闻/公告，用 2-3 句中文点出该股近期最值得关注的点。"
        "不预测涨跌、不给买卖建议。"
    )
    user = f"标的：{ticker}\n最新价：{price}\n近期新闻与公告：\n{headlines}"
    try:
        return llm.chat(system, user).strip()
    except LLMError:
        return ""


def build_message(ticker: str, quote: Quote | None, items: list[NewsItem], take: str) -> Message:
    now = datetime.now(timezone.utc).astimezone(_CST).strftime("%Y-%m-%d %H:%M")
    title = f"🔎 {ticker} 速览"

    lines = [f"# {title}", f"*{now} (北京时间)*", ""]
    if quote:
        chg = f"（日内 {quote.change_pct:+.1f}%）" if quote.change_pct is not None else ""
        lines.append(f"**行情**：{quote.price:g}{chg}")
    if take:
        lines.append(f"\n**AI 点评**：{take}")
    lines.append("\n## 近期新闻与公告")
    if items:
        for n in items:
            date = n.published_at.astimezone(_CST).strftime("%m-%d") if n.published_at else ""
            lines.append(f"- [{n.title}]({n.url}) {date}")
    else:
        lines.append("- （近期无相关新闻/公告）")
    lines.append("\n---\n_仅信息提醒，非投资建议；免费行情约 15 分钟延迟_")
    markdown = "\n".join(lines)

    body = []
    if quote:
        chg = f"（日内 {quote.change_pct:+.1f}%）" if quote.change_pct is not None else ""
        body.append(f"**行情**：{quote.price:g}{chg}")
    if take:
        body.append(f"**AI 点评**：{take}")
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(body)}}]
    if items:
        listmd = "\n".join(
            f"• [{n.title}]({n.url})"
            + (f" {n.published_at.astimezone(_CST).strftime('%m-%d')}" if n.published_at else "")
            for n in items
        )
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": listmd}})
    elements.append(
        {"tag": "note", "elements": [{"tag": "plain_text", "content": f"{now} 北京时间 · 非投资建议"}]}
    )
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": "turquoise"},
        "elements": elements,
    }
    return Message(title=title, markdown=markdown, feishu_card=card)


def run_brief(settings: Settings, ticker: str, *, push: bool = False) -> Message:
    ticker = ticker.upper()
    quote, items = gather(settings, ticker)
    take = ai_take(settings, ticker, quote, items)
    msg = build_message(ticker, quote, items, take)
    if push:
        from .notifiers.registry import build_notifiers

        for n in build_notifiers(settings):
            n.send(msg)
    return msg
