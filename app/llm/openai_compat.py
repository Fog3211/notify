"""OpenAI 兼容客户端：覆盖 OpenAI / DeepSeek / 通义千问(DashScope) 等。

它们都用 /chat/completions 同款协议，差别只在 base_url、model 与 api_key，
因此一个类靠 base_url 即可复用。
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import LLMClient, LLMError


class OpenAICompatClient(LLMClient):
    def __init__(self, *, api_key: str, base_url: str, **kw) -> None:
        super().__init__(**kw)
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"

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
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=120,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM API {exc.response.status_code}: {exc.response.text[:200]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
