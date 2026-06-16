"""渠道无关的消息载体。

把「渲染」和「发送」解耦：render 层把 Report / 异动告警渲染成 Message，
notifier 层只管把 Message 发到各渠道。每日简报与盘中速报共用同一发送路径。
"""

from __future__ import annotations

from pydantic import BaseModel


class Message(BaseModel):
    title: str
    markdown: str          # PushPlus / Server酱 用
    feishu_card: dict      # 飞书交互卡片的 card 部分
