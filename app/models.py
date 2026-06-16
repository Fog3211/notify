"""贯穿整条管道的数据模型。

采集 -> 去重 -> 分析 -> 渲染 都围绕这几个对象流转，保持单一数据形状，
避免各模块各自用 dict 导致字段漂移。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """一条标准化后的资讯。不同 collector 的原始结构都收敛到这里。"""

    source: str                      # 数据源名称（config 里的 source.name）
    topic: str                       # 主题分组：ai / us_tech / finance / semiconductor ...
    title: str
    url: str
    summary: str = ""                # 原文摘要/正文片段（可能为空）
    published_at: datetime | None = None

    @property
    def fingerprint(self) -> str:
        """去重指纹。优先用 URL（最稳定），URL 缺失时退回标题。

        用归一化后的串做 sha1，确保同一条新闻在多次运行间指纹一致。
        """
        basis = (self.url or self.title).strip().lower()
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    @property
    def age_hours(self) -> float | None:
        """距今小时数；published_at 缺失时返回 None（交由调用方决定是否保留）。"""
        if self.published_at is None:
            return None
        now = datetime.now(timezone.utc)
        pub = self.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return (now - pub).total_seconds() / 3600.0


class Quote(BaseModel):
    """一条美股行情快照。不同行情源（Yahoo / Stooq）都收敛到这里。"""

    symbol: str
    price: float                     # 最新价（免费源约 15 分钟延迟）
    prev_close: float | None = None  # 前收盘价，用于算日内涨跌幅
    volume: int | None = None
    avg_volume: int | None = None    # 历史均量，用于量能异常判断（可能为空）
    source: str = "yahoo"

    @property
    def change_pct(self) -> float | None:
        """日内涨跌幅(%)。prev_close 缺失或为 0 时返回 None。"""
        if not self.prev_close:
            return None
        return (self.price - self.prev_close) / self.prev_close * 100.0


class MoverAlert(BaseModel):
    """一条异动告警。由规则检测产出，可叠加 AI 归因。"""

    symbol: str
    window: str                      # daily | hourly | volume —— 触发口径
    change_pct: float                # 触发时的涨跌幅(%)（量能异动时为日内涨跌幅）
    price: float
    reason: str = ""                 # 一句话说明（规则文案，或 AI 归因）

    @property
    def direction(self) -> str:
        """up / down —— 与冷却去重的「同方向」判断一致。"""
        return "up" if self.change_pct >= 0 else "down"

    @property
    def cooldown_key(self) -> str:
        """冷却去重键：同标的同方向同口径在冷却期内只推一次。"""
        return f"{self.symbol}:{self.window}:{self.direction}"


class TopicAnalysis(BaseModel):
    """AI 对单个主题的分析结论。"""

    topic: str
    headline: str                    # 一句话概括今日该主题最关键的事
    bullets: list[str] = Field(default_factory=list)   # 要点（已含影响判断）
    sentiment: str = "neutral"       # bullish / bearish / neutral / mixed
    tickers: list[str] = Field(default_factory=list)   # 涉及的相关标的


class Report(BaseModel):
    """一次完整运行产出的报告，交给各 notifier 渲染。"""

    title: str
    generated_at: datetime
    analyses: list[TopicAnalysis] = Field(default_factory=list)
    overview: str = ""               # 跨主题的全局综述（可选）
    stats: dict[str, int] = Field(default_factory=dict)   # topic -> 入选条数

    @property
    def is_empty(self) -> bool:
        return not self.analyses
