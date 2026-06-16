"""根据 config.llm.provider 构造对应 LLMClient。

新增 provider：在 _PROVIDERS 注册一行（env key + base_url + 协议类型）即可，
切换只需改 config.yaml 的 llm.provider / llm.model。
"""

from __future__ import annotations

from ..config import Settings
from .anthropic_client import AnthropicClient
from .base import LLMClient, LLMError
from .openai_compat import OpenAICompatClient

# provider -> (env_key, base_url, kind)
# kind: "anthropic" 用自有协议；"openai" 用 OpenAI 兼容协议。
_PROVIDERS: dict[str, tuple[str, str | None, str]] = {
    "anthropic": ("ANTHROPIC_API_KEY", None, "anthropic"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1", "openai"),
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "openai"),
    "dashscope": (
        "DASHSCOPE_API_KEY",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "openai",
    ),
}


def build_llm(settings: Settings) -> LLMClient:
    cfg = settings.llm
    entry = _PROVIDERS.get(cfg.provider)
    if entry is None:
        raise LLMError(
            f"未知 LLM provider '{cfg.provider}'，可选: {', '.join(_PROVIDERS)}"
        )
    env_key, base_url, kind = entry
    api_key = settings.env(env_key)
    if not api_key:
        raise LLMError(f"provider '{cfg.provider}' 需要环境变量 {env_key}，但未设置")

    common = dict(
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
    if kind == "anthropic":
        return AnthropicClient(api_key=api_key, base_url=base_url, **common)
    return OpenAICompatClient(api_key=api_key, base_url=base_url, **common)
