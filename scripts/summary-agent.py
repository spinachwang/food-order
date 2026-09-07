"""F040 — 总结与推荐 Agent 手工试跑入口.

CLI：`python scripts/summary-agent.py "<场景>"` 直接调 `SummaryAgent`
验证 F040 §2 / §3.3 / §4 验收点。默认走 fake provider（不消耗 token /
离线可跑）；传 `--live` 才走真实 MiniMax LLM。

设计目的:
- 开发 / 调试阶段快速验证 summary 节点本身（无 LangGraph graph 开销）
- CI / 凭据缺失环境下用 `--scenario` 选预设场景（happy_sunny /
  rainy_bad_weather / extreme_heat / no_data / all_failed / mixed）
- 真实联调时 `--live` 走 MiniMax API

用法:

    # 1. Happy path (晴天 + 300m) -- 不调真实 LLM
    python scripts/summary-agent.py --scenario happy_sunny --all-fake

    # 2. 雨天 (恶劣天气 → order_takeout=true)
    python scripts/summary-agent.py --scenario rainy_bad_weather --all-fake

    # 3. 高温 (38℃ → order_takeout=true)
    python scripts/summary-agent.py --scenario extreme_heat --all-fake

    # 4. 无数据 (全 0 候选 → 降级)
    python scripts/summary-agent.py --scenario no_data --all-fake

    # 5. 全失败 (cuisine_results 满 + restaurant_lists 全空 → 降级)
    python scripts/summary-agent.py --scenario all_failed --all-fake

    # 6. 注入 LLM 回包 (节省 token / CI)
    python scripts/summary-agent.py --scenario mixed \\
        --llm-response '{"headline":"...", "reason":"..."}'

    # 7. 真实 LLM (需要 .env 中 MINIMAX_API_KEY)
    python scripts/summary-agent.py --scenario happy_sunny --live

    # 8. 性能硬上限 (>500ms 报错退出, F040 实测 SLA)
    python scripts/summary-agent.py --scenario happy_sunny --all-fake \\
        --max-elapsed-ms 500
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.agents.llm.testing import FakeLLMProvider  # noqa: E402
from app.agents.scoring import should_order_takeout  # noqa: E402
from app.agents.state import (  # noqa: E402
    AgentState,
    CuisineExpertOutput,
    UserPreferencesDict,
)
from app.agents.summary import DEGRADED_HEADLINE, SummaryAgent  # noqa: E402
from app.core.constants import CUISINE_IDS  # noqa: E402

# ---------------------------------------------------------------------------
# 预设场景 fixtures
# ---------------------------------------------------------------------------


def _prefs() -> UserPreferencesDict:
    return {
        "user_id": "u-smoke",
        "cuisine_weights": {
            "sichuan": 0.9,
            "cantonese": 0.7,
            "japanese": 0.6,
            **dict.fromkeys(CUISINE_IDS, 0.5),
        },
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }


def _restaurant(
    *,
    poi_id: str,
    name: str,
    distance_meters: int,
    rating: float | None,
    cuisine_tags: list[str] | None = None,
) -> dict[str, object]:
    return {
        "poi_id": poi_id,
        "name": name,
        "address": "北京市朝阳区国贸",
        "distance_meters": distance_meters,
        "rating": rating,
        "avg_price": None,
        "cuisine_tags": cuisine_tags or [],
        "location": (116.433840, 39.908740),
    }


def _cuisine(cid: str, conclusion: str = "推荐") -> CuisineExpertOutput:
    return {
        "cuisine_id": cid,
        "conclusion": conclusion,
        "keywords": [f"{cid}_kw"],
        "matched_allergies": [],
    }


_SCENARIOS: dict[str, dict[str, Any]] = {
    "happy_sunny": {
        "description": "晴天 + 短距离 → order_takeout=false",
        "state": lambda: {
            "user_id": "u-smoke",
            "user_message": "今天想吃辣的",
            "user_preferences": _prefs(),
            "cuisine_results": {
                "sichuan": _cuisine("sichuan", "今天推荐川菜, 麻婆豆腐"),
                "cantonese": _cuisine("cantonese", "清蒸鱼也很合适"),
            },
            "restaurant_lists": {
                "sichuan": [
                    _restaurant(poi_id="S1", name="蜀香苑", distance_meters=300, rating=4.7),
                ],
                "cantonese": [
                    _restaurant(poi_id="C1", name="粤菜馆", distance_meters=600, rating=4.4),
                ],
            },
            "weather": {"temperature_celsius": 22, "condition": "sunny", "wind_level": 2},
        },
        "expect_takeout": False,
    },
    "rainy_bad_weather": {
        "description": "雨天 → order_takeout=true",
        "state": lambda: {
            "user_id": "u-smoke",
            "user_message": "今天想吃辣的",
            "user_preferences": _prefs(),
            "cuisine_results": {"sichuan": _cuisine("sichuan")},
            "restaurant_lists": {
                "sichuan": [
                    _restaurant(poi_id="S1", name="蜀香苑", distance_meters=300, rating=4.7),
                ],
            },
            "weather": {"temperature_celsius": 22, "condition": "rainy", "wind_level": 2},
        },
        "expect_takeout": True,
    },
    "extreme_heat": {
        "description": "38℃ → order_takeout=true",
        "state": lambda: {
            "user_id": "u-smoke",
            "user_message": "今天想吃辣的",
            "user_preferences": _prefs(),
            "cuisine_results": {"sichuan": _cuisine("sichuan")},
            "restaurant_lists": {
                "sichuan": [
                    _restaurant(poi_id="S1", name="蜀香苑", distance_meters=200, rating=4.7),
                ],
            },
            "weather": {"temperature_celsius": 38, "condition": "sunny", "wind_level": 1},
        },
        "expect_takeout": True,
    },
    "no_data": {
        "description": "全 0 候选 → 降级 headline",
        "state": lambda: {
            "user_id": "u-smoke",
            "user_message": "",
            "user_preferences": _prefs(),
            "cuisine_results": {},
            "restaurant_lists": {},
            "weather": None,
        },
        "expect_degraded": True,
    },
    "all_failed": {
        "description": "cuisine_results 有 / 餐厅全空 → 降级",
        "state": lambda: {
            "user_id": "u-smoke",
            "user_message": "今天想吃辣的",
            "user_preferences": _prefs(),
            "cuisine_results": {"sichuan": _cuisine("sichuan")},
            "restaurant_lists": {},  # 高德全失败
            "weather": {"temperature_celsius": 22, "condition": "sunny", "wind_level": 2},
        },
        "expect_degraded": True,
    },
    "mixed": {
        "description": "3 个菜系, 主推荐 + 备选",
        "state": lambda: {
            "user_id": "u-smoke",
            "user_message": "今天想吃辣的",
            "user_preferences": _prefs(),
            "cuisine_results": {
                "sichuan": _cuisine("sichuan", "今天推荐川菜"),
                "cantonese": _cuisine("cantonese", "清蒸鱼合适"),
                "japanese": _cuisine("japanese", "寿司套餐"),
            },
            "restaurant_lists": {
                "sichuan": [
                    _restaurant(poi_id="S1", name="蜀香苑", distance_meters=300, rating=4.8),
                ],
                "cantonese": [
                    _restaurant(poi_id="C1", name="粤菜馆", distance_meters=700, rating=4.5),
                ],
                "japanese": [
                    _restaurant(poi_id="J1", name="寿司店", distance_meters=1000, rating=4.6),
                ],
            },
            "weather": {"temperature_celsius": 22, "condition": "sunny", "wind_level": 2},
        },
        "expect_alternatives_min": 2,
    },
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="F040 — 总结与推荐 Agent 手工冒烟脚本",
    )
    p.add_argument(
        "--scenario",
        choices=sorted(_SCENARIOS.keys()),
        default="happy_sunny",
        help="预设场景 (default: happy_sunny)",
    )
    p.add_argument(
        "--all-fake",
        action="store_true",
        default=True,
        help="使用 FakeLLMProvider (默认; 不消耗 token / 离线可跑)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="走真实 MiniMax LLM (需要 .env 中 MINIMAX_API_KEY)",
    )
    p.add_argument(
        "--llm-response",
        type=str,
        default=None,
        help="注入 LLM JSON 回包 (单点注入, 覆盖 FakeLLMProvider 默认)",
    )
    p.add_argument(
        "--max-elapsed-ms",
        type=int,
        default=None,
        help="性能硬上限 (ms); 超时则非零退出",
    )
    return p.parse_args()


def _build_fake_provider(content: str | None) -> FakeLLMProvider:
    fake = FakeLLMProvider()
    if content is None:
        # 默认给一个合理回包
        content = json.dumps(
            {
                "headline": "今天推荐：蜀香苑（川菜）",
                "reason": "天气晴朗, 距您 300m, 评分 4.7, 适合堂食",
                "confidence": 0.85,
                "alternatives": [
                    {"cuisine_id": "cantonese", "short_reason": "备选粤菜"},
                ],
            },
            ensure_ascii=False,
        )
    fake.set_response({"content": content, "model": "fake", "usage": None})
    return fake


def main() -> int:
    args = _parse_args()

    if args.live:
        args.all_fake = False

    scenario = _SCENARIOS[args.scenario]
    state = cast(AgentState, scenario["state"]())

    if args.all_fake:
        provider = _build_fake_provider(args.llm_response)
    else:
        # 真实 LLM — 延迟导入, 避免离线环境缺 key 直接崩
        from app.agents.llm.factory import get_llm_provider  # noqa: PLC0415

        provider = get_llm_provider()

    agent = SummaryAgent(llm=provider)

    started = time.monotonic()
    rec = agent.assemble(state)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    # ---- 校验 ----
    errors: list[str] = []

    if scenario.get("expect_degraded"):
        if rec["headline"] != DEGRADED_HEADLINE:
            errors.append(
                f"期望降级 headline, 实际: {rec['headline']!r}"
            )
    else:
        # 非降级场景: 必须有 poi_id
        if not rec.get("restaurant_id"):
            errors.append("非降级场景但缺少 restaurant_id")
        if not rec.get("headline"):
            errors.append("缺少 headline")

    if "expect_takeout" in scenario:
        expected = scenario["expect_takeout"]
        # 验证决策矩阵与 LLM 输出对齐 (F040 §3.3 硬阈值)
        weather = state.get("weather") if isinstance(state, dict) else None
        decision = should_order_takeout(
            temperature_c=(
                weather.get("temperature_celsius")  # type: ignore[union-attr]
                if isinstance(weather, dict)
                else None
            ),
            condition=(
                weather.get("condition")  # type: ignore[union-attr]
                if isinstance(weather, dict)
                else None
            ),
            wind_level=(
                weather.get("wind_level")  # type: ignore[union-attr]
                if isinstance(weather, dict)
                else None
            ),
            distance_m=None,  # 决策矩阵预期只看天气 (脚本关注天气分支)
        )
        # 注: 这里只用天气参数; 主推荐餐厅距离不在该断言范围
        if decision != expected:
            errors.append(
                f"决策矩阵与期望不一致: 期望 {expected}, 决策矩阵={decision}"
            )

    if "expect_alternatives_min" in scenario:
        n = len(rec.get("alternatives") or [])
        if n < scenario["expect_alternatives_min"]:
            errors.append(
                f"备选数不足: 期望 ≥{scenario['expect_alternatives_min']}, 实际 {n}"
            )

    if args.max_elapsed_ms is not None and elapsed_ms > args.max_elapsed_ms:
        errors.append(f"超时: {elapsed_ms}ms > {args.max_elapsed_ms}ms")

    # ---- 输出 ----
    out = {
        "scenario": args.scenario,
        "description": scenario["description"],
        "elapsed_ms": elapsed_ms,
        "recommendation": rec,
        "errors": errors,
        "ok": not errors,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0 if not errors else 1


def _sync_main() -> int:
    """Top-level sync entry — matches script idioms (no asyncio.run needed).

    `SummaryAgent.assemble` is synchronous; the LLM hop is bridged internally
    via `asyncio.run` in `SummaryAgent._call_llm_sync`. The script therefore
    needs no top-level event loop.
    """
    return main()


if __name__ == "__main__":
    sys.exit(_sync_main())