"""Internal observability helpers — full-chain logging across the LangGraph workflow.

Public surface (re-exported by `app/agents/__init__.py` is NOT done — this is
intentionally underscored; consumers should use the wrapped callables directly):

- `logged_node(name, fn)` — wrap a graph Node function with enter/exit logs.
- `instrument_llm_call(method)` — decorator for `LLMProvider.complete` that
  logs outbound prompts and inbound responses (DEBUG-level content; INFO
  summary).

Both helpers:

1. Emit INFO summary lines (model, elapsed, counts) so the default `LOG_LEVEL`
   gives a full request skeleton — 7 node entries + 7 node exits + 1 LLM
   enter + 1 LLM exit + 1 API enter + 1 API done.
2. Emit DEBUG content lines for prompts and raw responses, gated by both
   `LOG_LEVEL=DEBUG` AND `Settings.log_prompt_debug=true`.
3. Honor `app.core.request_id` automatically via the logging Filter
   installed in `app/core/logging.py` — log records render `[rid=...]`
   without manual threading.

Logger: `app.agents.observability`. `app/core/logging.py` pins this logger
to DEBUG regardless of root level, so the prompt/response blocks print
even when the operator runs with `LOG_LEVEL=INFO`. If you ever move this
module to a new logger name, update the `loggers` entry in
`app/core/logging._build_config` to match.
"""
from __future__ import annotations

import functools
import inspect
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.core.request_id import get_request_id

if TYPE_CHECKING:
    # Imported only for type checkers — the runtime decorator body uses
    # duck typing. Importing the module eagerly would create a circular
    # dependency (minimax → _observability → llm.types → llm.__init__ →
    # factory → minimax).
    pass

_logger = logging.getLogger("app.agents.observability")

# Truncation thresholds. 4 KB is enough for the router system prompt (~2 KB)
# and a typical cuisine user message (~500 B) while keeping a single log line
# under ~6 KB so most terminals render it without wrapping glitches.
_MAX_RENDER_BYTES = 4096


# ---------------------------------------------------------------------------
# Render helpers — exposed for tests + manual debugging.
# ---------------------------------------------------------------------------


def render_messages(messages: list[Any]) -> str:
    """Render a chat `messages` list as a multi-line block.

    Example output:

        [system]
        你是"午餐决策助手"的路由 Agent ...
        [user]
        想吃辣的 ...

    Truncates each message body at 4 KB to keep a single log entry bounded;
    truncated blocks end with `<... N bytes truncated>` on a new line.

    Args:
        messages: List of `Message` TypedDicts (duck-typed at runtime to
            avoid the `llm.types` import chain during module init).
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "?") if isinstance(msg, dict) else "?"
        content = msg.get("content", "") or "" if isinstance(msg, dict) else ""
        header = f"[{role}]"
        parts.append(header)
        parts.append(_truncate(content))
        parts.append("")  # blank line between messages
    return "\n".join(parts).rstrip()


def render_response_content(content: str) -> str:
    """Render an LLM response body with the same truncation rules as prompts."""
    return _truncate(content or "")


def _truncate(text: str, limit: int = _MAX_RENDER_BYTES) -> str:
    """Return `text` if it fits in `limit` bytes; otherwise truncated + marker.

    Counts `len(text)` (codepoints), not bytes — Chinese characters take 3 bytes
    in UTF-8 but we treat them uniformly for readability.
    """
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n<... {omitted} bytes truncated>"


# ---------------------------------------------------------------------------
# Node observability
# ---------------------------------------------------------------------------


def logged_node(
    name: str, fn: Callable[..., Any]
) -> Callable[..., Any]:
    """Wrap a graph Node function with enter/exit/exception logs.

    Preserves the original signature (sync or async) — LangGraph calls the
    wrapped callable with whatever args it normally passes (typically a single
    `AgentState`). The wrapper detects async via `inspect.iscoroutinefunction`
    so it works for both styles without code duplication.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            state = args[0] if args else None
            state_keys = _safe_state_keys(state)
            rid = get_request_id() or "-"
            _logger.info(
                "node[%s] enter rid=%s state_keys=%s", name, rid, state_keys
            )
            started = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
            except BaseException:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                _logger.exception(
                    "node[%s] raise rid=%s elapsed_ms=%d", name, rid, elapsed_ms
                )
                raise
            elapsed_ms = int((time.monotonic() - started) * 1000)
            out_keys = _safe_out_keys(result)
            _logger.info(
                "node[%s] exit rid=%s elapsed_ms=%d out_keys=%s",
                name,
                rid,
                elapsed_ms,
                out_keys,
            )
            return result

        return _async_wrapper

    @functools.wraps(fn)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        state = args[0] if args else None
        state_keys = _safe_state_keys(state)
        rid = get_request_id() or "-"
        _logger.info("node[%s] enter rid=%s state_keys=%s", name, rid, state_keys)
        started = time.monotonic()
        try:
            result = fn(*args, **kwargs)
        except BaseException:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            _logger.exception(
                "node[%s] raise rid=%s elapsed_ms=%d", name, rid, elapsed_ms
            )
            raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        out_keys = _safe_out_keys(result)
        _logger.info(
            "node[%s] exit rid=%s elapsed_ms=%d out_keys=%s",
            name,
            rid,
            elapsed_ms,
            out_keys,
        )
        return result

    return _sync_wrapper


def _safe_state_keys(state: Any) -> list[str]:
    """Return sorted state keys, or [] if state is not a mapping."""
    if isinstance(state, dict):
        return sorted(state.keys())
    return []


def _safe_out_keys(result: Any) -> list[str]:
    """Return sorted partial-state keys, or [] if the node returned nothing."""
    if isinstance(result, dict):
        return sorted(result.keys())
    return []


# ---------------------------------------------------------------------------
# LLM I/O observability — decorator for `LLMProvider.complete`.
# ---------------------------------------------------------------------------


def instrument_llm_call(method: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for `LLMProvider.complete(request) -> response`.

    Logs:
    - INFO on entry: model + message count + attempt hint
    - DEBUG on entry: full rendered prompt (gated by `log_prompt_debug`)
    - INFO on exit: model + elapsed_ms + usage tokens
    - DEBUG on exit: full response content (gated by `log_prompt_debug`)
    - WARNING/EXCEPTION on error: elapsed_ms + exception class

    The decorated method must be `async def complete(self, request)` per the
    `LLMProvider` ABC. The decorator assumes one positional `self` plus one
    positional `request`; `**kwargs` are passed through unchanged.
    """

    @functools.wraps(method)
    async def _wrapper(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        rid = get_request_id() or "-"
        model = getattr(self, "model", "?")
        messages = request.get("messages") or [] if isinstance(request, dict) else []
        msg_count = len(messages)

        _logger.info(
            "llm enter rid=%s model=%s messages=%d", rid, model, msg_count
        )
        if _prompt_debug_enabled():
            _logger.debug(
                "llm prompt rid=%s model=%s\n%s",
                rid,
                model,
                render_messages(messages),
            )

        started = time.monotonic()
        try:
            response = await method(self, request, *args, **kwargs)
        except BaseException as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            _logger.warning(
                "llm error rid=%s model=%s elapsed_ms=%d exc=%s",
                rid,
                model,
                elapsed_ms,
                type(exc).__name__,
            )
            raise

        elapsed_ms = int((time.monotonic() - started) * 1000)
        usage = response.get("usage") or {} if isinstance(response, dict) else {}
        _logger.info(
            "llm exit rid=%s model=%s elapsed_ms=%d "
            "tokens(prompt=%s completion=%s total=%s)",
            rid,
            response.get("model", model) if isinstance(response, dict) else model,
            elapsed_ms,
            usage.get("prompt_tokens", "-") if isinstance(usage, dict) else "-",
            usage.get("completion_tokens", "-") if isinstance(usage, dict) else "-",
            usage.get("total_tokens", "-") if isinstance(usage, dict) else "-",
        )
        if _prompt_debug_enabled():
            content = (
                response.get("content", "") if isinstance(response, dict) else ""
            )
            _logger.debug(
                "llm response rid=%s model=%s\n%s",
                rid,
                response.get("model", model) if isinstance(response, dict) else model,
                render_response_content(content),
            )
        return response

    return _wrapper


def _prompt_debug_enabled() -> bool:
    """True iff DEBUG-level logging is on AND `Settings.log_prompt_debug` is True.

    Both conditions must hold to render full prompt/response bodies. The
    `_logger.isEnabledFor` check short-circuits the rendering cost when DEBUG
    is off, even if the gate flag is True.
    """
    if not _logger.isEnabledFor(logging.DEBUG):
        return False
    try:
        return bool(get_settings().log_prompt_debug)
    except Exception:
        # Settings may fail during early import / test setup — be conservative.
        return False


# ---------------------------------------------------------------------------
# Stream helpers (unused for now; reserved for future streaming providers).
# ---------------------------------------------------------------------------


@asynccontextmanager
async def logged_stream(name: str) -> AsyncIterator[None]:
    """Pair for `logged_node` if a future streaming LLM provider arrives.

    Use:

        async with logged_stream("cuisine_expert.sichuan"):
            async for chunk in provider.stream(request):
                ...
    """
    rid = get_request_id() or "-"
    _logger.info("stream[%s] start rid=%s", name, rid)
    started = time.monotonic()
    try:
        yield
    except BaseException:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _logger.exception(
            "stream[%s] raise rid=%s elapsed_ms=%d", name, rid, elapsed_ms
        )
        raise
    elapsed_ms = int((time.monotonic() - started) * 1000)
    _logger.info("stream[%s] end rid=%s elapsed_ms=%d", name, rid, elapsed_ms)


__all__ = [
    "instrument_llm_call",
    "logged_node",
    "logged_stream",
    "render_messages",
    "render_response_content",
]
