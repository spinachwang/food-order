"""Fake LLM provider for tests.

`FakeLLMProvider` returns a configurable `ChatResponse` for every `complete()` call.
This lets us write unit tests for any consumer (cuisine expert, summary agent,
etc.) without mocking httpx or hitting the real API.

Use the `set_response` method to install a canned response, or `set_responses`
for sequential calls.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.agents._observability import instrument_llm_call
from app.agents.llm.base import LLMProvider
from app.agents.llm.types import ChatRequest, ChatResponse


class FakeLLMProvider(LLMProvider):
    """Returns canned responses; tracks every call for assertion."""

    def __init__(self, response: ChatResponse | None = None) -> None:
        self.model = "fake-model"
        self.timeout = 0.0
        self.max_retries = 0
        self._responses: list[ChatResponse] = [response] if response else []
        self.calls: list[ChatRequest] = []

    def set_response(self, response: ChatResponse) -> None:
        self._responses = [response]

    def set_responses(self, responses: Iterable[ChatResponse]) -> None:
        self._responses = list(responses)

    @instrument_llm_call
    async def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        if not self._responses:
            return {"content": "", "model": self.model, "usage": None}
        if len(self._responses) == 1:
            return self._responses[0]
        return self._responses.pop(0)
