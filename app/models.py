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
