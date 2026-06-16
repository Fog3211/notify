"""美股行情采集，免 key。

主源 CNBC 报价接口（字段丰富，含 10 日均量，可用于量能异常判断），
单个标的失败时退回 Nasdaq 接口。两者都是公开 JSON，无需密钥。
每标的一次请求、并发拉取；单标的失败只跳过，不影响其他。

注：免费源约 15 分钟延迟，仅用于看趋势 / 找异动，不做高频交易。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import httpx

from ..config import Settings
from ..models import Quote

log = logging.getLogger("market")

_CNBC = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
_NASDAQ = "https://api.nasdaq.com/api/quote/{symbol}/info"


def _to_float(s) -> float | None:
    if s is None:
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", "").replace("+", "").strip())
    except (ValueError, TypeError):
        return None


def _to_int(s) -> int | None:
    f = _to_float(s)
    return int(f) if f is not None else None


def _cnbc_quote(client: httpx.Client, symbol: str) -> Quote | None:
    resp = client.get(
        _CNBC,
        params={"symbols": symbol, "requestMethod": "itv", "exthrs": "1", "fund": "1", "output": "json"},
    )
    resp.raise_for_status()
    quotes = resp.json().get("FormattedQuoteResult", {}).get("FormattedQuote", [])
    if not quotes:
        return None
    q = quotes[0]
    price = _to_float(q.get("last"))
    if price is None:
        return None  # 无报价（停牌/代码错误）
    return Quote(
        symbol=symbol,
        price=price,
        prev_close=_to_float(q.get("previous_day_closing")),
        volume=_to_int(q.get("volume")),
        avg_volume=_to_int(q.get("tendayavgvol")),
        source="cnbc",
    )


def _nasdaq_quote(client: httpx.Client, symbol: str) -> Quote | None:
    resp = client.get(
        _NASDAQ.format(symbol=symbol),
        params={"assetclass": "stocks"},
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    pd = (resp.json().get("data") or {}).get("primaryData") or {}
    price = _to_float(pd.get("lastSalePrice"))
    if price is None:
        return None
    net = _to_float(pd.get("netChange"))
    # Nasdaq 不直接给前收，用 最新价 - 涨跌额 反推
    prev_close = (price - net) if net is not None else None
    return Quote(
        symbol=symbol,
        price=price,
        prev_close=prev_close,
        volume=_to_int(pd.get("volume")),
        avg_volume=None,
        source="nasdaq",
    )


def _one(client: httpx.Client, symbol: str) -> Quote | None:
    """单标的：主源失败退回兜底；都失败返回 None。"""
    for fetch in (_cnbc_quote, _nasdaq_quote):
        try:
            q = fetch(client, symbol)
            if q is not None:
                return q
        except Exception as exc:
            log.debug("行情源 %s 拉取 %s 失败：%s", fetch.__name__, symbol, exc)
    log.warning("标的 %s 所有行情源均失败", symbol)
    return None


def fetch_quotes(settings: Settings, symbols: list[str], client: httpx.Client) -> list[Quote]:
    """并发拉取 symbols 的最新行情。"""
    if not symbols:
        return []
    with ThreadPoolExecutor(max_workers=min(12, len(symbols))) as pool:
        results = pool.map(lambda s: _one(client, s), symbols)
    quotes = [q for q in results if q is not None]
    log.info("行情采集：%d/%d 个标的成功", len(quotes), len(symbols))
    return quotes
