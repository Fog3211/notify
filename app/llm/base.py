"""LLM 客户端统一接口。

各 provider 协议不同（Anthropic 自有格式 / OpenAI 兼容格式），但对管道只暴露
一个 chat(system, user) -> str。切 provider 不影响 analyzer。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        """单轮对话，返回纯文本。实现内部负责鉴权、超时与重试。"""


class LLMError(RuntimeError):
    """LLM 调用失败（鉴权/网络/配额）。analyzer 据此决定是否降级。"""
