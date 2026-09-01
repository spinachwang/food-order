"""LLM provider factory — single source of truth for which provider the app uses.

`get_llm_provider()` returns a cached singleton. To swap providers in future
(deepseek / openai / anthropic), add a key to `Settings` and select on it here.
Tests override this singleton via `app.dependency_overrides` or by patching
`get_llm_provider` directly.
"""
from __future__ import annotations

from functools import lru_cache

from app.agents.llm.base import LLMProvider
from app.agents.llm.minimax import MiniMaxProvider
from app.core.config import Settings, get_settings


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """Build (once) and return the active LLM provider from settings."""
    settings = get_settings()
    return _build_provider(settings)


def _build_provider(settings: Settings) -> LLMProvider:
    return MiniMaxProvider(
        api_key=settings.minimax_api_key,
        base_url=settings.minimax_base_url,
        model=settings.minimax_model,
        timeout=settings.minimax_timeout_seconds,
        max_retries=settings.minimax_max_retries,
        thinking=settings.minimax_thinking,
    )


def reset_llm_provider_cache() -> None:
    """For tests that mutate settings and need a fresh provider."""
    get_llm_provider.cache_clear()
