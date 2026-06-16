"""配置加载：合并 config.yaml（业务）+ .env（密钥）。

设计原则：业务配置可入库、密钥只在环境变量。两者在此汇合成强类型对象，
其余模块只依赖这里的 Settings，不直接读 yaml/env。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ScheduleCfg(BaseModel):
    timezone: str = "Asia/Shanghai"
    daily_at: str = "07:00"
    intraday_every_minutes: int = 60


class LLMCfg(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.3
    max_tokens: int = 4096


class SourceCfg(BaseModel):
    name: str
    type: str                        # rss | finnhub_news | ...
    topic: str
    url: str | None = None
    category: str | None = None


class ProcessingCfg(BaseModel):
    lookback_hours: int = 30
    max_items_per_topic: int = 15
    dedup_db: str = "data/seen.sqlite"
    dedup_retention_days: int = 14


class MoversCfg(BaseModel):
    daily_threshold_pct: float = 5.0
    hourly_threshold_pct: float = 3.0
    volume_multiple: float = 3.0
    cooldown_hours: int = 4


class MarketCfg(BaseModel):
    enabled: bool = False
    source: str = "yahoo"            # yahoo（主）| stooq（兜底）
    snapshot_db: str = "data/market.sqlite"
    movers: MoversCfg = Field(default_factory=MoversCfg)


class NotifierToggle(BaseModel):
    enabled: bool = False
    template: str | None = None


class NotifiersCfg(BaseModel):
    feishu: NotifierToggle = Field(default_factory=NotifierToggle)
    pushplus: NotifierToggle = Field(default_factory=NotifierToggle)
    serverchan: NotifierToggle = Field(default_factory=NotifierToggle)


class ReportCfg(BaseModel):
    title: str = "每日简报"
    show_stats: bool = True


class Settings(BaseModel):
    schedule: ScheduleCfg = Field(default_factory=ScheduleCfg)
    llm: LLMCfg = Field(default_factory=LLMCfg)
    sources: list[SourceCfg] = Field(default_factory=list)
    watchlist: dict[str, list[str]] = Field(default_factory=dict)
    market: MarketCfg = Field(default_factory=MarketCfg)
    processing: ProcessingCfg = Field(default_factory=ProcessingCfg)
    notifiers: NotifiersCfg = Field(default_factory=NotifiersCfg)
    report: ReportCfg = Field(default_factory=ReportCfg)

    def env(self, key: str) -> str | None:
        """读取环境变量；集中一处便于测试时 monkeypatch。"""
        val = os.getenv(key)
        return val.strip() if val else None

    def dedup_db_path(self) -> Path:
        p = Path(self.processing.dedup_db)
        return p if p.is_absolute() else PROJECT_ROOT / p

    def snapshot_db_path(self) -> Path:
        p = Path(self.market.snapshot_db)
        return p if p.is_absolute() else PROJECT_ROOT / p

    def all_tickers(self) -> list[str]:
        """watchlist 去重后的全部标的，作为给 AI 的上下文。"""
        seen: list[str] = []
        for group in self.watchlist.values():
            for t in group:
                if t not in seen:
                    seen.append(t)
        return seen


def load_settings(config_path: str | os.PathLike | None = None) -> Settings:
    """加载配置。先 load .env，再读 yaml，最后构造强类型 Settings。"""
    load_dotenv(PROJECT_ROOT / ".env")
    path = Path(config_path) if config_path else PROJECT_ROOT / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Settings(**raw)
