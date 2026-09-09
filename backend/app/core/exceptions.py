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


class InvalidStructuredAddressError(DomainError):
    """F051 §7 — default_location 结构化对象字段缺失或正则不匹配.

    与 `app.schemas.structured_address.StructuredAddress` 的
    `field_validator` 编码 `INVALID_STRUCTURED_ADDRESS` 错误码配套 —
    Pydantic 路径下用户看到的仍是 `INVALID_STRUCTURED_ADDRESS`，本类
    仅供业务代码（服务层 / Node 层）显式抛错的场景。
    """

    code = "INVALID_STRUCTURED_ADDRESS"
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


# ----- F030 / F031 — AMAP MCP transport errors -----


class AmapError(DomainError):
    """Base for AMAP MCP failures. Mapped to HTTP 502 by default (upstream issue)."""

    code = "AMAP_ERROR"
    http_status = 502


class AmapInvalidKeyError(AmapError):
    """AMAP_API_KEY 无效或未配置。

    F030 §5 / F031 §5: 启动时 fail-fast 应当拦截；运行时触发则说明
    配置漂移，需要运维介入。
    """

    code = "AMAP_INVALID_KEY"
    http_status = 502


class AmapQuotaExceededError(AmapError):
    """AMAP 配额耗尽（HTTP 429 或 infocode=10044）。"""

    code = "AMAP_QUOTA_EXCEEDED"
    http_status = 429


class AmapNetworkError(AmapError):
    """AMAP 网络超时或连接错误，工具层已重试 1 次仍失败。"""

    code = "AMAP_NETWORK_ERROR"
    http_status = 504


class AmapLocationInvalidError(AmapError):
    """AMAP 无法解析 location（坐标无法落到有效行政区划 / adcode 不存在）。

    HTTP **422** (Unprocessable Entity) 而不是 502:
    - 502 = "Bad Gateway", 描述网关/代理层收到上游协议级失败
    - 但高德 `status=1 + regeocode` 缺失是正常 200 响应 + 业务数据缺失,
      属于客户端请求语义无法处理 (Unprocessable Entity), 不是网关错
    - 前端 `useGeolocation` 据此判别降级路径, 而不是误以为网关挂了

    F031 §5: 调用方（summary agent）应使用 IP 城市兜底。
    F051 §2.4: 弹窗层也要走「定位失败 → 默认城市兜底」分支。
    """

    code = "AMAP_LOCATION_INVALID"
    http_status = 422


class AmapDistrictNotFoundError(AmapError):
    """F051 §5.1 — 高德 /config/district 未命中 keywords.

    调用方应回退到省级列表 (36 项硬编码) 或引导用户重新输入.
    """

    code = "AMAP_DISTRICT_NOT_FOUND"
    http_status = 404


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
        content=err(
            "VALIDATION_ERROR", "请求参数校验失败", {"errors": _safe_errors(exc.errors())}
        ),
    )


def _safe_errors(errors: "Any") -> list[dict[str, Any]]:
    """Make a JSON-safe copy of Pydantic error dicts.

    Pydantic v2 attaches the original `ValueError` to `ctx["error"]`, which
    `JSONResponse` cannot serialize. Replace it with its string form so the
    frontend can still inspect the encoded `<CODE>|<message>|<details>` payload.

    Accepts `Any` because FastAPI's `RequestValidationError.errors()` is typed as
    `Sequence[ErrorDetails]`; we only iterate / index, so the broader type is fine.
    """
    safe: list[dict[str, Any]] = []
    if not errors:
        return safe
    for error in errors:
        if not isinstance(error, dict):
            continue
        ctx = error.get("ctx")
        if isinstance(ctx, dict) and isinstance(ctx.get("error"), BaseException):
            ctx = {**ctx, "error": str(ctx["error"])}
            safe.append({**error, "ctx": ctx})
        else:
            safe.append(dict(error))
    return safe


async def _http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    # Preserve the HTTPException's status but envelope its detail string.
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content=err("HTTP_ERROR", detail))


async def _value_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """F051 §4 — wrapper `ValueError` (入参非法) → 400 envelope.

    MCP wrappers (`amap_regeo`, `amap_search_places`, `amap_get_district`)
    raise plain `ValueError` on bad inputs (not in the `DomainError` family
    — they're reusable utilities, not HTTP-coupled). Without this handler,
    those propagate as 500 / re-raise in TestClient.

    Routing `ValueError` → 400 here keeps the public contract consistent:
    "bad input from client → 4xx, never 5xx". The original message is
    surfaced verbatim (already user-friendly Chinese / structured).
    """
    assert isinstance(exc, ValueError)
    message = str(exc) or "参数非法"
    return JSONResponse(status_code=400, content=err("VALIDATION_ERROR", message))


def _try_decode_encoded_error(
    exc: RequestValidationError,
) -> tuple[str, str, Any] | None:
    """Pick out the first Pydantic error whose payload was emitted by
    `_validation_error(code, message, details)` and return `(code, message, details)`.

    Returns None when no error carries the encoded payload — caller falls back
    to the generic `VALIDATION_ERROR` envelope.

    Special case (F051 §6/§7): errors with `loc` rooted at `default_location`
    are always surfaced as `INVALID_STRUCTURED_ADDRESS`, regardless of whether
    they came from a `ValueError` payload, a Pydantic `model_type` mismatch
    (string passed instead of dict/StructuredAddress), a `missing` field, or
    a nested field-validator regex miss. This keeps the public contract stable
    so the frontend can switch on a single code regardless of which sub-rule
    fired.
    """
    errors = exc.errors()

    # 1) F051 mapping first — `default_location` failures always emit this code.
    # FastAPI prefixes errors with `("body", ...)` for request payloads, so the
    # `default_location` path may appear anywhere in `loc`.
    for error in errors:
        loc = error.get("loc") or ()
        if "default_location" in loc:
            return (
                "INVALID_STRUCTURED_ADDRESS",
                "default_location 校验失败",
                _safe_errors(errors),
            )

    # 2) Generic encoded-ValueError payload (F001 etc.)
    for error in errors:
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
    # F051: wrapper ValueError → 400 envelope (避免 500 / TestClient 重抛)
    app.add_exception_handler(ValueError, _value_error_handler)
