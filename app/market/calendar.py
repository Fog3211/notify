"""财报日历（Finnhub，免费档）。

让每日简报带上「关注列表里哪些票近期财报」，提前知道催化点。
经济日历（Fed/CPI）是 Finnhub 付费资源，免费档拿不到，暂不做。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from ..config import Settings

log = logging.getLogger("calendar")

_EARNINGS = "https://finnhub.io/api/v1/calendar/earnings"
_HOUR = {"bmo": "盘前", "amc": "盘后", "dmh": "盘中"}


def upcoming_earnings(client: httpx.Client, settings: Settings, days: int) -> list[str]:
    """返回关注列表里未来 days 天的财报安排，如 ["NVDA 2026-06-25 盘后"]。"""
    key = settings.env("FINNHUB_API_KEY")
    if not key:
        return []
    watch = {t.upper() for t in settings.all_tickers()}
    today = date.today()
    try:
        resp = client.get(
            _EARNINGS,
            params={"from": str(today), "to": str(today + timedelta(days=days)), "token": key},
        )
        resp.raise_for_status()
    except Exception as exc:   # 日历失败不应拖垮简报
        log.warning("财报日历拉取失败：%s", exc)
        return []

    out: set[str] = set()
    for e in resp.json().get("earningsCalendar", []):
        sym = (e.get("symbol") or "").upper()
        if sym not in watch:
            continue
        hour = _HOUR.get(e.get("hour", ""), "")
        out.add(f"{sym} {e.get('date', '')} {hour}".strip())
    return sorted(out)
