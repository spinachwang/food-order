"""Schema 共享 helper —— `_validation_error` 编码器.

被 `app.schemas.preferences` 与 `app.schemas.structured_address` 复用，
避免两个 schema 互相 import 形成循环依赖。

约定 (per [app/core/exceptions.py _request_validation_error_handler]):
    Pydantic v2 仅捕获 `ValueError` / `AssertionError` / `TypeError`,
    在 `field_validator` 中 raise ValueError, message 编码:
        <CODE>|<human message>|<json-encoded details>
    HTTP 边界由 `_request_validation_error_handler` 解码回 envelope。

调用方: 仅 schema 层 (`field_validator` / `model_validator` / `model_post_init`)。
"""
from __future__ import annotations

import json
from typing import Any


def _validation_error(code: str, message: str, details: Any | None = None) -> ValueError:
    """Build a `ValueError` whose message encodes the DomainError envelope fields.

    Args:
        code: 业务错误码 (e.g. `INVALID_STRUCTURED_ADDRESS` / `INVALID_CUISINE_ID`).
        message: 人类可读的描述.
        details: 任意 JSON-serializable 上下文; 序列化为 JSON 字符串.

    Returns:
        `ValueError` whose `args[0]` 形如 `<code>|<message>|<details-json>`.
    """
    details_json = "null" if details is None else json.dumps(details, ensure_ascii=False)
    return ValueError(f"{code}|{message}|{details_json}")


__all__ = ["_validation_error"]