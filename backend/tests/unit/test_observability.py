"""Tests for `app.agents._observability` — node wrapping + LLM I/O instrumentation."""
from __future__ import annotations

import logging

import pytest
from app.agents._observability import (
    instrument_llm_call,
    logged_node,
    render_messages,
    render_response_content,
)
from app.agents.llm.types import ChatRequest
from app.core.request_id import reset_request_id, set_request_id

# ---------------------------------------------------------------------------
# render_messages / render_response_content
# ---------------------------------------------------------------------------


class TestRenderMessages:
    def test_renders_single_user_message(self) -> None:
        out = render_messages([{"role": "user", "content": "你好"}])
        assert "[user]" in out
        assert "(2 chars)" in out
        assert "你好" in out

    def test_renders_system_and_user_with_blank_line_between(self) -> None:
        out = render_messages(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "usr"},
            ]
        )
        assert "[system]" in out
        assert "[user]" in out
        # system block appears before user block
        sys_pos = out.index("[system]")
        user_pos = out.index("[user]")
        assert sys_pos < user_pos

    def test_truncates_at_4kb(self) -> None:
        big = "x" * 8192
        out = render_messages([{"role": "user", "content": big}])
        assert "<... 4096 bytes truncated>" in out
        assert "(8192 chars)" in out  # header reports true size

    def test_handles_empty_messages_list(self) -> None:
        assert render_messages([]) == ""

    def test_handles_missing_content_key(self) -> None:
        out = render_messages([{"role": "user"}])  # type: ignore[list-item]
        assert "[user]" in out


class TestRenderResponseContent:
    def test_short_content_passes_through(self) -> None:
        assert render_response_content("hello") == "hello"

    def test_long_content_truncated(self) -> None:
        out = render_response_content("y" * 6000)
        assert "y" * 4096 in out
        assert "<... 1904 bytes truncated>" in out

    def test_empty_string(self) -> None:
        assert render_response_content("") == ""


# ---------------------------------------------------------------------------
# logged_node
# ---------------------------------------------------------------------------


class TestLoggedNode:
    @pytest.mark.asyncio
    async def test_logs_enter_and_exit_with_elapsed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def my_node(state: dict[str, object]) -> dict[str, object]:
            return {"ok": True}

        wrapped = logged_node("my_node", my_node)
        with caplog.at_level(logging.INFO, logger="app.agents.observability"):
            await wrapped({"user_id": "u1"})

        msgs = [r.getMessage() for r in caplog.records]
        assert any("node[my_node] enter" in m for m in msgs)
        assert any("node[my_node] exit" in m for m in msgs)
        exit_line = next(m for m in msgs if "exit" in m)
        assert "elapsed_ms=" in exit_line
        assert "out_keys=" in exit_line

    @pytest.mark.asyncio
    async def test_logs_exception_with_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def boom(state: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("kaboom")

        wrapped = logged_node("boom_node", boom)
        with (
            caplog.at_level(logging.INFO, logger="app.agents.observability"),
            pytest.raises(RuntimeError, match="kaboom"),
        ):
            await wrapped({"user_id": "u1"})

        msgs = [r.getMessage() for r in caplog.records]
        assert any("node[boom_node] raise" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_passes_through_state_keys(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def nop(state: dict[str, object]) -> dict[str, object]:
            return {}

        wrapped = logged_node("kp", nop)
        with caplog.at_level(logging.INFO, logger="app.agents.observability"):
            await wrapped({"a": 1, "b": 2, "c": 3})

        enter_line = next(
            r.getMessage()
            for r in caplog.records
            if "enter" in r.getMessage()
        )
        # Sorted keys appear in the enter line
        assert "a" in enter_line and "b" in enter_line and "c" in enter_line

    @pytest.mark.asyncio
    async def test_includes_request_id_from_contextvar(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def nop(state: dict[str, object]) -> dict[str, object]:
            return {}

        token = set_request_id("deadbeef")
        try:
            wrapped = logged_node("rid_test", nop)
            with caplog.at_level(logging.INFO, logger="app.agents.observability"):
                await wrapped({})
            msgs = [r.getMessage() for r in caplog.records]
            assert any("rid=deadbeef" in m for m in msgs)
        finally:
            reset_request_id(token)

    def test_wraps_sync_function(self) -> None:
        # logged_node should detect sync vs async via inspect.
        def sync_node(state: dict[str, object]) -> dict[str, object]:
            return {"sync": True}

        wrapped = logged_node("sync_node", sync_node)
        assert wrapped({"x": 1}) == {"sync": True}


# ---------------------------------------------------------------------------
# instrument_llm_call — uses FakeLLMProvider to exercise the decorator path.
# ---------------------------------------------------------------------------


class TestInstrumentLlmCall:
    @pytest.mark.asyncio
    async def test_logs_enter_and_exit_with_model_and_elapsed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.agents.llm.testing import FakeLLMProvider

        provider = FakeLLMProvider(
            response={"content": "hello", "model": "fake-model", "usage": None}
        )
        request: ChatRequest = {"messages": [{"role": "user", "content": "hi"}]}

        with caplog.at_level(logging.INFO, logger="app.agents.observability"):
            result = await provider.complete(request)

        assert result["content"] == "hello"
        msgs = [r.getMessage() for r in caplog.records]
        assert any("llm enter" in m and "model=fake-model" in m for m in msgs)
        assert any("llm exit" in m and "elapsed_ms=" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_logs_full_prompt_at_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.agents.llm.testing import FakeLLMProvider

        provider = FakeLLMProvider(
            response={"content": "ok", "model": "fake-model", "usage": None}
        )
        request: ChatRequest = {
            "messages": [
                {"role": "system", "content": "SYS-CONTENT-12345"},
                {"role": "user", "content": "USR-CONTENT-67890"},
            ]
        }

        with caplog.at_level(logging.DEBUG, logger="app.agents.observability"):
            await provider.complete(request)

        msgs = [r.getMessage() for r in caplog.records]
        assert any("SYS-CONTENT-12345" in m for m in msgs)
        assert any("USR-CONTENT-67890" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_does_not_log_prompt_at_info_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.agents.llm.testing import FakeLLMProvider

        provider = FakeLLMProvider(
            response={"content": "ok", "model": "fake-model", "usage": None}
        )
        request: ChatRequest = {
            "messages": [{"role": "user", "content": "MARKER-ZZZ"}]
        }

        with caplog.at_level(logging.INFO, logger="app.agents.observability"):
            await provider.complete(request)

        msgs = [r.getMessage() for r in caplog.records]
        # MARKER only appears in DEBUG prompt render; INFO shouldn't contain it.
        assert not any("MARKER-ZZZ" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_logs_error_on_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.agents.llm.testing import FakeLLMProvider

        class BoomProvider(FakeLLMProvider):
            async def complete(self, request: ChatRequest):  # type: ignore[override]
                raise RuntimeError("transport down")

        # Manually decorate since subclass override breaks the decorator chain.
        BoomProvider.complete = instrument_llm_call(  # type: ignore[method-assign]
            BoomProvider.complete.__wrapped__  # type: ignore[attr-defined]
            if hasattr(BoomProvider.complete, "__wrapped__")
            else BoomProvider.complete
        )

        provider = BoomProvider()
        with (
            caplog.at_level(logging.INFO, logger="app.agents.observability"),
            pytest.raises(RuntimeError, match="transport down"),
        ):
            await provider.complete(
                {"messages": [{"role": "user", "content": "x"}]}
            )

        msgs = [r.getMessage() for r in caplog.records]
        assert any("llm error" in m and "RuntimeError" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_logs_usage_tokens_on_exit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app.agents.llm.testing import FakeLLMProvider

        provider = FakeLLMProvider(
            response={
                "content": "ok",
                "model": "fake-model",
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 7,
                    "total_tokens": 19,
                },
            }
        )
        with caplog.at_level(logging.INFO, logger="app.agents.observability"):
            await provider.complete(
                {"messages": [{"role": "user", "content": "x"}]}
            )

        msgs = [r.getMessage() for r in caplog.records]
        assert any("prompt=12" in m and "completion=7" in m and "total=19" in m for m in msgs)
