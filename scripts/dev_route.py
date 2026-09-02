"""F002 router 手工试跑入口。

CLI：`python scripts/dev_route.py "<消息>"`，打印 router 决策结果。

设计目的：开发 / 调试阶段快速验证 router 全链路。默认走真实 MiniMax
LLM（配置从 .env 读），需要节省 token 时用 `--llm-response` 注入
`FakeLLMProvider` 回包。生产里 router 只在 LangGraph 内部被调用
（`route_cuisines(state) -> partial state`），不会对外暴露 HTTP。

用法：
    # 规则层（不调 LLM）
    python scripts/dev_route.py "想吃辣的"

    # 模糊层（不调 LLM）
    python scripts/dev_route.py "今天都行，看你"

    # LLM 兜底（默认走真实 MiniMax API）
    python scripts/dev_route.py "想吃点暖胃的"

    # LLM 兜底 + 自定义回包（节省 token / CI）
    python scripts/dev_route.py "想吃点暖胃的" \\
        --llm-response '{"selected_cuisines":["suzhou"],"routing_reason":"暖胃 → 苏"}'

    # 互斥标签（降级 LLM）
    python scripts/dev_route.py "想吃清淡的辣菜"

    # 空消息 / 乱码
    python scripts/dev_route.py ""
    python scripts/dev_route.py "！！！@#￥"

    # 自定义偏好
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

from app.agents.llm.base import LLMProvider  # noqa: E402
from app.agents.llm.factory import get_llm_provider  # noqa: E402
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


def _make_provider(llm_response_raw: str | None) -> tuple[LLMProvider, str]:
    """决定 LLM provider：默认真实 LLM，--llm-response 注入 FakeLLM 兜底。

    Returns (provider, mode_label) — mode_label 进入输出 JSON 帮助辨识。
    """
    if llm_response_raw is None:
        # 默认走真实 provider（从 .env 读 MiniMax key / url / model）。
        provider = get_llm_provider()
        return provider, "real"
    response_obj = _parse_optional_json(llm_response_raw, {}, "llm-response")
    if not isinstance(response_obj, dict):
        raise SystemExit("--llm-response 必须是 JSON 对象")
    provider = FakeLLMProvider()
    provider.set_response(
        {
            "content": json.dumps(response_obj, ensure_ascii=False),
            "model": "fake-model",
            "usage": None,
        }
    )
    return provider, "fake"


async def _run(
    message: str,
    prefs: UserPreferencesDict,
    provider: LLMProvider,
) -> dict[str, object]:
    """同步桥 async router 调用 → 输出 dict。

    真实 LLM 抛出的异常（auth / network / parse）不在这里吞——开发期要看
    完整错误。FakeLLM 不会抛。
    """
    state: AgentState = {
        "user_id": prefs["user_id"],
        "user_message": message,
        "user_preferences": prefs,
    }
    out = await route_cuisines(state, provider=provider, rng=random.Random(0))
    return {
        "user_id": prefs["user_id"],
        "message": message,
        "selected_cuisines": out.get("selected_cuisines"),
        "routing_reason": out.get("routing_reason"),
        "routing_log": out.get("routing_log"),
        "errors": out.get("errors"),
        "llm_called": getattr(provider, "calls", None) is not None and bool(provider.calls),
        "provider_model": getattr(provider, "model", None),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F002 router 手工试跑（默认走真实 MiniMax LLM，可注入 Fake 回包）"
    )
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
        default=None,
        help=(
            "若指定，注入 FakeLLM 回包（不消耗 token）；不指定则走真实 MiniMax "
            "provider（.env 里 MINIMAX_API_KEY 等）"
        ),
    )
    args = parser.parse_args(argv)

    prefs = _build_prefs(args.cuisine_weights, args.allergies, seed=0)
    provider, mode = _make_provider(args.llm_response)

    try:
        result = asyncio.run(_run(args.message, prefs, provider))
    finally:
        # 真实 provider 持有 httpx.AsyncClient，结束时显式关闭避免资源泄漏。
        if hasattr(provider, "aclose"):
            asyncio.run(provider.aclose())

    result["provider_mode"] = mode
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
