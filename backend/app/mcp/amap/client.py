"""AmapClient — F030 / F031 共用的高德 MCP HTTP 客户端.

设计要点 (per spec/features/F030-amap-restaurant-search.md §5 / F031 §5):

- HTTP 5xx / 429 / network timeout → 重试 `max_retries` 次后抛
  `AmapNetworkError` 或 `AmapQuotaExceededError`
- HTTP 401 / body `infocode=10001` → 抛 `AmapInvalidKeyError` (启动时
  fail-fast, 运行时触发说明配置漂移)
- Body `infocode=10044` → 抛 `AmapQuotaExceededError`
- 业务错误 (`status != "1"`) 由调用方按 status / infocode 自行判断

实现参考 `app/agents/llm/minimax.py` 的 transport-level retry 模式
(attempt loop + backoff + 异常分类), 保证两个外部依赖的错误处理语义
一致.

Endpoint 约定:

- 餐厅搜索: `GET /v3/place/around`
- 天气查询: `GET /v3/weather/weatherInfo` (F031 复用)
- 所有响应均为 JSON; key 走 query string (`?key=...`)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AmapInvalidKeyError,
    AmapLocationInvalidError,
    AmapNetworkError,
    AmapQuotaExceededError,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://restapi.amap.com"
# 高德 body-level 错误码 (见 https://lbs.amap.com/api/webservice/guide/tools/info)
_INVALID_KEY_INFOCODES = {"10001", "10002", "10003", "10004", "10005", "10007", "10008"}
_QUOTA_INFOCODES = {"10044", "10045", "10046", "10047", "10048"}
# F031 §5: 城市/区域编码不存在 (e.g. infocode=20001) → 调用方应用 IP 城市兜底
_LOCATION_INVALID_INFOCODES = {"20001", "20002", "20003", "20010", "20011", "20012"}
# 重试退避基础秒数（与 LLM provider 保持一致）
_BACKOFF_BASE_SECONDS = 0.3


class AmapClient:
    """高德 MCP 通用客户端 —— 餐厅 / 天气复用同一实例.

    客户端是**无状态**的: `aclose()` 后可丢弃, 下次调用重新打开。
    长生命周期场景下建议用 `async with AmapClient(...) as client:`。
    """

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 2.0,
        max_retries: int = 1,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        if not api_key:
            # F030 §6 / F031 §6: 启动时校验 key 存在；缺失即 fail-fast
            raise ValueError("AmapClient.api_key 不能为空 — 请在 .env 中设置 AMAP_API_KEY")
        if timeout_seconds <= 0:
            raise ValueError(f"AmapClient.timeout_seconds 必须 > 0, 实际={timeout_seconds}")
        if max_retries < 0:
            raise ValueError(f"AmapClient.max_retries 必须 >= 0, 实际={max_retries}")

        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    # ----- public properties (便于测试断言) -----

    @property
    def api_key(self) -> str:
        return self._api_key

    # ----- context manager -----

    async def __aenter__(self) -> AmapClient:
        await self._get_client()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ----- core GET -----

    async def get_json(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET `{base_url}{path}`, 把 `key` 自动拼到 query, 返回 JSON 字典.

        - 401 / body infocode 表示 invalid key → `AmapInvalidKeyError`
        - HTTP 429 / body infocode 10044-10048 → `AmapQuotaExceededError`
        - 网络 / 超时 → 重试 `max_retries` 次, 仍失败 → `AmapNetworkError`
        - 其他非 2xx → `AmapNetworkError` (带 status, 不重试)
        """
        client = await self._get_client()
        query: dict[str, Any] = {"key": self._api_key, "output": "JSON"}
        if params:
            query.update(params)

        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        # 共 max_retries + 1 次尝试
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.get(url, params=query)
            except httpx.TimeoutException as exc:
                last_error = AmapNetworkError(
                    f"高德 MCP 超时 ({self.timeout_seconds}s)",
                    details={"path": path, "attempt": attempt + 1},
                )
                logger.warning(
                    "Amap timeout (attempt %d/%d) path=%s: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    path,
                    exc,
                )
                await self._sleep_backoff(attempt)
                continue
            except httpx.HTTPError as exc:
                last_error = AmapNetworkError(
                    f"高德 MCP 网络错误: {exc}",
                    details={"path": path, "attempt": attempt + 1},
                )
                logger.warning(
                    "Amap HTTP error (attempt %d/%d) path=%s: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    path,
                    exc,
                )
                await self._sleep_backoff(attempt)
                continue

            # --- 拿到 response, 按 status 分类 ---
            if response.status_code == 200:
                payload = self._safe_json(response)
                if not isinstance(payload, dict):
                    raise AmapNetworkError(
                        "高德 MCP 返回非 JSON 字典",
                        details={"path": path, "body": str(payload)[:200]},
                    )
                self._raise_for_amap_status(payload, path)
                return payload

            if response.status_code == 401:
                raise AmapInvalidKeyError(
                    "高德 MCP 鉴权失败 (HTTP 401)",
                    details={"hint": "检查 .env 中 AMAP_API_KEY"},
                )

            if response.status_code == 429 or response.status_code >= 500:
                # 429 / 5xx → 重试; 用尽再抛
                last_error = (
                    AmapQuotaExceededError(
                        f"高德 MCP 返回 {response.status_code}",
                        details={"path": path, "attempt": attempt + 1},
                    )
                    if response.status_code == 429
                    else AmapNetworkError(
                        f"高德 MCP 返回 {response.status_code}",
                        details={"path": path, "attempt": attempt + 1},
                    )
                )
                logger.warning(
                    "Amap transient status %d (attempt %d/%d) path=%s",
                    response.status_code,
                    attempt + 1,
                    self.max_retries + 1,
                    path,
                )
                await self._sleep_backoff(attempt)
                continue

            # 其他 4xx (例如 403 / 400) — 不重试, 直接抛网络错误
            raise AmapNetworkError(
                f"高德 MCP 返回 {response.status_code}",
                details={"path": path, "body": response.text[:200]},
            )

        # 重试耗尽
        assert last_error is not None  # 给 type checker
        raise last_error

    # ----- internals -----

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return response.text[:500]

    @staticmethod
    def _raise_for_amap_status(payload: dict[str, Any], path: str) -> None:
        """检查 body-level `status` 与 `infocode` 并抛对应异常.

        高德协议约定: `status=1` 表示业务成功; 其它值携带 `infocode`
        描述错误类别. 我们在业务层（restaurant/weather）单独处理
        `status=1 + count=0` (AMAP_NO_RESULT) —— 这种情况不算错误。
        """
        status = str(payload.get("status", ""))
        if status == "1":
            return  # 业务成功, 调用方决定空结果如何处理

        infocode = str(payload.get("infocode", ""))

        if infocode in _INVALID_KEY_INFOCODES or payload.get("info") == "INVALID_USER_KEY":
            raise AmapInvalidKeyError(
                f"高德 MCP 鉴权失败 (infocode={infocode})",
                details={"info": payload.get("info"), "path": path},
            )

        if infocode in _QUOTA_INFOCODES or "CUQPS_HAS_EXCEEDED" in str(payload.get("info", "")):
            raise AmapQuotaExceededError(
                f"高德 MCP 配额耗尽 (infocode={infocode})",
                details={"info": payload.get("info"), "path": path},
            )

        if infocode in _LOCATION_INVALID_INFOCODES:
            # F031 §5: AMAP_LOCATION_INVALID — 调用方应使用 IP 城市兜底
            raise AmapLocationInvalidError(
                f"高德 MCP 无法解析 location (infocode={infocode})",
                details={"info": payload.get("info"), "path": path},
            )

        # 其它业务错误 (status=0 但 infocode 未识别) — 抛网络错误兜底
        raise AmapNetworkError(
            f"高德 MCP 业务错误 (status={status}, infocode={infocode})",
            details={"info": payload.get("info"), "path": path},
        )

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        if attempt < 0:
            return
        await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))


# ----- factory -----


@lru_cache(maxsize=1)
def get_amap_client() -> AmapClient:
    """从 Settings 工厂构造单例 AmapClient.

    F030 §6: AMAP_API_KEY 缺失即 fail-fast（由 `AmapClient.__init__`
    抛 `ValueError` 实现）；调用方在 app 启动时显式调一次本函数以
    触发校验。
    """
    settings: Settings = get_settings()
    return AmapClient(
        api_key=settings.amap_api_key,
        timeout_seconds=settings.amap_timeout_seconds,
        max_retries=settings.amap_max_retries,
    )


def reset_amap_client_cache() -> None:
    """测试用 —— 清掉 `get_amap_client` 的 lru_cache.

    仅供 conftest / 单元测试在 monkeypatch env 后重置缓存使用。
    """
    get_amap_client.cache_clear()


__all__ = ["AmapClient", "get_amap_client", "reset_amap_client_cache"]
