"""PushPlus（推送加）—— 推到个人微信。文档：http://www.pushplus.plus"""

from __future__ import annotations

import httpx

from .base import Notifier
from .message import Message

_API = "http://www.pushplus.plus/send"


class PushPlusNotifier(Notifier):
    name = "pushplus"

    def _send(self, msg: Message) -> None:
        token = self.settings.env("PUSHPLUS_TOKEN")
        if not token:
            raise RuntimeError("缺少 PUSHPLUS_TOKEN")

        template = self.settings.notifiers.pushplus.template or "markdown"

        resp = httpx.post(
            _API,
            json={
                "token": token,
                "title": msg.title,
                "content": msg.markdown,
                "template": template,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        # PushPlus 成功 code=200
        if body.get("code") != 200:
            raise RuntimeError(f"PushPlus 返回错误: {body}")
