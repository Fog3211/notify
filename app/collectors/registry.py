"""把 config 里的 sources 实例化成具体 collector，并做可用性预检。

预检的意义：缺 key 的 API 源在这里就被跳过（带提示），不会进入运行期才报错。
新增数据源类型只需在 _TYPES 注册一行。
"""

from __future__ import annotations

import logging

from ..config import Settings
from .base import Collector
from .finnhub import FinnhubNewsCollector
from .rss import RSSCollector

log = logging.getLogger("collector")

# source.type -> (Collector 类, 需要的 env key 或 None)
_TYPES: dict[str, tuple[type[Collector], str | None]] = {
    RSSCollector.type: (RSSCollector, None),
    FinnhubNewsCollector.type: (FinnhubNewsCollector, "FINNHUB_API_KEY"),
}


def build_collectors(settings: Settings) -> list[Collector]:
    collectors: list[Collector] = []
    for src in settings.sources:
        entry = _TYPES.get(src.type)
        if entry is None:
            log.warning("未知数据源类型 '%s'（源 %s），已跳过", src.type, src.name)
            continue
        cls, required_key = entry
        if required_key and not settings.env(required_key):
            log.info("源 [%s] 缺少 %s，跳过", src.name, required_key)
            continue
        collectors.append(cls(src, settings))
    return collectors
