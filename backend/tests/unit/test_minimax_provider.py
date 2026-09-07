"""Unit tests for `MiniMaxProvider` — respx mocks the httpx transport."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from app.agents.llm.minimax import MiniMaxProvider
from app.agents.llm.types import ChatRequest
from app.core.exceptions import (
    LLMAuthError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)


def _make_provider(**overrides: object) -> MiniMaxProvider:
    defaults: dict[str, object] = {
        "api_key": "test-key",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M3",
        "timeout": 5.0,
        "max_retries": 0,  # tests run fast — no retry by default
        "thinking": "disabled",
    }
    defaults.update(overrides)
    return MiniMaxProvider(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def req() -> ChatRequest:
    return {"messages": [{"role": "user", "content": "你好"}]}


@respx.mock
@pytest.mark.asyncio
async def test_complete_happy_path_parses_content_and_model(req: ChatRequest) -> None:
    # Arrange
    provider = _make_provider()
    respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "MiniMax-M3",
                "choices": [{"message": {"role": "assistant", "content": "hello"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )
    )

    # Act
    result = await provider.complete(req)

    # Assert
    assert result["content"] == "hello"
    assert result["model"] == "MiniMax-M3"
    assert result["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }


@respx.mock
@pytest.mark.asyncio
async def test_complete_sends_required_fields_in_body(req: ChatRequest) -> None:
    provider = _make_provider()
    route = respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )
    )

    await provider.complete(req)

    request = route.calls.last.request
    import json as _json

    body = _json.loads(request.content)
    assert body["model"] == "MiniMax-M3"
    assert body["messages"] == [{"role": "user", "content": "你好"}]
    assert body["thinking"] == {"type": "disabled"}
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["content-type"] == "application/json"


@respx.mock
@pytest.mark.asyncio
async def test_complete_401_raises_llm_auth_error(req: ChatRequest) -> None:
    provider = _make_provider()
    respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )

    with pytest.raises(LLMAuthError):
        await provider.complete(req)


@respx.mock
@pytest.mark.asyncio
async def test_complete_400_raises_llm_response_error(req: ChatRequest) -> None:
    provider = _make_provider()
    respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        return_value=httpx.Response(400, json={"error": "bad request"})
    )

    with pytest.raises(LLMResponseError):
        await provider.complete(req)


@respx.mock
@pytest.mark.asyncio
async def test_complete_500_eventually_raises_rate_limit_error(req: ChatRequest) -> None:
    # max_retries=1 → two total attempts.
    provider = _make_provider(max_retries=1)
    respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    with (
        patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        pytest.raises(LLMRateLimitError),
    ):
        await provider.complete(req)


@respx.mock
@pytest.mark.asyncio
async def test_complete_500_succeeds_after_retry(req: ChatRequest) -> None:
    provider = _make_provider(max_retries=2)
    route = respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(500, json={"error": "boom"}),
            httpx.Response(503, json={"error": "still boom"}),
            httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "recovered"}}],
                    "model": "MiniMax-M3",
                },
            ),
        ]
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        result = await provider.complete(req)

    assert result["content"] == "recovered"
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_complete_timeout_retries_then_raises(req: ChatRequest) -> None:
    provider = _make_provider(max_retries=1, timeout=0.1)
    respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        side_effect=httpx.ReadTimeout("timeout")
    )

    with (
        patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        pytest.raises(LLMTimeoutError),
    ):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_complete_without_api_key_raises_llm_auth_error(req: ChatRequest) -> None:
    provider = _make_provider(api_key="")
    with pytest.raises(LLMAuthError):
        await provider.complete(req)


@respx.mock
@pytest.mark.asyncio
async def test_complete_malformed_response_raises_llm_response_error(
    req: ChatRequest,
) -> None:
    provider = _make_provider()
    respx.post("https://api.minimaxi.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"oops": "no choices"})
    )

    with pytest.raises(LLMResponseError):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_aclose_clears_internal_client() -> None:
    provider = _make_provider()
    # Force the lazy client to materialize.
    client = await provider._get_client()
    assert provider._client is client

    await provider.aclose()
    assert provider._client is None


@pytest.mark.asyncio
async def test_async_context_manager_closes_on_exit() -> None:
    provider = _make_provider()

    # Lazily create the client so we can verify __aexit__ cleans it up.
    await provider._get_client()
    assert provider._client is not None

    async with provider:
        # Inside the block, the client we created before __aenter__ is still set.
        assert provider._client is not None

    assert provider._client is None