"""MiniMax-M3 provider — OpenAI-compatible chat completions over httpx.

Endpoint:    POST {base_url}/chat/completions
Auth:        `Authorization: Bearer {api_key}`
Model field: `MiniMax-M3` (configurable via settings, default per F003 §8.1)
Thinking:    `{"type": "<mode>"}` per MiniMax-M3 docs; default `disabled`.

Transport-level retry handles:
  - HTTP 5xx (server errors) — retryable
  - HTTP 429 (rate limit)   — retryable with exponential backoff
  - Timeout / connect error — retryable

Other errors raise `DomainError` subclasses from `app.core.exceptions` and are
caught by the global handler in `app.main`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast

import httpx

from app.agents._observability import instrument_llm_call
from app.agents.llm.base import LLMProvider
from app.agents.llm.types import ChatRequest, ChatResponse, ChatResponseUsage
from app.core.exceptions import (
    LLMAuthError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_BACKOFF_BASE_SECONDS = 0.5


class MiniMaxProvider(LLMProvider):
    """OpenAI-compatible provider for MiniMax-M3 (and any other MiniMax model)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float,
        max_retries: int,
        thinking: str = "disabled",
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._thinking = thinking
        self._client: httpx.AsyncClient | None = None

    # ----- LLMProvider -----

    @instrument_llm_call
    async def complete(self, request: ChatRequest) -> ChatResponse:
        if not self._api_key:
            raise LLMAuthError(
                "MINIMAX_API_KEY 未配置",
                details={"hint": "在 .env 中填入 MiniMax 控制台签发的 API key"},
            )

        client = await self._get_client()
        body = self._build_body(request)
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(url, json=body, headers=headers)
            except httpx.TimeoutException as exc:
                last_error = LLMTimeoutError(f"MiniMax 请求超时 ({self.timeout}s)")
                logger.warning("MiniMax timeout (attempt %d/%d): %s", attempt + 1, self.max_retries + 1, exc)
                await self._sleep_backoff(attempt)
                continue
            except httpx.HTTPError as exc:
                # Network-level failure → treat as transient within retry budget.
                last_error = LLMResponseError(f"MiniMax 网络错误: {exc}")
                logger.warning("MiniMax HTTP error (attempt %d): %s", attempt + 1, exc)
                await self._sleep_backoff(attempt)
                continue

            if response.status_code == 200:
                return self._parse_response(response.json())

            # Non-2xx — distinguish auth / rate-limit / transient / permanent.
            if response.status_code == 401:
                raise LLMAuthError("MiniMax 鉴权失败 (401)", details={"hint": "检查 MINIMAX_API_KEY"})

            if response.status_code == 429 or response.status_code in _RETRYABLE_STATUSES:
                last_error = LLMRateLimitError(
                    f"MiniMax 返回 {response.status_code}",
                    details={"body": _safe_json(response)},
                )
                logger.warning(
                    "MiniMax transient status %d (attempt %d/%d)",
                    response.status_code,
                    attempt + 1,
                    self.max_retries + 1,
                )
                await self._sleep_backoff(attempt)
                continue

            # Permanent failure (4xx other than 401/429).
            raise LLMResponseError(
                f"MiniMax 返回 {response.status_code}",
                details={"body": _safe_json(response)},
            )

        # Retries exhausted.
        assert last_error is not None  # for type checker
        raise last_error

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ----- internals -----

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    def _build_body(self, request: ChatRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": list(request["messages"]),
        }
        if request.get("temperature") is not None:
            body["temperature"] = request["temperature"]
        if request.get("max_tokens") is not None:
            body["max_tokens"] = request["max_tokens"]
        if request.get("top_p") is not None:
            body["top_p"] = request["top_p"]
        # `thinking` is provider-specific; MiniMax-M3 supports it.
        body["thinking"] = {"type": self._thinking}
        return body

    @staticmethod
    def _parse_response(payload: dict[str, Any]) -> ChatResponse:
        try:
            choices = payload["choices"]
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                "MiniMax 响应缺少 choices[0].message.content",
                details={"payload": payload},
            ) from exc

        usage_raw = payload.get("usage")
        usage: ChatResponseUsage | None = None
        if isinstance(usage_raw, dict):
            coerced: dict[str, int] = {
                str(k): int(v)
                for k, v in usage_raw.items()
                if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and isinstance(v, (int, float))
            }
            usage = cast(ChatResponseUsage, coerced) if coerced else None

        return {
            "content": content,
            "model": str(payload.get("model", "")),
            "usage": usage,
        }

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        if attempt < 0:
            return
        delay = _BACKOFF_BASE_SECONDS * (2**attempt)
        await asyncio.sleep(delay)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text[:500]
