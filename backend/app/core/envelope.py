"""API response envelope per `spec/api.md` §通用约定.

Success: `{"ok": true, "data": <payload>}`
Error:   `{"ok": false, "error": {"code": str, "message": str, "details": object | null}}`

These are plain dicts so they serialize cleanly without going through FastAPI's
`JSONResponse` Pydantic model path (which would require a wrapper model). They
also keep the contract identical across HTTP and any future non-HTTP transport
(e.g. internal WebSocket events for SSE).
"""
from __future__ import annotations

from typing import Any


def ok(data: object) -> dict[str, Any]:
    """Wrap a success payload in the standard envelope."""
    return {"ok": True, "data": data}


def err(code: str, message: str, details: object | None = None) -> dict[str, Any]:
    """Wrap an error in the standard envelope; `details` is optional structured context."""
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}
