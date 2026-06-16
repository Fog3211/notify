"""共享的 httpx.Client 构造。

用浏览器式 User-Agent：不少新闻站（CNBC/Yahoo 等）会对非浏览器 UA 返回
403/429，伪装成常见浏览器能显著提高 RSS 抓取成功率。
"""

from __future__ import annotations

import httpx

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def make_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={
            "User-Agent": _BROWSER_UA,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
