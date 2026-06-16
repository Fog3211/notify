"""飞书自定义机器人 webhook。支持「签名校验」（配置了 secret 时自动加签）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import httpx

from ..models import Report
from .base import Notifier
from .render import render_feishu_card


def _gen_sign(secret: str, timestamp: int) -> str:
    """飞书加签：sign = base64(hmac_sha256(key=f"{ts}\\n{secret}", msg=""))。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class FeishuNotifier(Notifier):
    name = "feishu"

    def _send(self, report: Report) -> None:
        url = self.settings.env("FEISHU_WEBHOOK_URL")
        if not url:
            raise RuntimeError("缺少 FEISHU_WEBHOOK_URL")

        payload: dict = {
            "msg_type": "interactive",
            "card": render_feishu_card(report, self.settings.report.show_stats),
        }

        # 开启签名校验的机器人需带 timestamp + sign
        secret = self.settings.env("FEISHU_WEBHOOK_SECRET")
        if secret:
            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = _gen_sign(secret, ts)

        resp = httpx.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        # 飞书即使 HTTP 200 也可能返回业务错误码，需校验 body.code
        body = resp.json()
        if body.get("code", 0) not in (0, None):
            raise RuntimeError(f"飞书返回错误: {body}")
