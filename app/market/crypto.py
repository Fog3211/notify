"""主流币行情采集，免 key。

主源 CoinGecko（全球可用，含 24h 涨跌幅与成交额，一次请求拿全部）；失败退回
Binance（symbol 直取）。产出与股票相同的 Quote，从而复用同一套异动检测/渲染。

加密 24/7 交易，不需要交易时段门控；prev_close 用「24h 前价格」反推，使 Quote
的 change_pct 自然表示 24h 涨跌幅。
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import Settings
from ..models import Quote

log = logging.getLogger("crypto")

# 主流币 -> CoinGecko id（user 只要主流，固定一张小表即可）
_CG_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "DOGE": "dogecoin", "ADA": "cardano", "AVAX": "avalanche-2",
    "LINK": "chainlink", "TRX": "tron", "DOT": "polkadot", "LTC": "litecoin",
}


def _prev_from_pct(price: float, pct: float | None) -> float | None:
    """由最新价与涨跌幅(%)反推基准价，使 Quote.change_pct == pct。"""
    return price / (1 + pct / 100.0) if pct is not None else None


def _coingecko(client: httpx.Client, symbols: list[str]) -> list[Quote]:
    pairs = [(s, _CG_IDS[s]) for s in symbols if s in _CG_IDS]
    if not pairs:
        return []
    resp = client.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": ",".join(cid for _, cid in pairs),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    out: list[Quote] = []
    for sym, cid in pairs:
        d = data.get(cid)
        if not d or d.get("usd") is None:
            continue
        price = float(d["usd"])
        pct = d.get("usd_24h_change")
        vol = d.get("usd_24h_vol")
        out.append(
            Quote(
                symbol=sym,
                price=price,
                prev_close=_prev_from_pct(price, pct),
                volume=int(vol) if vol else None,
                source="coingecko",
            )
        )
    return out


def _binance(client: httpx.Client, symbols: list[str]) -> list[Quote]:
    pairs = [f"{s}USDT" for s in symbols]
    resp = client.get(
        "https://api.binance.com/api/v3/ticker/24hr",
        params={"symbols": json.dumps(pairs, separators=(",", ":"))},
    )
    resp.raise_for_status()
    out: list[Quote] = []
    for d in resp.json():
        sym = d["symbol"].removesuffix("USDT")
        price = float(d["lastPrice"])
        pct = float(d["priceChangePercent"])
        out.append(
            Quote(
                symbol=sym,
                price=price,
                prev_close=_prev_from_pct(price, pct),
                volume=int(float(d.get("quoteVolume", 0))) or None,
                source="binance",
            )
        )
    return out


def fetch_crypto_quotes(settings: Settings, symbols: list[str], client: httpx.Client) -> list[Quote]:
    """拉取主流币行情；主源失败自动切兜底。"""
    if not symbols:
        return []
    for fetch in (_coingecko, _binance):
        try:
            quotes = fetch(client, symbols)
            if quotes:
                log.info("币圈行情：%d/%d 成功（%s）", len(quotes), len(symbols), fetch.__name__)
                return quotes
        except Exception as exc:
            log.warning("币圈行情源 %s 失败：%s", fetch.__name__, exc)
    log.warning("所有币圈行情源均失败")
    return []
