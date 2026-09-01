"""Domain exception hierarchy and FastAPI exception handlers.

Per `spec/api.md` §通用约定, errors are returned in the standard envelope:
    {"ok": false, "error": {"code", "message", "details"}}

`DomainError` is the base class; subclasses fix HTTP status and error code.
Handlers are registered in `app/main.py` (not middleware — middleware can't
reach route context and bypasses `RequestValidationError`).

`RequestValidationError` handler also recognises the `ValueError` payload
emitted by `app.schemas.preferences._validation_error` (format:
`<CODE>|<message>|<json-details>`) and decodes it back into the same envelope
shape. Pydantic v2 only wraps ValueError, so this is the cleanest way to
surface F001's per-field error codes without coupling the schema layer to
the DomainError class hierarchy.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.envelope import err


class DomainError(Exception):
    """Base for business-level errors that should serialize via the envelope."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


# ----- F001 §6 — preferences validation errors (all HTTP 400) -----


class InvalidCuisineIDError(DomainError):
    code = "INVALID_CUISINE_ID"
    http_status = 400


class InvalidAllergyError(DomainError):
    code = "INVALID_ALLERGY"
    http_status = 400


class InvalidSpiceError(DomainError):
    code = "INVALID_SPICE"
    http_status = 400


class InvalidTemperatureError(DomainError):
    code = "INVALID_TEMPERATURE"
    http_status = 400


class InvalidBudgetError(DomainError):
    code = "INVALID_BUDGET"
    http_status = 400


# ----- Reserved for future -----


class PreferenceNotFoundError(DomainError):
    """M1 GET returns defaults; this remains for M2+ explicit-lookup endpoints."""

    code = "PREFERENCE_NOT_FOUND"
    http_status = 404


# ----- LLM transport errors -----


class LLMError(DomainError):
    """Base for LLM provider failures. Mapped to HTTP 502 by default."""

    code = "LLM_ERROR"
    http_status = 502


class LLMAuthError(LLMError):
    code = "LLM_AUTH_ERROR"
    http_status = 502


class LLMRateLimitError(LLMError):
    code = "LLM_RATE_LIMIT"
    http_status = 502


class LLMTimeoutError(LLMError):
    code = "LLM_TIMEOUT"
    http_status = 504


class LLMResponseError(LLMError):
    code = "LLM_RESPONSE_ERROR"
    http_status = 502


# ----- Exception handlers -----


async def _domain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(status_code=exc.http_status, content=err(exc.code, exc.message, exc.details))


async def _request_validation_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Pydantic validation errors → envelope at HTTP 400. Detect the encoded
    # `<CODE>|<message>|<details>` payload emitted by `app.schemas.preferences`
    # and use it directly; otherwise surface the raw Pydantic errors under
    # `details` so the frontend can map field-level issues without inventing
    # codes per failure mode.
    decoded = _try_decode_encoded_error(exc)
    if decoded is not None:
        code, message, details = decoded
        return JSONResponse(status_code=400, content=err(code, message, details))
    return JSONResponse(
        status_code=400,
        content=err("VALIDATION_ERROR", "请求参数校验失败", {"errors": exc.errors()}),
    )


async def _http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    # Preserve the HTTPException's status but envelope its detail string.
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content=err("HTTP_ERROR", detail))


def _try_decode_encoded_error(
    exc: RequestValidationError,
) -> tuple[str, str, Any] | None:
    """Pick out the first Pydantic error whose payload was emitted by
    `_validation_error(code, message, details)` and return `(code, message, details)`.

    Returns None when no error carries the encoded payload — caller falls back
    to the generic `VALIDATION_ERROR` envelope.
    """
    for error in exc.errors():
        ctx = error.get("ctx") or {}
        raw = ctx.get("error") or error.get("input")
        if not isinstance(raw, ValueError):
            continue
        parts = str(raw).split("|", maxsplit=2)
        if len(parts) != 3:
            continue
        code, message, details_raw = parts
        try:
            details: Any = json.loads(details_raw)
        except (TypeError, ValueError):
            details = None
        return code, message, details
    return None


def register_exception_handlers(app: FastAPI) -> None:
    """Wire all handlers onto a FastAPI app. Idempotent within a single app."""
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_error_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
