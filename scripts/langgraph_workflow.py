"""F004 LangGraph 工作流手工试跑入口。

CLI：`python scripts/langgraph_workflow.py "<消息>"`，从 router 一路驱动到
summarize，把 SSE 事件 + 最终 state 以 JSON dump 到 stdout。

设计目的：开发 / 调试阶段快速验证 F004 全链路。当前 14 个菜系 expert 都
是 Phase 1 stub（`run()` 抛 `NotImplementedError`），所以脚本**无条件 patch
所有 expert**——不是只 patch router 选中的几个，因为：

- 14 个 patch 的复杂度是 O(1)（都是 loop over CUISINE_IDS）
- 不依赖 router 输出才能跑通，规则层 / 模糊层短路也安全
- 真实现就位后 patch 仍安全（覆盖真方法），仅失去加速意义

默认走真实 MiniMax LLM（配置从 .env 读），需要节省 token 或离线跑用
`--all-fake`；单点注入 fake 回包用 `--llm-response`。生产里 workflow 只
通过 `/api/v1/agent/chat` SSE 端点对外暴露。

用法：

    # 1. Happy path（规则层短路 — 不调 LLM；--all-fake 让环境无关）
    python scripts/langgraph_workflow.py "想吃辣的" --all-fake

    # 2. Happy path（LLM 兜底 + 自定义回包 — 节省 token / CI）
    python scripts/langgraph_workflow.py "想吃点暖胃的" \\
        --llm-response '{"selected_cuisines":["suzhou"],"routing_reason":"暖胃 → 苏"}'

    # 3. Happy path（默认走真实 MiniMax LLM；需要 .env）
    python scripts/langgraph_workflow.py "想吃点暖胃的"

    # 4. 空消息 → EMPTY_MESSAGE 错误路径
    python scripts/langgraph_workflow.py "" --all-fake

    # 5. 乱码 → EMPTY_MESSAGE 错误路径
    python scripts/langgraph_workflow.py "！！！@#￥" --all-fake

    # 6. 单菜系失败注入（验证 §3.4 容错；--fail-cuisine 必须是会被选中的菜系）
    python scripts/langgraph_workflow.py "想吃辣的" --all-fake --fail-cuisine sichuan

    # 7. 忌口互斥（rule-layer 命中 + 互斥 → 降级 LLM）
    python scripts/langgraph_workflow.py "想吃清淡的辣菜" \\
        --allergies '["peanut","shellfish"]'

    # 8. Checkpointer 验证（--checkpointer + get_state round-trip）
    python scripts/langgraph_workflow.py "今天都行" --all-fake --checkpointer

    # 9. 性能硬上限（>2 秒报错退出）
    python scripts/langgraph_workflow.py "今天都行" --all-fake --max-elapsed-ms 2000

    # 10. 互斥报错（期望非零退出）
    python scripts/langgraph_workflow.py "今天都行" \\
        --all-fake --llm-response '{"selected_cuisines":["suzhou"]}'
"""

from __future__ import annotations

# 允许从仓库根目录直接 `python scripts/langgraph_workflow.py "..."` 而不需要 PYTHONPATH。
# backend/ 与 scripts/ 同级，把 backend/ 加到 sys.path 让 `from app.xxx` 工作。
import argparse
import asyncio
import contextlib
import json
import random
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.agents.cuisines import CUISINE_REGISTRY  # noqa: E402
from app.agents.graph import GRAPH_NODE_NAMES, build_graph  # noqa: E402
from app.agents.llm.base import LLMProvider  # noqa: E402
from app.agents.llm.factory import get_llm_provider  # noqa: E402
from app.agents.llm.testing import FakeLLMProvider  # noqa: E402
from app.agents.state import AgentState, CuisineExpertOutput, UserPreferencesDict  # noqa: E402
from app.core.constants import CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.core.request_id import new_request_id, set_request_id  # noqa: E402

# Wire stdlib logging so every node / LLM call in this run logs to stderr
# with the same `rid=...` tag the FastAPI entry would set. Mirrors the
# behavior of `uvicorn app.main:app` so dev runs match prod output shape.
setup_logging()
# The FastAPI entry would set this per request; the smoke script runs once,
# so we set a single rid for the whole workflow and surface it in the
# summary so the user can grep their log file.
_RID = new_request_id()
set_request_id(_RID)


# ---------------------------------------------------------------------------
# 镜像 agent.py:58-64 — Node 名 → SSE 事件名映射（spec §4）。
# agent.py 是 source of truth，但 `_NODE_TO_SSE_EVENT` 是模块私有（不在 __all__），
# 本地重新声明避免跨 PR 改动；spec §4 + test_graph.py 是契约的不变量来源。
# ---------------------------------------------------------------------------
_NODE_TO_SSE_EVENT: dict[str, str] = {
    "route_cuisines": "cuisine_selected",
    "cuisine_fanout": "cuisine_result",
    "search_restaurants": "restaurant_found",
    "fetch_weather": "weather",
    "summarize": "recommendation",
}

# 错误码（spec F002 §6 + F004 §3.4）。
_EMPTY_MESSAGE_CODE = "EMPTY_MESSAGE"
_NO_CUISINE_MATCHED_CODE = "NO_CUISINE_MATCHED"
_ALL_CUISINES_FILTERED_CODE = "ALL_CUISINES_FILTERED"
_CUISINE_NODE_FAILED_CODE = "CUISINE_NODE_FAILED"

# `--all-fake` 模式下 router 走 LLM 兜底时的默认 canned 回包。
# 规则层 / 模糊层短路不调 LLM，所以这个默认只在「无规则命中 + 非 ambient」
# 的输入（如 "想吃点暖胃的"）下生效。
_DEFAULT_ALL_FAKE_RESPONSE: dict[str, Any] = {
    "selected_cuisines": ["sichuan", "cantonese"],
    "routing_reason": "<all-fake canned>",
}


# ---------------------------------------------------------------------------
# Helpers lifted from dev_route.py（语义保持一致）
# ---------------------------------------------------------------------------


def _parse_optional_json(raw: str | None, default: object, label: str) -> object:
    """CLI `--xxx '{"a":1}'` 解析；解析失败给可读报错。"""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"--{label} 不是合法 JSON：{e}") from e


def _build_rng(seed_arg: str) -> random.Random:
    """`--seed` → RNG：默认 `random`（与生产行为一致）；填整数则固定 seed。"""
    if seed_arg == "random":
        return random.Random()
    try:
        return random.Random(int(seed_arg))
    except ValueError as e:
        raise SystemExit(f"--seed 必须是整数或 'random'：{e}") from e


def _build_prefs(
    user_id: str,
    cuisine_weights_raw: str | None,
    allergies_raw: str | None,
) -> UserPreferencesDict:
    """CLI args → `UserPreferencesDict`；没传就走中性默认。"""
    weights = _parse_optional_json(
        cuisine_weights_raw,
        dict.fromkeys(CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT),
        "cuisine-weights",
    )
    allergies = _parse_optional_json(allergies_raw, [], "allergies")
    if not isinstance(weights, dict):
        raise SystemExit("--cuisine-weights 必须是 JSON 对象")
    if not isinstance(allergies, list):
        raise SystemExit("--allergies 必须是 JSON 数组")
    return {
        "user_id": user_id,
        "cuisine_weights": {k: float(v) for k, v in weights.items()},
        "allergies": list(allergies),
        "spice_tolerance": 2,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }


def _make_provider(
    llm_response_raw: str | None,
    all_fake: bool,
) -> tuple[LLMProvider, str]:
    """决定 LLM provider 与 mode 标签。

    - `--llm-response '<json>'` → FakeLLMProvider，content = json.dumps(parsed)
    - `--all-fake`（无 `--llm-response`）→ FakeLLMProvider，content = 默认 canned
    - 其他 → `get_llm_provider()`（从 .env 读真实 MiniMax 凭据）

    mode 标签进入输出 JSON 帮助辨识："real" / "fake" / "all-fake"。
    """
    if llm_response_raw is not None:
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

    if all_fake:
        provider = FakeLLMProvider()
        provider.set_response(
            {
                "content": json.dumps(_DEFAULT_ALL_FAKE_RESPONSE, ensure_ascii=False),
                "model": "fake-model",
                "usage": None,
            }
        )
        return provider, "all-fake"

    provider = get_llm_provider()
    return provider, "real"


# ---------------------------------------------------------------------------
# Initial state + 菜系 stub
# ---------------------------------------------------------------------------


def _build_initial_state(
    user_id: str,
    session_id: str | None,
    message: str,
    prefs: UserPreferencesDict,
) -> AgentState:
    """照 api/v1/agent.py:93-100 的契约构造 AgentState。"""
    return {
        "user_id": user_id,
        "user_message": message,
        "session_id": session_id,
        "location_override": None,
        "user_preferences": prefs,
    }


def _canned_cuisine_output(cuisine_id: str) -> CuisineExpertOutput:
    """Phase 1 stub 替身：固定形状的 CuisineExpertOutput dict。

    实际由 `CUISINE_REGISTRY[cid].run()` 抛 `NotImplementedError`，所以
    smoke 必须注入；真实实现就位后此函数仍可用，但失去加速意义。
    """
    expert = CUISINE_REGISTRY.get(cuisine_id)
    display = getattr(expert, "display_name", cuisine_id) if expert else cuisine_id
    return {
        "cuisine_id": cuisine_id,
        "conclusion": f"<canned {display}>",
        "keywords": [display, "推荐"],
        "matched_allergies": [],
    }


@contextlib.contextmanager
def _patch_all_cuisines(fail_cuisine: str | None):
    """无条件 patch 所有 14 个 expert 的 `run()`。

    - 默认 `return_value = _canned_cuisine_output(cid)`
    - 若 `cid == fail_cuisine` → `side_effect = RuntimeError(...)`

    复杂度 O(1)（loop over CUISINE_IDS）；不依赖 router 输出，规则层 /
    模糊层短路也安全。
    """
    if fail_cuisine is not None and fail_cuisine not in CUISINE_IDS:
        raise SystemExit(
            f"--fail-cuisine 必须是已知 cuisine_id（{fail_cuisine} 未知）"
        )
    with contextlib.ExitStack() as stack:
        for cid in CUISINE_IDS:
            expert = CUISINE_REGISTRY.get(cid)
            if expert is None:
                continue
            cm = stack.enter_context(patch.object(expert, "run"))
            if cid == fail_cuisine:
                cm.side_effect = RuntimeError(
                    f"--fail-cuisine injected for {cid}"
                )
            else:
                cm.return_value = _canned_cuisine_output(cid)
        yield


# ---------------------------------------------------------------------------
# SSE 事件收集 — 镜像 api/v1/agent.py:151-219
# ---------------------------------------------------------------------------


def _to_sse_event_name(node_name: str) -> str | None:
    """Node 名 → SSE 事件名；silent nodes 返回 None。"""
    return _NODE_TO_SSE_EVENT.get(node_name)


def _payload_for_event(node_name: str, event_output: dict[str, Any]) -> dict[str, Any] | None:
    """镜像 `_state_payload_for_event`（agent.py:186-219）。"""
    if not isinstance(event_output, dict):
        return None
    if node_name == "route_cuisines":
        return {
            "cuisines": list(event_output.get("selected_cuisines") or []),
            "routing_reason": str(event_output.get("routing_reason") or ""),
        }
    if node_name == "cuisine_fanout":
        return {"results": dict(event_output.get("cuisine_results") or {})}
    if node_name == "search_restaurants":
        return {"restaurant_lists": dict(event_output.get("restaurant_lists") or {})}
    if node_name == "fetch_weather":
        return {"weather": event_output.get("weather")}
    if node_name == "summarize":
        return {"recommendation": event_output.get("recommendation")}
    return None


def _frame_to_event_tuple(event: Any) -> tuple[str, dict[str, Any]] | None:
    """镜像 `_frame_from_event`（agent.py:151-183）的过滤。

    跳过 on_chain_start / on_chain_stream / __start__ / _write / LangGraph 内部事件；
    只取 on_chain_end 且 name 命中 GRAPH_NODE_NAMES 且非 silent node。
    """
    if not isinstance(event, dict):
        return None
    name = str(event.get("name") or "")
    event_type = str(event.get("event") or "")
    if name not in GRAPH_NODE_NAMES:
        return None
    if event_type != "on_chain_end":
        return None
    sse_event = _to_sse_event_name(name)
    if sse_event is None:
        return None
    output = event.get("data", {}).get("output")
    payload = _payload_for_event(name, output if isinstance(output, dict) else {})
    if payload is None:
        return None
    return (sse_event, payload)


async def _collect_events(
    compiled: Any,
    initial_state: AgentState,
    config: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """drain `astream_events(..., version="v2")` 并过滤出 SSE 帧元组。"""
    out: list[tuple[str, dict[str, Any]]] = []
    async for event in compiled.astream_events(
        initial_state, config=config, version="v2"
    ):
        mapped = _frame_to_event_tuple(event)
        if mapped is not None:
            out.append(mapped)
    return out


# ---------------------------------------------------------------------------
# Workflow runner
# ---------------------------------------------------------------------------


def _assemble_output(
    args: argparse.Namespace,
    final_state: dict[str, Any],
    events: list[tuple[str, dict[str, Any]]],
    provider_mode: str,
    provider_model: Any,
    elapsed_ms: int,
    checkpointer_enabled: bool,
    checkpoint_round_trip_ok: bool | None,
) -> dict[str, Any]:
    """把 ainvoke final_state + astream_events timeline 拼成 stdout JSON。

    字段优先级：SSE 事件流覆盖 ainvoke 状态（事件流是 spec §4 的契约），
    但 `errors` / `cuisine_results` 等 ainvoke 才有的字段保留。
    """
    # SSE 事件 → 顶层字段映射。
    selected_cuisines: list[str] = []
    routing_reason: str = ""
    cuisine_results: dict[str, Any] = {}
    restaurant_lists: dict[str, Any] = {}
    weather: Any = None
    recommendation: Any = None
    for sse_name, payload in events:
        if sse_name == "cuisine_selected":
            selected_cuisines = list(payload.get("cuisines") or [])
            routing_reason = str(payload.get("routing_reason") or "")
        elif sse_name == "cuisine_result":
            cuisine_results = dict(payload.get("results") or {})
        elif sse_name == "restaurant_found":
            restaurant_lists = dict(payload.get("restaurant_lists") or {})
        elif sse_name == "weather":
            weather = payload.get("weather")
        elif sse_name == "recommendation":
            recommendation = payload.get("recommendation")

    # ainvoke final_state 是完整 State（包括 errors 等 SSE 不发的字段）。
    errors = list(final_state.get("errors") or []) if isinstance(final_state, dict) else []
    routing_log = list(final_state.get("routing_log") or []) if isinstance(final_state, dict) else []

    return {
        "user_id": args.user_id,
        "session_id": args.session_id,
        "message": args.message,
        "provider_mode": provider_mode,
        "provider_model": provider_model,
        "seed": args.seed,
        "selected_cuisines": selected_cuisines,
        "routing_reason": routing_reason,
        "routing_log": routing_log,
        "cuisine_results": cuisine_results,
        "restaurant_lists": restaurant_lists,
        "weather": weather,
        "recommendation": recommendation,
        "errors": errors,
        "events": [{"name": n, "payload": p} for n, p in events],
        "checkpointer_enabled": checkpointer_enabled,
        "checkpoint_state_round_trip_ok": checkpoint_round_trip_ok,
        "fail_cuisine": args.fail_cuisine,
        "elapsed_ms": elapsed_ms,
    }


async def _run(args: argparse.Namespace, prefs: UserPreferencesDict, provider: LLMProvider, rng: random.Random) -> dict[str, Any]:
    """编排：build_graph → ainvoke 拿 final_state → astream_events 拿事件 → 拼输出。

    LangGraph 节点只用 `state` 调，不传 kwargs——F002 router 的 `provider`
    注入只能通过 patch `app.agents.main_router.get_llm_provider` 实现。
    否则 `_route_via_llm` 会回退到 `get_llm_provider()`（lru_cache 真实 provider），
    `--llm-response` / `--all-fake` 形同虚设。
    """
    initial_state = _build_initial_state(
        args.user_id, args.session_id, args.message, prefs
    )
    thread_id = args.session_id or args.user_id
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    compiled = build_graph(checkpointer=args.checkpointer)

    started = time.monotonic()
    with patch("app.agents.main_router.get_llm_provider", return_value=provider):
        # Run #1: ainvoke 拿完整 final_state（含 errors / routing_log 等 SSE 不发的字段）。
        final_state = await compiled.ainvoke(initial_state, config=config)
        # Run #2: astream_events 拿事件时间线（spec §4 契约）。
        events = await _collect_events(compiled, initial_state, config)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    # 可选：checkpointer round-trip 探测（仅 --checkpointer 时执行）。
    checkpoint_round_trip_ok: bool | None = None
    if args.checkpointer:
        snapshot = await compiled.aget_state(config)
        checkpoint_round_trip_ok = bool(
            snapshot is not None
            and isinstance(snapshot.values, dict)
            and snapshot.values.get("user_id") == args.user_id
        )

    # --fail-cuisine 若未被 router 选中则 patch 静默 no-op；给个 stderr 警告。
    if args.fail_cuisine is not None:
        selected = final_state.get("selected_cuisines") or []
        if args.fail_cuisine not in selected:
            sys.stderr.write(
                f"warn: --fail-cuisine={args.fail_cuisine} 不在 selected_cuisines "
                f"{selected}，patch 静默 no-op；要看到 CUISINE_NODE_FAILED 需选个会被 "
                f"router 选中的菜系（例：--fail-cuisine sichuan + '想吃辣的'）。\n"
            )

    return _assemble_output(
        args=args,
        final_state=final_state if isinstance(final_state, dict) else {},
        events=events,
        provider_mode=_provider_mode_label(args, provider),
        provider_model=getattr(provider, "model", None),
        elapsed_ms=elapsed_ms,
        checkpointer_enabled=args.checkpointer,
        checkpoint_round_trip_ok=checkpoint_round_trip_ok,
    )


def _provider_mode_label(args: argparse.Namespace, provider: LLMProvider) -> str:
    """根据 args 推导 mode 标签（all-fake / fake / real）。"""
    if args.all_fake:
        return "all-fake"
    if args.llm_response is not None:
        return "fake"
    return "real"


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F004 LangGraph 工作流手工试跑（默认走真实 MiniMax LLM）"
    )
    parser.add_argument("message", help="用户消息原文；空串 / 乱码也支持（带引号）")
    parser.add_argument(
        "--user-id",
        default="dev",
        help="Echo dev_route.py；区分多次 smoke 调用的 thread_id",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="透传到 graph configurable.thread_id；不传则回落到 --user-id",
    )
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
        help="注入 FakeLLM 回包（不消耗 token）；不指定则走真实 provider",
    )
    parser.add_argument(
        "--all-fake",
        action="store_true",
        help="无 .env / 无 LLM / 无 DB 也能跑（仍走真 router，但喂 FakeLLM）",
    )
    parser.add_argument(
        "--seed",
        default="random",
        help="router ambient RNG 种子；默认 'random'（生产语义）；整数固定 seed",
    )
    parser.add_argument(
        "--checkpointer",
        action="store_true",
        help="build_graph(checkpointer=True) + get_state round-trip 探测",
    )
    parser.add_argument(
        "--fail-cuisine",
        default=None,
        help="指定 cuisine_id 让其 expert 抛 RuntimeError（验证 §3.4 容错）",
    )
    parser.add_argument(
        "--max-elapsed-ms",
        type=int,
        default=None,
        help="硬上限；超过 exit 2；不指定则仅报告 elapsed_ms",
    )
    args = parser.parse_args(argv)

    # 互斥：--all-fake + --llm-response 都装 FakeLLMProvider，silent override 藏 bug。
    if args.all_fake and args.llm_response is not None:
        parser.error("--all-fake 与 --llm-response 互斥")

    # session_id 回落到 user_id。
    if args.session_id is None:
        args.session_id = args.user_id

    prefs = _build_prefs(args.user_id, args.cuisine_weights, args.allergies)
    provider, _mode = _make_provider(args.llm_response, args.all_fake)
    rng = _build_rng(args.seed)

    try:
        with _patch_all_cuisines(args.fail_cuisine):
            try:
                result = asyncio.run(_run(args, prefs, provider, rng))
            finally:
                # 真实 provider 持有 httpx.AsyncClient；显式关闭避免泄漏。
                if hasattr(provider, "aclose"):
                    asyncio.run(provider.aclose())
    finally:
        # `with` ExitStack 已经自动 close，但这里留个兜底可观察点。
        pass

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    if args.max_elapsed_ms is not None and result["elapsed_ms"] > args.max_elapsed_ms:
        sys.stderr.write(
            f"elapsed_ms {result['elapsed_ms']} exceeds --max-elapsed-ms "
            f"{args.max_elapsed_ms}\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
