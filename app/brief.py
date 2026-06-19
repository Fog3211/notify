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


def gather(
    settings: Settings, ticker: str
) -> tuple[Quote | None, list[NewsItem], list[NewsItem]]:
    """并发拉取行情、近三周 8-K 公告、近一周公司新闻。

    公告与新闻分开返回：8-K 频率低但更重要，单独成栏置顶，避免被高频新闻挤掉。
    """
    with make_client() as client:
        quote = next(iter(fetch_quotes(settings, [ticker], client)), None)
        news = company_news(client, settings, ticker, days=7)
        try:
            events = recent_8k(client, settings, [ticker], days=21)
        except Exception:
            events = []   # SEC 故障不应拖垮 brief
    key = lambda n: (n.published_at is not None, n.published_at)   # noqa: E731
    events.sort(key=key, reverse=True)
    news.sort(key=key, reverse=True)
    return quote, events[:8], news[:12]


def ai_take(
    settings: Settings, ticker: str, quote: Quote | None,
    events: list[NewsItem], news: list[NewsItem],
) -> str:
    """基于行情与公告/新闻给一句话点评；无 LLM key 或失败时返回空串。"""
    try:
        llm = build_llm(settings)
    except LLMError:
        return ""
    price = "N/A"
    if quote:
        price = f"{quote.price:g}"
        if quote.change_pct is not None:
            price += f"（日内 {quote.change_pct:+.1f}%）"
    # 公告优先进上下文，再补新闻
    headlines = "\n".join(f"- {n.title}" for n in (events + news)[:15]) or "（暂无）"
    system = (
        "你是美股投研助手。基于给定行情与公告/新闻，用 2-3 句中文点出该股近期最值得关注的点，"
        "若有 8-K 重大公告请优先点出。不预测涨跌、不给买卖建议。"
    )
    user = f"标的：{ticker}\n最新价：{price}\n近期公告与新闻：\n{headlines}"
    try:
        return llm.chat(system, user).strip()
    except LLMError:
        return ""


def _date(n: NewsItem) -> str:
    return n.published_at.astimezone(_CST).strftime("%m-%d") if n.published_at else ""


def build_message(
    ticker: str, quote: Quote | None,
    events: list[NewsItem], news: list[NewsItem], take: str,
) -> Message:
    now = datetime.now(timezone.utc).astimezone(_CST).strftime("%Y-%m-%d %H:%M")
    title = f"🔎 {ticker} 速览"
    chg = f"（日内 {quote.change_pct:+.1f}%）" if quote and quote.change_pct is not None else ""

    # ---- Markdown（PushPlus / Server酱）----
    lines = [f"# {title}", f"*{now} (北京时间)*", ""]
    if quote:
        lines.append(f"**行情**：{quote.price:g}{chg}")
    if take:
        lines.append(f"\n**AI 点评**：{take}")
    if events:   # 8-K 公告置顶单独成栏
        lines.append("\n## 📋 重大公告 (SEC 8-K)")
        lines += [f"- [{n.title}]({n.url}) {_date(n)}" for n in events]
    lines.append("\n## 📰 近期新闻")
    lines += [f"- [{n.title}]({n.url}) {_date(n)}" for n in news] or ["- （近期无相关新闻）"]
    lines.append("\n---\n_仅信息提醒，非投资建议；免费行情约 15 分钟延迟_")
    markdown = "\n".join(lines)

    # ---- 飞书卡片 ----
    body = []
    if quote:
        body.append(f"**行情**：{quote.price:g}{chg}")
    if take:
        body.append(f"**AI 点评**：{take}")
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(body)}}]

    def _card_list(items: list[NewsItem]) -> str:
        return "\n".join(f"• [{n.title}]({n.url}) {_date(n)}" for n in items)

    if events:
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                         "content": "**📋 重大公告 (8-K)**\n" + _card_list(events)}})
    elements.append({"tag": "hr"})
    elements.append({"tag": "div", "text": {"tag": "lark_md",
                     "content": "**📰 近期新闻**\n" + (_card_list(news) or "（无）")}})
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
    quote, events, news = gather(settings, ticker)
    take = ai_take(settings, ticker, quote, events, news)
    msg = build_message(ticker, quote, events, news, take)
    if push:
        from .notifiers.registry import build_notifiers

        for n in build_notifiers(settings):
            n.send(msg)
    return msg
