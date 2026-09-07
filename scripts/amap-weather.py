"""F031 — 高德 MCP 天气查询手工试跑入口.

CLI: `python scripts/amap-weather.py "<location>"`, 验证 F031 §2 / §6
所有验收点 (mock 高德回包 + 错误码透传 + 条件映射 + 入参校验). 默认走 mock
模式 (不消耗配额 / 离线可跑); 传 `--live` 才发真实 HTTP.

设计目的:

- 开发 / 调试阶段快速验证 F031 契约本身 (无 LangGraph 编排开销)
- CI / 凭据缺失环境下用 `--fixture <name>` 注入回包快速跑通
- 真实联调时 `--live` 走 AMAP_API_KEY, 验证 SLA (1s 总耗时)

用法:

    # 1. Happy path (mock 晴天, 不发真实 HTTP)
    python scripts/amap-weather.py "110000"

    # 2. 雨天 (mock 中雨, condition=rainy, pop=0.85)
    python scripts/amap-weather.py "310000" --fixture rainy_base

    # 3. 预报模式 (extensions=all, 返回未来 3 天预报)
    python scripts/amap-weather.py "110000" --extensions all --fixture forecast_all

    # 4. 错误码: AMAP_INVALID_KEY (mock infocode=10001)
    python scripts/amap-weather.py "110000" --fixture invalid_key

    # 5. 错误码: AMAP_QUOTA_EXCEEDED (mock infocode=10044)
    python scripts/amap-weather.py "110000" --fixture quota_exceeded

    # 6. 错误码: AMAP_LOCATION_INVALID (mock infocode=20001)
    python scripts/amap-weather.py "某个不存在的地标" --fixture location_invalid

    # 7. 入参校验 (空 location → ValueError)
    python scripts/amap-weather.py ""

    # 8. 真实调用 (需要 .env 中 AMAP_API_KEY)
    python scripts/amap-weather.py "110000" --live

    # 9. 性能硬上限 (>1s 报错退出, 真实 AMAP SLA)
    python scripts/amap-weather.py "110000" --live --max-elapsed-ms 1000
"""

from __future__ import annotations

# 允许从仓库根目录直接 `python scripts/amap-weather.py "..."`.
# backend/ 与 scripts/ 同级, 把 backend/ 加到 sys.path 让 `from app.xxx` 工作.
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

import httpx
import respx
from app.core.exceptions import (
    AmapInvalidKeyError,
    AmapLocationInvalidError,
    AmapNetworkError,
    AmapQuotaExceededError,
)
from app.mcp.amap.client import AmapClient
from app.mcp.amap.weather import amap_get_weather

_FIXTURE_PATH = _BACKEND_DIR / "tests" / "fixtures" / "amap_weather_responses.json"
_AMAP_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> dict[str, object]:
    """从 fixture JSON 读出指定 key 的负载."""
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    payload = data[name]
    if not isinstance(payload, dict):
        raise SystemExit(f"fixture {name!r} 不是 dict")
    return payload


def _default_client() -> AmapClient:
    """构造测试用 client (不发真实请求). timeout=0.5s 加速失败."""
    return AmapClient(api_key="smoke-key", timeout_seconds=0.5, max_retries=1)


# ---------------------------------------------------------------------------
# Step 1: 真实或 mock 调用 (主路径)
# ---------------------------------------------------------------------------


async def _run_with_mock(
    location: str,
    extensions: str,
    fixture_name: str,
) -> dict[str, Any]:
    """用 respx mock 高德回包, 跑 `amap_get_weather` 一次."""
    started = time.monotonic()
    payload = _load_fixture(fixture_name)

    with respx.mock(assert_all_called=True) as router:
        router.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))
        client = _default_client()
        try:
            result = await amap_get_weather(
                location=location,
                extensions=extensions,  # type: ignore[arg-type]
                client=client,
            )
        finally:
            await client.aclose()

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "mode": "mock",
        "fixture": fixture_name,
        "elapsed_ms": elapsed_ms,
        "result": result,
        "result_location": result["location"],
        "result_condition": result["condition"],
        "result_temperature": result["temperature_celsius"],
        "result_pop": result["precipitation_probability"],
        "result_forecast_3h_len": len(result["forecast_3h"]),
    }


async def _run_with_live(
    location: str,
    extensions: str,
) -> dict[str, Any]:
    """真实调一次高德 (需要 .env 中 AMAP_API_KEY + 走真实网络)."""
    started = time.monotonic()
    # client=None → 走 `get_amap_client` 工厂, 从 .env 读 AMAP_API_KEY
    result = await amap_get_weather(
        location=location,
        extensions=extensions,  # type: ignore[arg-type]
        client=None,
    )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "mode": "live",
        "elapsed_ms": elapsed_ms,
        "result": result,
        "result_location": result["location"],
        "result_condition": result["condition"],
        "result_temperature": result["temperature_celsius"],
        "result_pop": result["precipitation_probability"],
        "result_forecast_3h_len": len(result["forecast_3h"]),
    }


# ---------------------------------------------------------------------------
# Step 2: 错误路径 (不调真实 HTTP, 直接触发 AmapError)
# ---------------------------------------------------------------------------


def _run_param_validation() -> dict[str, Any]:
    """入参校验 — 不发 HTTP, 直接构造非法输入, 期望抛 ValueError."""
    err_code: str | None = None
    err_msg: str | None = None
    try:
        asyncio.run(
            amap_get_weather(
                location="",
                client=_default_client(),
            )
        )
    except ValueError as exc:
        err_code = "VALUE_ERROR"
        err_msg = str(exc)

    return {
        "step": "param_validation",
        "rejected_as_expected": err_code == "VALUE_ERROR",
        "error_code": err_code,
        "error_message": err_msg,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F031 高德 MCP 天气手工试跑 (默认 mock, --live 真实调用)"
    )
    parser.add_argument(
        "location",
        nargs="?",
        default="110000",
        help='location (adcode / "lng,lat" / 地标名, 默认 "110000" 北京)',
    )
    parser.add_argument(
        "--extensions",
        choices=["base", "all"],
        default="base",
        help="气象类型 (默认 base 实况, all 预报)",
    )
    parser.add_argument(
        "--fixture",
        default="sunny_base",
        help=(
            "mock 模式下要注入的 fixture key, 取自 "
            "backend/tests/fixtures/amap_weather_responses.json. 默认 sunny_base"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="真实调用高德 (需要 .env 中 AMAP_API_KEY)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只跑入参校验 (不调 HTTP)",
    )
    parser.add_argument(
        "--max-elapsed-ms",
        type=int,
        default=None,
        help="硬上限 (含 mock), 超过 exit 2",
    )
    args = parser.parse_args(argv)

    steps: list[dict[str, Any]] = []
    overall_pass = True

    # ---- 入参校验 (单独跑) ----
    if args.validate_only:
        validation = _run_param_validation()
        steps.append(validation)
        overall_pass = overall_pass and validation["rejected_as_expected"]
        print(json.dumps({"steps": steps, "overall_pass": overall_pass}, ensure_ascii=False))
        return 0 if overall_pass else 1

    # ---- 主路径 ----
    try:
        if args.live:
            main_result = asyncio.run(
                _run_with_live(
                    location=args.location,
                    extensions=args.extensions,
                )
            )
        else:
            main_result = asyncio.run(
                _run_with_mock(
                    location=args.location,
                    extensions=args.extensions,
                    fixture_name=args.fixture,
                )
            )
    except AmapInvalidKeyError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False))
        sys.stderr.write(f"AMAP_INVALID_KEY: {exc.message}\n")
        return 3
    except AmapQuotaExceededError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False))
        sys.stderr.write(f"AMAP_QUOTA_EXCEEDED: {exc.message}\n")
        return 4
    except AmapNetworkError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False))
        sys.stderr.write(f"AMAP_NETWORK_ERROR: {exc.message}\n")
        return 5
    except AmapLocationInvalidError as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False))
        sys.stderr.write(f"AMAP_LOCATION_INVALID: {exc.message}\n")
        return 6

    steps.append(main_result)

    # ---- 性能 / 主路径硬上限 ----
    total_elapsed_ms = main_result["elapsed_ms"]
    if args.max_elapsed_ms is not None and total_elapsed_ms > args.max_elapsed_ms:
        sys.stderr.write(
            f"elapsed_ms {total_elapsed_ms} exceeds --max-elapsed-ms {args.max_elapsed_ms}\n"
        )
        return 2

    # ---- 验收点 (mock 与 live 都跑) ----
    weather = main_result["result"]

    # F031 §2: 条件必须在合法枚举内
    valid_conditions = {"sunny", "cloudy", "rainy", "snowy", "foggy", "dust"}
    condition_ok = weather["condition"] in valid_conditions
    if not condition_ok:
        logger.warning("condition %r not in valid set", weather["condition"])

    # F031 §2: precipitation_probability 必须在 [0, 1]
    pop = weather["precipitation_probability"]
    pop_ok = isinstance(pop, (int, float)) and 0.0 <= pop <= 1.0

    # F031 §2: forecast_3h 必须恰好 3 条
    forecast_len_ok = len(weather["forecast_3h"]) == 3

    # F031 §2 SLA: live 模式 1s 内返回; mock 模式 < 200ms 视为健康
    sla_ms = 1000 if args.live else 200
    sla_ok = total_elapsed_ms <= sla_ms
    if not sla_ok:
        logger.warning("SLA miss: %dms > %dms", total_elapsed_ms, sla_ms)

    # F031 §3.2: fetched_at 必须是 datetime 字段
    fetched_at = weather["fetched_at"]
    fetched_at_ok = hasattr(fetched_at, "isoformat")

    steps.append(
        {
            "step": "validation",
            "condition_check": condition_ok,
            "condition_value": weather["condition"],
            "pop_check": pop_ok,
            "pop_value": pop,
            "forecast_3h_length_check": forecast_len_ok,
            "forecast_3h_length": len(weather["forecast_3h"]),
            "sla_check_ms": sla_ok,
            "sla_threshold_ms": sla_ms,
            "fetched_at_check": fetched_at_ok,
        }
    )
    overall_pass = (
        overall_pass
        and condition_ok
        and pop_ok
        and forecast_len_ok
        and sla_ok
        and fetched_at_ok
    )

    print(
        json.dumps(
            {"overall_pass": overall_pass, "total_elapsed_ms": total_elapsed_ms, "steps": steps},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())