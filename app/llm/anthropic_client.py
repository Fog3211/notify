"""Anthropic Claude 客户端（Messages API，直连 httpx，无需 SDK）。"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import LLMClient, LLMError

_API = "https://api.anthropic.com/v1/messages"
_VERSION = "2023-06-01"


class AnthropicClient(LLMClient):
    def __init__(self, *, api_key: str, base_url: str | None = None, **kw) -> None:
        super().__init__(**kw)
        self._api_key = api_key
        self._url = (base_url.rstrip("/") + "/v1/messages") if base_url else _API

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    def chat(self, system: str, user: str) -> str:
        try:
            resp = httpx.post(
                self._url,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": _VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=120,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # 4xx 多为鉴权/模型名错误，重试无意义 —— 直接转 LLMError。
            raise LLMError(f"Anthropic API {exc.response.status_code}: {exc.response.text[:200]}")
        data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []))
