"""LLM TypedDicts — provider-agnostic wire format for chat requests/responses.

All 14 cuisine experts (F003 §3.1) and the future summary agent (F040) call into
`LLMProvider.complete(ChatRequest)` and never touch HTTP/JSON shape directly.
"""
from __future__ import annotations

from typing import Literal, TypedDict

MessageRole = Literal["system", "user", "assistant"]


class Message(TypedDict):
    role: MessageRole
    content: str


class ChatRequest(TypedDict, total=False):
    """Chat completion request. All fields except `messages` are optional.

    `thinking` is provider-specific (MiniMax-M3 takes {"type": "disabled" | "enabled" | "adaptive"}).
    Other providers can ignore it via `ChatRequest.__getitem__` semantics.
    """

    messages: list[Message]
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    thinking: dict[str, str] | None


class ChatResponseUsage(TypedDict, total=False):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(TypedDict):
    content: str
    model: str
    usage: ChatResponseUsage | None
