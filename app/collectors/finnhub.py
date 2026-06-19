"""Finnhub 市场新闻采集器（需 FINNHUB_API_KEY）。

无 key 时 registry 会跳过本源，因此免费 RSS 用户零配置也能跑通。
免费额度文档：https://finnhub.io/docs/api/market-news
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..config import Settings
from ..models import NewsItem
from .base import Collector

_BASE = "https://finnhub.io/api/v1/news"
_COMPANY = "https://finnhub.io/api/v1/company-news"


def company_news(
    client: httpx.Client, settings: Settings, symbol: str, days: int
) -> list[NewsItem]:
    """单只个股最近 days 天的新闻（brief 命令用）。无 key 时返回空。"""
    api_key = settings.env("FINNHUB_API_KEY")
    if not api_key:
        return []
    today = datetime.now(timezone.utc).date()
    resp = client.get(
        _COMPANY,
        params={
            "symbol": symbol.upper(),
            "from": str(today - timedelta(days=days)),
            "to": str(today),
            "token": api_key,
        },
    )
    resp.raise_for_status()
    items: list[NewsItem] = []
    for row in resp.json():
        title = (row.get("headline") or "").strip()
        url = (row.get("url") or "").strip()
        if not title or not url:
            continue
        ts = row.get("datetime")
        items.append(
            NewsItem(
                source=f"Finnhub:{symbol.upper()}",
                topic="events",
                title=title,
                url=url,
                summary=(row.get("summary") or "")[:600],
                published_at=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
            )
        )
    return items


class FinnhubNewsCollector(Collector):
    type = "finnhub_news"

    def _fetch(self, client: httpx.Client) -> list[NewsItem]:
        api_key = self.settings.env("FINNHUB_API_KEY")
        if not api_key:
            # 理论上 registry 已过滤；这里再兜一层，避免误带空 key 请求。
            return []
        category = self.source.category or "general"
        resp = client.get(
            _BASE, params={"category": category, "token": api_key}
        )
        resp.raise_for_status()

        items: list[NewsItem] = []
        for row in resp.json():
            title = (row.get("headline") or "").strip()
            url = (row.get("url") or "").strip()
            if not title or not url:
                continue
            ts = row.get("datetime")
            published = (
                datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            )
            items.append(
                NewsItem(
                    source=self.source.name,
                    topic=self.source.topic,
                    title=title,
                    url=url,
                    summary=(row.get("summary") or "")[:600],
                    published_at=published,
                )
            )
        return items
