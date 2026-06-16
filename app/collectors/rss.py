"""RSS/Atom 采集器。无需 API key，是默认主力数据源。"""

from __future__ import annotations

from datetime import datetime, timezone
from time import struct_time

import feedparser
import httpx

from ..models import NewsItem
from .base import Collector


def _parse_time(entry) -> datetime | None:
    """feedparser 把时间解析成 struct_time(UTC)；转成 aware datetime。"""
    tm: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    if not tm:
        return None
    return datetime(*tm[:6], tzinfo=timezone.utc)


def _clean(text: str) -> str:
    """去掉摘要里的 HTML 标签噪音，喂给 AI 更省 token。"""
    import re

    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


class RSSCollector(Collector):
    type = "rss"

    def _fetch(self, client: httpx.Client) -> list[NewsItem]:
        # 用 httpx 取原始字节（统一超时/UA），再交给 feedparser 解析。
        resp = client.get(self.source.url, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        items: list[NewsItem] = []
        for entry in feed.entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            summary = _clean(entry.get("summary", ""))[:600]
            items.append(
                NewsItem(
                    source=self.source.name,
                    topic=self.source.topic,
                    title=title,
                    url=link,
                    summary=summary,
                    published_at=_parse_time(entry),
                )
            )
        return items
