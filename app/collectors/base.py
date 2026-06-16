"""Collector 基类。

约定：collect() 不抛异常到管道层 —— 单个源失败只记录并返回空列表，
保证「一个源挂了不拖垮整条管道」。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from ..config import Settings, SourceCfg
from ..models import NewsItem

log = logging.getLogger("collector")


class Collector(ABC):
    type: str = ""   # 子类声明，用于 registry 匹配 SourceCfg.type

    def __init__(self, source: SourceCfg, settings: Settings) -> None:
        self.source = source
        self.settings = settings

    @abstractmethod
    def _fetch(self, client: httpx.Client) -> list[NewsItem]:
        """实际抓取逻辑，由子类实现。异常向上抛，由 collect() 兜底。"""

    def collect(self, client: httpx.Client) -> list[NewsItem]:
        try:
            items = self._fetch(client)
            log.info("源 [%s] 采集到 %d 条", self.source.name, len(items))
            return items
        except Exception as exc:  # 单源容错：记录但不中断
            log.warning("源 [%s] 采集失败：%s", self.source.name, exc)
            return []
