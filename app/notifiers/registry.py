"""按 config.notifiers 的开关构造启用的 notifier 列表。"""

from __future__ import annotations

import logging

from ..config import Settings
from .base import Notifier
from .feishu import FeishuNotifier
from .pushplus import PushPlusNotifier
from .serverchan import ServerChanNotifier

log = logging.getLogger("notifier")

_TYPES: dict[str, type[Notifier]] = {
    "feishu": FeishuNotifier,
    "pushplus": PushPlusNotifier,
    "serverchan": ServerChanNotifier,
}


def build_notifiers(settings: Settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    toggles = settings.notifiers
    for name, cls in _TYPES.items():
        toggle = getattr(toggles, name)
        if toggle.enabled:
            notifiers.append(cls(settings))
    if not notifiers:
        log.warning("未启用任何推送渠道，报告只会打印到日志")
    return notifiers
