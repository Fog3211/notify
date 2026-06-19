"""SEC EDGAR 8-K 重大事件采集器（免 key）。

8-K 是美股公司发生重大事件（并购、业绩、高管变动、退市、重大协议等）时必须当场
向 SEC 申报的表格，EDGAR 近实时分发。这是「大事件、立刻能查」最权威的免费源。

SEC 要求请求带可识别的 User-Agent（含联系方式）；通过环境变量 SEC_USER_AGENT 覆盖。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..config import Settings
from ..models import NewsItem
from .base import Collector

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_DEFAULT_UA = "notify-bot/0.1 finance-news (contact: configure SEC_USER_AGENT)"

# 8-K 条目代码 -> 中文事件类型（只列常见的；未知代码原样保留）
_ITEM_LABELS = {
    "1.01": "签订重大协议",
    "1.02": "终止重大协议",
    "1.03": "破产/接管",
    "2.01": "完成收购/资产处置",
    "2.02": "业绩/财务结果",
    "2.03": "新增重大债务",
    "2.05": "重组/减值成本",
    "3.01": "退市/上市规则通知",
    "4.01": "更换会计师事务所",
    "4.02": "财报不可依赖",
    "5.02": "高管/董事变动",
    "5.07": "股东投票结果",
    "7.01": "Regulation FD 披露",
    "8.01": "其他重大事件",
}

# 进程内缓存 ticker->CIK，避免每次重拉 10000+ 条映射
_cik_map: dict[str, int] | None = None


def _sec_headers(settings: Settings) -> dict[str, str]:
    return {"User-Agent": settings.env("SEC_USER_AGENT") or _DEFAULT_UA}


def _load_cik_map(client: httpx.Client, settings: Settings) -> dict[str, int]:
    global _cik_map
    if _cik_map is None:
        resp = client.get(_TICKERS_URL, headers=_sec_headers(settings))
        resp.raise_for_status()
        # 结构: {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
        _cik_map = {row["ticker"].upper(): int(row["cik_str"]) for row in resp.json().values()}
    return _cik_map


def _label_items(items: str) -> str:
    """把 '2.02,9.01' 这样的条目代码翻成中文；9.01（附件）无信息量，忽略。"""
    codes = [c.strip() for c in (items or "").split(",") if c.strip() and c.strip() != "9.01"]
    labels = [_ITEM_LABELS.get(c, c) for c in codes]
    return " / ".join(labels) if labels else "重大事件申报"


def recent_8k(
    client: httpx.Client, settings: Settings, tickers: list[str], days: int
) -> list[NewsItem]:
    """拉取 tickers 在最近 days 天内的 8-K，产出 NewsItem(topic=events)。"""
    cik_map = _load_cik_map(client, settings)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items: list[NewsItem] = []

    for ticker in tickers:
        cik = cik_map.get(ticker.upper())
        if cik is None:
            continue
        resp = client.get(_SUBMISSIONS_URL.format(cik=cik), headers=_sec_headers(settings))
        resp.raise_for_status()
        recent = resp.json().get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            stamp = recent.get("acceptanceDateTime", [None] * len(forms))[i]
            published = (
                datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
            )
            if published and published < cutoff:
                continue
            accession = recent["accessionNumber"][i].replace("-", "")
            doc = recent["primaryDocument"][i]
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
            label = _label_items(recent.get("items", [""] * len(forms))[i])
            items.append(
                NewsItem(
                    source="SEC 8-K",
                    topic="events",
                    title=f"{ticker.upper()} 8-K · {label}",
                    url=url,
                    summary=f"{ticker.upper()} 向 SEC 申报 8-K：{label}",
                    published_at=published,
                )
            )
    return items


class SEC8KCollector(Collector):
    type = "sec_8k"

    def _fetch(self, client: httpx.Client) -> list[NewsItem]:
        # 关注列表里的所有美股标的；窗口取 7 天，pipeline 再按 lookback 收窄
        return recent_8k(client, self.settings, self.settings.all_tickers(), days=7)
