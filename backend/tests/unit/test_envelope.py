"""Unit tests for `app.core.envelope`."""
from __future__ import annotations

from app.core.envelope import err, ok


class TestOk:
    def test_wraps_dict_payload(self) -> None:
        # Arrange / Act
        result = ok({"foo": 1})

        # Assert
        assert result == {"ok": True, "data": {"foo": 1}}

    def test_wraps_arbitrary_payload_types(self) -> None:
        assert ok([1, 2, 3]) == {"ok": True, "data": [1, 2, 3]}
        assert ok("scalar") == {"ok": True, "data": "scalar"}

    def test_wraps_none_as_null_payload(self) -> None:
        # `ok(None)` is valid — distinguishes from "no payload field" semantically.
        assert ok(None) == {"ok": True, "data": None}


class TestErr:
    def test_minimal_error_envelope(self) -> None:
        result = err("INVALID_X", "x is invalid")

        assert result == {
            "ok": False,
            "error": {"code": "INVALID_X", "message": "x is invalid", "details": None},
        }

    def test_error_with_structured_details(self) -> None:
        result = err("INVALID_X", "x is invalid", {"field": "x", "min": 0})

        assert result["ok"] is False
        assert result["error"]["code"] == "INVALID_X"
        assert result["error"]["details"] == {"field": "x", "min": 0}

    def test_error_with_none_details_is_explicit(self) -> None:
        # When caller passes `None` explicitly, surface it as `null` not absent.
        assert err("CODE", "msg", None)["error"]["details"] is None
