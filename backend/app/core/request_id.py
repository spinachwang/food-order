"""Request-scoped correlation ID — single source of truth for `request_id`.

A `request_id` (rid) is an 8-char hex string generated once per inbound HTTP
request (`POST /api/v1/agent/chat`) and propagated to every log record emitted
during that request's lifetime, including log records from libraries that know
nothing about our domain.

Two propagation channels coexist (belt + suspenders):

1. **`contextvars.ContextVar`** — set in the API entry, inherited by every
   coroutine spawned afterwards under the same `asyncio.Task`. The
   `RequestIdFilter` below reads from this var and injects `record.request_id`
   so every `LogRecord` carries the value automatically — no manual `extra=`
   on each call site.

2. **`AgentState["request_id"]`** — written alongside the var for cases where
   contextvar inheritance is broken (e.g. LangGraph's checkpointer fork, or
   smoke scripts that bypass the API layer). Nodes can `state["request_id"]`
   as a fallback.

Both channels default to the sentinel `"-"` when unset so log lines are
always grep-friendly: `grep rid=abc12345` matches one full request.
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar, Token

# `default=None` keeps the filter's `record.request_id` always present (the
# filter substitutes "-" before the formatter renders).
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """Return a fresh 8-char lowercase hex ID.

    32 bits of entropy (4B distinct IDs) — enough to be unique within a single
    process lifetime without bloating log lines. NOT a security token.
    """
    return uuid.uuid4().hex[:8]


def set_request_id(rid: str | None) -> Token[str | None]:
    """Bind `rid` for the current async context. Returns a Token for reset."""
    return _request_id_var.set(rid)


def reset_request_id(token: Token[str | None]) -> None:
    """Undo a prior `set_request_id` (used in tests / teardown)."""
    _request_id_var.reset(token)


def get_request_id() -> str | None:
    """Return the current request_id, or None if unset."""
    return _request_id_var.get()


class RequestIdFilter(logging.Filter):
    """Attach `record.request_id` to every LogRecord passing through.

    Default value `"-"` matches the formatter's `%` placeholder so log lines
    always render consistently. Subclasses / LoggerAdapters can override by
    passing `extra={"request_id": "..."}` to a specific log call.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = get_request_id() or "-"
        return True


__all__ = [
    "RequestIdFilter",
    "get_request_id",
    "new_request_id",
    "reset_request_id",
    "set_request_id",
]
