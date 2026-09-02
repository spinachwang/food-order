"""F002 router 手工试跑入口。

CLI：`python scripts/dev_route.py "<消息>"`，打印 router 决策结果。
不需要 MySQL、不需要 LLM API key —— 用内联偏好 + `FakeLLMProvider`。

设计目的：开发 / 调试阶段快速验证规则层 / 模糊层 / LLM 兜底 / 降级
路径，覆盖所有 router 行为分支。生产里 router 只在 LangGraph 内部被
调用（`route_cuisines(state) -> partial state`），不会对外暴露 HTTP。

用法：
    # 规则层
    python scripts/dev_route.py "想吃辣的"

    # 模糊层（"随便"）
    python scripts/dev_route.py "今天都行，看你"

    # LLM 兜底（灰色地带）
    python scripts/dev_route.py "想吃点暖胃的"

    # 互斥标签（降级 LLM）
    python scripts/dev_route.py "想吃清淡的辣菜"

    # 空消息 / 乱码
    python scripts/dev_route.py ""
    python scripts/dev_route.py "！！！@#￥"

    # 自定义 LLM 回包
    python scripts/dev_route.py "想吃点暖胃的" \\
        --llm-response '{"selected_cuisines":["suzhou","japanese"],"routing_reason":"清淡口 → 苏 + 日"}'

    # 自定义偏好（覆盖默认值）
    python scripts/dev_route.py "随便" \\
        --cuisine-weights '{"sichuan":0.9,"cantonese":0.1,"hunan":0.1}' \\
        --allergies '["peanut"]'
"""

from __future__ import annotations

# 允许从仓库根目录直接 `python scripts/dev_route.py "..."` 而不需要 PYTHONPATH。
# backend/ 与 scripts/ 同级，把 backend/ 加到 sys.path 让 `from app.xxx` 工作。
import argparse
import asyncio
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.agents.llm.testing import FakeLLMProvider  # noqa: E402
from app.agents.main_router import route_cuisines  # noqa: E402
from app.agents.state import AgentState, UserPreferencesDict  # noqa: E402
from app.core.constants import CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT  # noqa: E402


def _parse_optional_json(raw: str | None, default: object, label: str) -> object:
    """CLI `--xxx '{"a":1}'` 解析；解析失败给可读报错。"""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"--{label} 不是合法 JSON：{e}") from e


def _build_prefs(
    cuisine_weights_raw: str | None,
    allergies_raw: str | None,
    seed: int,
) -> UserPreferencesDict:
    """CLI args → `UserPreferencesDict`；没传就走中性默认。"""
    weights = _parse_optional_json(
        cuisine_weights_raw, dict.fromkeys(CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT), "cuisine-weights"
    )
    allergies = _parse_optional_json(allergies_raw, [], "allergies")
    if not isinstance(weights, dict):
        raise SystemExit("--cuisine-weights 必须是 JSON 对象")
    if not isinstance(allergies, list):
        raise SystemExit("--allergies 必须是 JSON 数组")
    return {
        "user_id": f"dev-{seed}",
        "cuisine_weights": {k: float(v) for k, v in weights.items()},
        "allergies": list(allergies),
        "spice_tolerance": 2,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }


def _run(
    message: str, prefs: UserPreferencesDict, llm_response: dict[str, object]
) -> dict[str, object]:
    """同步桥 async router 调用 → 输出 dict。"""
    provider = FakeLLMProvider()
    provider.set_response(
        {
            "content": json.dumps(llm_response, ensure_ascii=False),
            "model": "fake-model",
            "usage": None,
        }
    )
    state: AgentState = {
        "user_id": prefs["user_id"],
        "user_message": message,
        "user_preferences": prefs,
    }
    out = asyncio.run(route_cuisines(state, provider=provider, rng=random.Random(0)))
    return {
        "user_id": prefs["user_id"],
        "message": message,
        "selected_cuisines": out.get("selected_cuisines"),
        "routing_reason": out.get("routing_reason"),
        "routing_log": out.get("routing_log"),
        "errors": out.get("errors"),
        "llm_called": bool(provider.calls),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F002 router 手工试跑（无需 DB / LLM key）")
    parser.add_argument("message", help="用户消息原文；空字符串 / 乱码也支持（带引号）")
    parser.add_argument(
        "--cuisine-weights",
        help='JSON 对象，例如 \'{"sichuan":0.9,"cantonese":0.5}\'；不传走中性默认',
    )
    parser.add_argument(
        "--allergies",
        help='JSON 数组，例如 \'["peanut","shellfish"]\'；不传为空',
    )
    parser.add_argument(
        "--llm-response",
        default='{"selected_cuisines":["suzhou"],"routing_reason":"暖胃 → 苏"}',
        help="LLM 兜底层返回的 JSON（规则 / 模糊层不调 LLM，所以此处不影响那两条路径）",
    )
    args = parser.parse_args(argv)

    prefs = _build_prefs(args.cuisine_weights, args.allergies, seed=0)
    llm_response = _parse_optional_json(args.llm_response, {}, "llm-response")
    if not isinstance(llm_response, dict):
        raise SystemExit("--llm-response 必须是 JSON 对象")

    result = _run(args.message, prefs, llm_response)  # type: ignore[arg-type]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
