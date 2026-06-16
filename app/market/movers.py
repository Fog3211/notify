"""暴涨暴跌异动检测（纯规则，无需 LLM）。

按三种口径判定，每个标的最多产出一条告警（按优先级 daily > hourly > volume 取一），
reason 汇总所有触发口径。冷却去重在 pipeline 层结合 SnapshotStore 完成。
"""

from __future__ import annotations

from ..config import MoversCfg
from ..models import MoverAlert, Quote


def _fmt_pct(p: float) -> str:
    return f"{'涨' if p >= 0 else '跌'} {abs(p):.1f}%"


def detect(
    quotes: list[Quote],
    last_prices: dict[str, float],
    cfg: MoversCfg,
) -> list[MoverAlert]:
    """对一批行情做异动判定，返回告警列表（未做冷却过滤）。"""
    alerts: list[MoverAlert] = []
    for q in quotes:
        triggered: list[tuple[str, float, str]] = []  # (window, change_pct, reason)

        # 1) 日内涨跌幅（相对前收）
        daily = q.change_pct
        if daily is not None and abs(daily) >= cfg.daily_threshold_pct:
            triggered.append(("daily", daily, f"日内{_fmt_pct(daily)}"))

        # 2) 小时涨跌幅（相对上一次快照）
        last = last_prices.get(q.symbol)
        if last and last > 0:
            hourly = (q.price - last) / last * 100.0
            if abs(hourly) >= cfg.hourly_threshold_pct:
                triggered.append(("hourly", hourly, f"近一时段{_fmt_pct(hourly)}"))

        # 3) 量能异常（成交量 vs 10 日均量）
        if q.volume and q.avg_volume and q.avg_volume > 0:
            ratio = q.volume / q.avg_volume
            if ratio >= cfg.volume_multiple:
                # 量能异动的「涨跌幅」取日内值（无则 0），方便展示方向
                vol_pct = daily if daily is not None else 0.0
                triggered.append(("volume", vol_pct, f"成交量达 10 日均量 {ratio:.1f}×"))

        if not triggered:
            continue

        # 每标的取优先级最高的口径作为主告警，reason 汇总全部
        priority = {"daily": 0, "hourly": 1, "volume": 2}
        triggered.sort(key=lambda t: priority[t[0]])
        window, change_pct, _ = triggered[0]
        reason = "；".join(t[2] for t in triggered)
        alerts.append(
            MoverAlert(
                symbol=q.symbol,
                window=window,
                change_pct=round(change_pct, 2),
                price=q.price,
                reason=reason,
            )
        )

    # 按涨跌幅绝对值排序，最猛的在前
    alerts.sort(key=lambda a: abs(a.change_pct), reverse=True)
    return alerts
