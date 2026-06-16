"""Server酱 Turbo —— 推到个人微信。文档：https://sct.ftqq.com"""

from __future__ import annotations

import httpx

from .base import Notifier
from .message import Message


class ServerChanNotifier(Notifier):
    name = "serverchan"

    def _send(self, msg: Message) -> None:
        sendkey = self.settings.env("SERVERCHAN_SENDKEY")
        if not sendkey:
            raise RuntimeError("缺少 SERVERCHAN_SENDKEY")

        # Server酱 Turbo 的端点由 SendKey 拼出
        url = f"https://sctapi.ftqq.com/{sendkey}.send"

        resp = httpx.post(
            url,
            data={"title": msg.title, "desp": msg.markdown},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        # Server酱成功 code=0
        if body.get("code") not in (0, None):
            raise RuntimeError(f"Server酱返回错误: {body}")
