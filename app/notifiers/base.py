"""Notifier 基类。send() 返回是否成功；失败不抛出，多渠道互不影响。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..config import Settings
from ..models import Report

log = logging.getLogger("notifier")


class Notifier(ABC):
    name: str = ""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def _send(self, report: Report) -> None:
        """实际发送，失败抛异常，由 send() 兜底。"""

    def send(self, report: Report) -> bool:
        try:
            self._send(report)
            log.info("渠道 [%s] 推送成功", self.name)
            return True
        except Exception as exc:
            log.error("渠道 [%s] 推送失败：%s", self.name, exc)
            return False
