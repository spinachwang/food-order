"""Tests for `app.core.request_id` — ContextVar + logging Filter."""
from __future__ import annotations

import asyncio
import logging
import re

from app.core.request_id import (
    RequestIdFilter,
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)


class TestRequestIdHelpers:
    def test_new_request_id_is_8_lowercase_hex_chars(self) -> None:
        rid = new_request_id()
        assert len(rid) == 8
        assert re.fullmatch(r"[0-9a-f]{8}", rid)

    def test_new_request_id_returns_unique_values(self) -> None:
        # 32 bits of entropy — collision is negligible, but verify the
        # generator actually varies.
        assert len({new_request_id() for _ in range(50)}) == 50

    def test_set_and_get_roundtrip(self) -> None:
        token = set_request_id("abc12345")
        try:
            assert get_request_id() == "abc12345"
        finally:
            reset_request_id(token)
        assert get_request_id() is None

    def test_set_none_clears_value(self) -> None:
        token = set_request_id("deadbeef")
        assert get_request_id() == "deadbeef"
        reset_token = set_request_id(None)
        try:
            assert get_request_id() is None
        finally:
            reset_request_id(reset_token)
        reset_request_id(token)

    def test_contextvar_isolation_between_concurrent_tasks(self) -> None:
        async def _read_after_delay(value: str, delay: float) -> str | None:
            token = set_request_id(value)
            try:
                await asyncio.sleep(delay)
                return get_request_id()
            finally:
                reset_request_id(token)

        async def _runner() -> tuple[str | None, str | None]:
            return await asyncio.gather(
                _read_after_delay("aaaaaaaa", 0.05),
                _read_after_delay("bbbbbbbb", 0.0),
            )

        a, b = asyncio.run(_runner())
        # Each task must observe its own rid at the end of its own sleep,
        # never the other task's value.
        assert a == "aaaaaaaa"
        assert b == "bbbbbbbb"


class TestRequestIdFilter:
    def test_filter_injects_request_id_from_contextvar(self) -> None:
        flt = RequestIdFilter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello", args=(), exc_info=None,
        )
        token = set_request_id("deadbeef")
        try:
            assert flt.filter(record) is True
            assert record.request_id == "deadbeef"  # type: ignore[attr-defined]
        finally:
            reset_request_id(token)

    def test_filter_uses_dash_when_unset(self) -> None:
        flt = RequestIdFilter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hi", args=(), exc_info=None,
        )
        # Ensure contextvar is None before this assertion.
        assert get_request_id() is None
        assert flt.filter(record) is True
        assert record.request_id == "-"  # type: ignore[attr-defined]

    def test_filter_preserves_explicit_request_id(self) -> None:
        flt = RequestIdFilter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname=__file__, lineno=1,
            msg="explicit", args=(), exc_info=None,
        )
        record.request_id = "explicit-id"  # type: ignore[attr-defined]
        # Even with contextvar unset, the filter must not overwrite an
        # explicit per-call extra.
        assert get_request_id() is None
        assert flt.filter(record) is True
        assert record.request_id == "explicit-id"  # type: ignore[attr-defined]
