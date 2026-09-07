"""LLM provider abstract base class (F003 §8.1, Phase 1 of M1).

`LLMProvider` is an ABC — concrete implementations (currently only `MiniMaxProvider`)
inherit from it and implement `complete`. The async context manager protocol
(`__aenter__` / `__aexit__` / `aclose`) lets callers safely share a long-lived
`httpx.AsyncClient` across requests without leaking connections.

Streaming (`stream()`) is intentionally NOT part of this Phase 1 ABC — cuisine
expert outputs are JSON and must be parsed in one shot per F003 §3.3. SSE
streaming belongs to F004 / F040 and will be added when those features ship.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self

from app.agents.llm.types import ChatRequest, ChatResponse


class LLMProvider(ABC):
    """Abstract base for chat completion providers."""

    model: str
    timeout: float
    max_retries: int

    @abstractmethod
    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Send `messages` to the underlying model and return a single `ChatResponse`.

        Implementations should:
        - Retry transport-level errors (5xx, 429, timeout) up to `max_retries`
          times with exponential backoff.
        - Map HTTP 401 to `LLMAuthError`, 429 to `LLMRateLimitError`,
          timeout to `LLMTimeoutError`, malformed payloads to `LLMResponseError`.
        """
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release any underlying resources (HTTP client, etc.). Default = no-op."""
        return None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()
