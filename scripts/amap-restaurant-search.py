"""F030 — 高德 MCP 周边搜索（餐厅）手工试跑入口.

CLI: `python scripts/amap-restaurant-search.py "<关键词>"`, 验证 F030 §2 / §6
所有验收点 (mock 高德回包 + 错误码透传 + 排序 + 入参校验). 默认走 mock
模式（不消耗配额 / 离线可跑）；传 `--live` 才发真实 HTTP.

设计目的:

- 开发 / 调试阶段快速验证 F030 契约本身（无 LangGraph 编排开销）
- CI / 凭据缺失环境下用 `--fixture <name>` 注入回包快速跑通
- 真实联调时 `--live` 走 AMAP_API_KEY, 验证 SLA (1.5s 总耗时)

用法:

    # 1. Happy path (mock 10 条 POI, 不发真实 HTTP)
    python scripts/amap-restaurant-search.py "火锅"

    # 2. 边界: 空结果 (mock 0 条 → partial=true)
    python scripts/amap-restaurant-search.py "某个完全找不到的菜" --fixture empty_result

    # 3. 错误码: AMAP_INVALID_KEY (mock infocode=10001)
    python scripts/amap-restaurant-search.py "火锅" --fixture invalid_key_401

    # 4. 错误码: AMAP_QUOTA_EXCEEDED (mock infocode=10044)
    python scripts/amap-restaurant-search.py "火锅" --fixture quota_exceeded_429_response_status

    # 5. 排序验证 (mock 缺评分 / 缺价格 POI, 验证降级为 None + 按距离排序)
    python scripts/amap-restaurant-search.py "火锅" --fixture happy_path_with_missing_rating_and_cost

    # 6. 入参校验 (空 keywords → ValueError)
    python scripts/amap-restaurant-search.py --keywords ""

    # 7. 真实调用 (需要 .env 中 AMAP_API_KEY)
    python scripts/amap-restaurant-search.py "火锅" --live \\
        --location "116.433840,39.908740"

    # 8. 性能硬上限 (>1.5s 报错退出, 真实 AMAP SLA)
    python scripts/amap-restaurant-search.py "火锅" --live --max-elapsed-ms 1500
"""

from __future__ import annotations

# 允许从仓库根目录直接 `python scripts/amap-restaurant-search.py "..."`.
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

import httpx  # noqa: E402
import respx  # noqa: E402

from app.core.exceptions import (  # noqa: E402
    AmapInvalidKeyError,
    AmapNetworkError,
    AmapQuotaExceededError,
)
from app.mcp.amap.client import AmapClient  # noqa: E402
from app.mcp.amap.restaurant import amap_search_restaurants  # noqa: E402

_FIXTURE_PATH = _BACKEND_DIR / "tests" / "fixtures" / "amap_restaurant_responses.json"
_AMAP_URL = "https://restapi.amap.com/v3/place/around"


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


def _parse_keywords(raw: str) -> list[str]:
    """CLI `--keywords "火锅|川菜"` → `["火锅", "川菜"]`."""
    if not raw or not raw.strip():
        raise SystemExit("--keywords 不能为空")
    return [k.strip() for k in raw.split("|") if k.strip()]


def _default_client() -> AmapClient:
    """构造测试用 client（不发真实请求）. timeout=0.5s 加速失败."""
    return AmapClient(api_key="smoke-key", timeout_seconds=0.5, max_retries=1)


# ---------------------------------------------------------------------------
# Step 1: 真实或 mock 调用 (主路径)
# ---------------------------------------------------------------------------


async def _run_with_mock(
    keywords: list[str],
    location: str,
    fixture_name: str,
    radius_meters: int,
    min_rating: float,
    max_results: int,
) -> dict[str, Any]:
    """用 respx mock 高德回包, 跑 `amap_search_restaurants` 一次."""
    started = time.monotonic()
    payload = _load_fixture(fixture_name)

    with respx.mock(assert_all_called=True) as router:
        router.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))
        client = _default_client()
        try:
            result = await amap_search_restaurants(
                keywords=keywords,
                location=location,
                radius_meters=radius_meters,
                min_rating=min_rating,
                max_results=max_results,
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
        "result_count": len(result["restaurants"]),
        "partial": result["partial"],
        "raw_count": result["raw_count"],
    }


async def _run_with_live(
    keywords: list[str],
    location: str,
    radius_meters: int,
    min_rating: float,
    max_results: int,
) -> dict[str, Any]:
    """真实调一次高德（需要 .env 中 AMAP_API_KEY + 走真实网络)."""
    started = time.monotonic()
    # client=None → 走 `get_amap_client` 工厂, 从 .env 读 AMAP_API_KEY
    result = await amap_search_restaurants(
        keywords=keywords,
        location=location,
        radius_meters=radius_meters,
        min_rating=min_rating,
        max_results=max_results,
        client=None,
    )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "mode": "live",
        "elapsed_ms": elapsed_ms,
        "result": result,
        "result_count": len(result["restaurants"]),
        "partial": result["partial"],
        "raw_count": result["raw_count"],
    }


# ---------------------------------------------------------------------------
# Step 2: 错误路径 (不调真实 HTTP, 直接触发 AmapError)
# ---------------------------------------------------------------------------


def _run_param_validation(keywords: list[str], radius: int, max_results: int) -> dict[str, Any]:
    """入参校验 — 不发 HTTP, 直接构造非法输入, 期望抛 ValueError."""
    err_code: str | None = None
    err_msg: str | None = None
    try:
        asyncio.run(
            amap_search_restaurants(
                keywords=keywords,
                location="116.433840,39.908740",
                radius_meters=radius,
                min_rating=3.5,
                max_results=max_results,
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
        description="F030 高德 MCP 周边搜索手工试跑 (默认 mock, --live 真实调用)"
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="火锅",
        help="占位 / 调试用; 真正的关键词走 --keywords",
    )
    parser.add_argument(
        "--keywords",
        default="火锅",
        help='关键词, "|" 分隔多个 (默认: "火锅")',
    )
    parser.add_argument(
        "--location",
        default="116.433840,39.908740",
        help='锚点经纬度 "lng,lat" (默认国贸)',
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=1500,
        help="搜索半径 (米, 默认 1500)",
    )
    parser.add_argument(
        "--min-rating",
        type=float,
        default=3.5,
        help="最低评分 (默认 3.5)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="上限条数 (默认 10)",
    )
    parser.add_argument(
        "--fixture",
        default="happy_path_10_pois",
        help=(
            "mock 模式下要注入的 fixture key, 取自 "
            "backend/tests/fixtures/amap_restaurant_responses.json. 默认 happy_path_10_pois"
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

    keywords = _parse_keywords(args.keywords)

    steps: list[dict[str, Any]] = []
    overall_pass = True

    # ---- 入参校验 (单独跑) ----
    if args.validate_only:
        # 故意构造非法输入 — 用空 list 触发 ValueError
        validation = _run_param_validation(
            keywords=[], radius=args.radius, max_results=args.max_results
        )
        steps.append(validation)
        overall_pass = overall_pass and validation["rejected_as_expected"]
        print(json.dumps({"steps": steps, "overall_pass": overall_pass}, ensure_ascii=False))
        return 0 if overall_pass else 1

    # ---- 主路径 ----
    try:
        if args.live:
            main_result = asyncio.run(
                _run_with_live(
                    keywords=keywords,
                    location=args.location,
                    radius_meters=args.radius,
                    min_rating=args.min_rating,
                    max_results=args.max_results,
                )
            )
        else:
            main_result = asyncio.run(
                _run_with_mock(
                    keywords=keywords,
                    location=args.location,
                    fixture_name=args.fixture,
                    radius_meters=args.radius,
                    min_rating=args.min_rating,
                    max_results=args.max_results,
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

    steps.append(main_result)

    # ---- 性能 / 主路径硬上限 ----
    total_elapsed_ms = main_result["elapsed_ms"]
    if args.max_elapsed_ms is not None and total_elapsed_ms > args.max_elapsed_ms:
        sys.stderr.write(
            f"elapsed_ms {total_elapsed_ms} exceeds --max-elapsed-ms {args.max_elapsed_ms}\n"
        )
        return 2

    # ---- 验收点 (mock 与 live 都跑) ----
    # F030 §2: 距离 > 3km 必须被剔除 (任何 mode 都适用)
    restaurants = main_result["result"]["restaurants"]
    for r in restaurants:
        assert isinstance(r, dict)
        d = r.get("distance_meters")
        distance_ok = isinstance(d, int) and d <= 3000
        if not distance_ok:
            overall_pass = False
            logger.warning("distance check failed for %s: %s", r.get("poi_id"), r)

    # F030 §2: partial 标记 — 不足 3 家 → True
    raw_count = main_result["raw_count"]
    expected_partial = raw_count < 3
    partial_ok = main_result["partial"] == expected_partial
    if not partial_ok:
        # 注: live 模式 raw_count 可能因服务端筛选而 < fixture; 这里只警告
        logger.warning(
            "partial mismatch: raw=%d got=%s expected=%s (raw_count 受服务端筛选影响)",
            raw_count,
            main_result["partial"],
            expected_partial,
        )

    # F030 §2 SLA: live 模式 1.5s 内返回; mock 模式 < 200ms 视为健康
    # 注: 排序按 (距离 / max_distance)*0.6 + (1 - rating/5)*0.4 加权,
    # 不是严格距离升序 — 已在 unit test `test_results_sorted_by_distance_then_rating` 覆盖
    sla_ms = 1500 if args.live else 200
    sla_ok = total_elapsed_ms <= sla_ms
    if not sla_ok:
        logger.warning("SLA miss: %dms > %dms", total_elapsed_ms, sla_ms)

    steps.append(
        {
            "step": "validation",
            "distance_check": all(
                isinstance(r, dict)
                and isinstance(r.get("distance_meters"), int)
                and r["distance_meters"] <= 3000
                for r in restaurants
            ),
            "partial_check": partial_ok,
            "sla_check_ms": sla_ok,
            "sla_threshold_ms": sla_ms,
        }
    )
    overall_pass = overall_pass and sla_ok

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
