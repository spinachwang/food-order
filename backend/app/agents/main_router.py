"""F002 主 Agent 路由节点 — 双层路由编排。

控制流（spec F002 §3.3）：

  1. 取偏好（state["user_preferences"] 是 NotRequired；缺失时降级中性权重）
  2. 前置校验：strip 后空 / 无意义字符 → EMPTY_MESSAGE，不进下游
  3. 规则层：match_rules() 命中且无互斥冲突 → 短路返回（不调 LLM）
  4. 模糊层：is_ambient_message() 命中 → 加权抽样（不调 LLM）
  5. LLM 兜底：仅在 1-4 全部未触发时调用，整段包在 asyncio.wait_for(timeout=5s)
  6. 忌口过滤：filter_conflicts() 作用于最终列表
  7. 降级路径：超时 / 解析失败 / selected_cuisines 不可用 → NO_CUISINE_MATCHED
     + cuisine_weights top-1 兜底（ties 按 CUISINE_IDS 顺序破平）
  8. ALL_CUISINES_FILTERED → routing_reason 是用户文案「今天没合适的，换个口味吧」

本文件不引入 langgraph 依赖——签名与既有 `BaseCuisineExpert.run(state) -> dict`
同构，组图留给 F004。理由见 [ADR 0002](../../../../spec/adr/0002-router-two-layer-strategy.md)。
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import UTC, datetime

from app.agents.llm.base import LLMProvider
from app.agents.llm.factory import get_llm_provider
from app.agents.routing.allergies import filter_conflicts, zero_out_conflicts
from app.agents.routing.prompt import (
    RouterResponseError,
    build_router_prompt,
    parse_router_response,
)
from app.agents.routing.rules import (
    CONTRADICTORY_TAGS,
    EXPLICIT_RULES,
    MAX_REASON_CODEPOINTS,
    MODIFIER_RULES,
    Rule,
    is_ambient_message,
    match_rules,
    sample_by_weights,
)
from app.agents.state import (
    AgentState,
    RouterOutput,
    RoutingLogEntry,
    UserPreferencesDict,
)
from app.core.constants import CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT
from app.core.exceptions import LLMError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error codes (spec F002 §6) — module-local so callers don't need to know
# routing internals to identify what went wrong.
# ---------------------------------------------------------------------------

EMPTY_MESSAGE: str = "EMPTY_MESSAGE"
NO_CUISINE_MATCHED: str = "NO_CUISINE_MATCHED"
ALL_CUISINES_FILTERED: str = "ALL_CUISINES_FILTERED"

# 路由策略硬约束。
MAX_SELECTED_CUISINES: int = 3
ROUTER_LLM_TIMEOUT_SECONDS: float = 5.0

# 「全部候选被忌口剔除」时直接展示给用户的固定文案。
ALL_FILTERED_USER_COPY: str = "今天没合适的，换个口味吧"

# 「乱码 / 空消息」判定：strip 后不含任何 CJK / 字母 / 数字字符。
# 用 Unicode property 比 `\w` 更精确：`\w` 不覆盖 CJK Unified Ideographs。
# 范围用 \uXXXX 转义，避免源码文件被工具二次处理时范围端点漂移。
_MEANINGFUL_CHAR_RE = re.compile(r"[一-鿿぀-ゟ゠-ヿA-Za-z0-9]")

# ambient / fallback 路径的 cuisine_id → 短中文名（≤4 字）。
# 复用 prompt 模块同源数据，保持显示名一致。
_CUISINE_SHORT_NAMES: dict[str, str] = {
    "sichuan": "川菜",
    "cantonese": "粤菜",
    "shandong": "鲁菜",
    "suzhou": "苏菜",
    "zhejiang": "浙菜",
    "fujian": "闽菜",
    "hunan": "湘菜",
    "anhui": "徽菜",
    "japanese": "日料",
    "western": "西餐",
    "western_fastfood": "西式快餐",
    "chinese_fastfood": "中式快餐",
    "snacks": "小吃",
    "dessert_drinks": "甜品饮品",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def route_cuisines(
    state: AgentState,
    *,
    provider: LLMProvider | None = None,
    rng: random.Random | None = None,
) -> RouterOutput:
    """F002 main router node — entry point for the LangGraph workflow.

    Keyword-only `provider` / `rng` exist solely for test injection. In
    production both are None — `provider` is resolved lazily from the
    factory the first time the LLM layer is actually reached, and `rng`
    defaults to a process-local `random.Random()` (non-deterministic).
    """
    user_id = state["user_id"]
    message = state.get("user_message", "") or ""
    preferences = _resolve_preferences(state)

    log: list[RoutingLogEntry] = []

    # ---- 1. 前置校验：空消息 / 乱码 ------------------------------------
    if not _is_meaningful(message):
        log.append(_log("rule", f"empty or garbage message: {message!r}", 0))
        _logger.info("router[%s] rejected empty/garbage message", user_id)
        return {
            "selected_cuisines": [],
            "routing_reason": "",
            "routing_log": log,
            "errors": [
                {
                    "code": EMPTY_MESSAGE,
                    "message": "用户消息为空或不可识别",
                }
            ],
        }

    # ---- 2. 规则层 ----------------------------------------------------
    rule_started = _now_ms()
    matched = match_rules(message)
    rule_elapsed = _now_ms() - rule_started

    if matched:
        explicit_tags = [r.tag for r in matched if r in EXPLICIT_RULES]
        modifier_tags = {r.tag for r in matched if r in MODIFIER_RULES}
        contradictory = modifier_tags & CONTRADICTORY_TAGS
        # 互斥标签 + 无显式点名 → 降级 LLM（spec §3.3「灰色地带」）
        escalate = len(contradictory) >= 2 and not explicit_tags
        log.append(
            _log(
                "rule",
                f"matched tags={[r.tag for r in matched]} contradictory={bool(escalate)}",
                rule_elapsed,
            )
        )

        if not escalate:
            cuisines = _merge_rule_cuisines(matched)
            cuisines = _apply_allergy_filter(cuisines, preferences)
            log.append(_log("allergy", f"post-filter cuisines={cuisines}", 0))
            return _finalize(
                cuisines=cuisines,
                reason=_build_rule_reason(matched),
                preferences=preferences,
                log=log,
            )

    # ---- 3. 模糊层 ----------------------------------------------------
    if is_ambient_message(message):
        ambient_started = _now_ms()
        weights = zero_out_conflicts(
            preferences["cuisine_weights"], set(preferences.get("allergies", []))
        )
        rng_inst = rng or random.Random()
        n = rng_inst.choice((2, 3))
        sampled = sample_by_weights(weights, n, rng_inst)
        sampled = _apply_allergy_filter(sampled, preferences)
        ambient_elapsed = _now_ms() - ambient_started
        log.append(_log("fuzzy", f"sampled n={n} → {sampled}", ambient_elapsed))

        if not sampled:
            return _finalize_all_filtered(log)
        return _finalize(
            cuisines=sampled,
            reason=_build_ambient_reason(sampled, n),
            preferences=preferences,
            log=log,
        )

    # ---- 4. LLM 兜底层 -------------------------------------------------
    log.append(_log("rule", "no rule match → escalating to LLM", rule_elapsed))
    return await _route_via_llm(state, message, preferences, log, provider)


# ---------------------------------------------------------------------------
# Helpers — exported for tests via __all__ below
# ---------------------------------------------------------------------------


def _resolve_preferences(state: AgentState) -> UserPreferencesDict:
    """Return `user_preferences` or a neutral-weights fallback.

    Spec §3.3 — router must NOT raise if preferences are absent (TypedDict
    field is NotRequired). Neutral weights let the rule layer still fire
    on intent keywords; for ambient the sample would be uniform.
    """
    prefs = state.get("user_preferences")
    if prefs is not None:
        return prefs
    return _neutral_preferences(str(state["user_id"]))


def _neutral_preferences(user_id: str) -> UserPreferencesDict:
    """Fallback when state lacks user_preferences (key absent)."""
    return {
        "user_id": user_id,
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT),
        "allergies": [],
        "spice_tolerance": 0,
        "temperature_preference": "room",
        "default_location": None,
        "budget_lunch_min": None,
        "budget_lunch_max": None,
    }


def _is_meaningful(message: str) -> bool:
    """strip 后是否含至少一个 CJK / 字母 / 数字字符。

    「乱码」举例：`"！！！@#￥"`、`"..."` —— strip 后无任何有意义的字符。
    """
    stripped = message.strip()
    if not stripped:
        return False
    return _MEANINGFUL_CHAR_RE.search(stripped) is not None


def _merge_rule_cuisines(matched: list[Rule]) -> list[str]:
    """合并命中规则的菜系列表，按「显式 > 修饰」顺序去重，截断 3 个。

    spec §3.3：多个非互斥 tag 命中时按优先级合并；同 cuisine_id 在多个规则
    里出现只取第一次（即显式规则的优先级）。
    """
    seen: set[str] = set()
    ordered: list[str] = []
    # 先显式（matched 列表里 EXPLICIT 在前），再修饰；同 tag 内 cuisines
    # 顺序按规则表定义。
    for rule in matched:
        for cuisine in rule.cuisines:
            if cuisine in seen:
                continue
            seen.add(cuisine)
            ordered.append(cuisine)
            if len(ordered) >= MAX_SELECTED_CUISINES:
                return ordered
    return ordered


def _apply_allergy_filter(cuisines: list[str], preferences: UserPreferencesDict) -> list[str]:
    """应用忌口硬冲突表（spec §3.3），并截断到 MAX_SELECTED_CUISINES。"""
    allergies = set(preferences.get("allergies") or [])
    filtered = filter_conflicts(cuisines, allergies)
    return filtered[:MAX_SELECTED_CUISINES]


def _build_rule_reason(matched: list[Rule]) -> str:
    """命中规则的 routing_reason 文案。

    - 单条命中：直接用规则 reason
    - 多条命中：用首条规则的 reason + 截断（F002 §2 ≤30 字）
    """
    if len(matched) == 1:
        return matched[0].reason
    # 多条合并时，仍用首条规则的 reason（spec §3.3 合并示例：「日料，清淡的」
    # 命中 japanese + light，结果文案保持简洁）。
    return matched[0].reason


def _build_ambient_reason(sampled: list[str], n: int) -> str:
    """ambient 路径的 reason：从实际抽到的菜系名拼出。

    用 sampled 而非 weights 排序——reason 必须与 `selected_cuisines` 实际
    返回一致（用户看到 "川菜 + 粤菜" 但拿到 western_fastfood + fujian 会
    困惑）。截断到 2 个名 +「等」字样，超长 → 走 `_clip_reason`。

    全 0 权重 / sampled 为空时退到「帮你挑了 n 家不一样的」。
    """
    if not sampled:
        return f"帮你挑了 {n} 家不一样的"
    head_names = [_CUISINE_SHORT_NAMES.get(c, c) for c in sampled[:2]]
    if len(sampled) > 2:
        return f"帮你挑了 {' + '.join(head_names)} 等"
    return f"帮你挑了 {' + '.join(head_names)}"


def _now_ms() -> int:
    """单调递增的相对毫秒数（用于 routing_log elapsed_ms）。"""
    # datetime.utcnow 微秒精度足够；规则层期望 <100ms，精确到 ms 即可。
    return int(datetime.now(UTC).timestamp() * 1000)


def _log(layer: str, detail: str, elapsed_ms: int) -> RoutingLogEntry:
    return {
        "ts": datetime.now(UTC).isoformat(),
        "layer": layer,
        "detail": detail,
        "elapsed_ms": int(elapsed_ms),
    }


def _finalize(
    cuisines: list[str],
    reason: str,
    preferences: UserPreferencesDict,
    log: list[RoutingLogEntry],
) -> RouterOutput:
    """正常返回路径：拼装 RouterOutput 并 clip reason 到 ≤30 码位。"""
    clipped = _clip_reason(reason)
    out: RouterOutput = {
        "selected_cuisines": cuisines,
        "routing_reason": clipped,
        "routing_log": log,
    }
    _logger.info(
        "router[%s] decided cuisines=%s reason=%r",
        preferences.get("user_id"),
        cuisines,
        clipped,
    )
    return out


def _finalize_all_filtered(log: list[RoutingLogEntry]) -> RouterOutput:
    """ALL_CUISINES_FILTERED 路径：用户文案 reason + 错误码。"""
    log.append(_log("fallback", "all candidates filtered by allergy", 0))
    return {
        "selected_cuisines": [],
        "routing_reason": ALL_FILTERED_USER_COPY,
        "routing_log": log,
        "errors": [
            {
                "code": ALL_CUISINES_FILTERED,
                "message": "候选菜系被忌口全部剔除",
            }
        ],
    }


def _finalize_no_match(
    preferences: UserPreferencesDict, log: list[RoutingLogEntry]
) -> RouterOutput:
    """NO_CUISINE_MATCHED 路径：取 cuisine_weights top-1 作为兜底。

    强制走 `_clip_reason` —— spec §2 写明「routing_reason ≤30 字」是全路径
    不变量；任何动态拼接都要经过裁剪，防止未来新增超长 cuisine_id 时静默越界。
    """
    weights = preferences.get("cuisine_weights") or {}
    top = _top1_weighted(weights)
    log.append(_log("fallback", f"no match → fallback top-1={top}", 0))
    reason = _clip_reason(f"今天为你挑了 {top}")
    out: RouterOutput = {
        "selected_cuisines": [top],
        "routing_reason": reason,
        "routing_log": log,
        "errors": [
            {
                "code": NO_CUISINE_MATCHED,
                "message": "路由策略无输出，已用偏好 top-1 兜底",
            }
        ],
    }
    _logger.info(
        "router[%s] no match → fallback top-1=%s",
        preferences.get("user_id"),
        top,
    )
    return out


def _top1_weighted(weights: dict[str, float]) -> str:
    """取 cuisine_weights top-1，ties 按 CUISINE_IDS 顺序破平（spec §3.3 兜底语义）。

    未知 cuisine_id 直接按权重参与排序、不抛 `ValueError`——F001 schema 验证是
    生产路径唯一来源，未知 key 出现在这里是上游 bug，不应让 router 崩溃。
    """
    if not weights:
        return CUISINE_IDS[0]
    return max(
        weights,
        key=lambda k: (
            float(weights.get(k) or 0.0),
            -_cuisine_index_or_inf(k),
        ),
    )


def _cuisine_index_or_inf(cuisine_id: str) -> float:
    """未知 cuisine_id 返回 +∞，确保它在 ties 时排在已知菜系之后。"""
    try:
        return float(CUISINE_IDS.index(cuisine_id))
    except ValueError:
        return float("inf")


def _clip_reason(reason: str, limit: int = MAX_REASON_CODEPOINTS) -> str:
    """≤limit 码位；超过则保留前 limit-1 码位 + …。

    `limit` 默认绑 spec 常量 `MAX_REASON_CODEPOINTS`（来自 `routing/rules.py`），
    禁止在任何路径上 magic-number 覆盖。
    """
    if len(reason) <= limit:
        return reason
    return reason[: limit - 1] + "…"


async def _route_via_llm(
    state: AgentState,
    message: str,
    preferences: UserPreferencesDict,
    log: list[RoutingLogEntry],
    injected_provider: LLMProvider | None,
) -> RouterOutput:
    """LLM 兜底层：包在 asyncio.wait_for 里；任何错误都降级到 NO_CUISINE_MATCHED。"""
    provider = injected_provider or get_llm_provider()
    request = build_router_prompt(preferences, message)

    llm_started = _now_ms()
    try:
        response = await asyncio.wait_for(
            provider.complete(request), timeout=ROUTER_LLM_TIMEOUT_SECONDS
        )
    except TimeoutError:
        llm_elapsed = _now_ms() - llm_started
        log.append(_log("llm", f"timeout after {llm_elapsed}ms", llm_elapsed))
        _logger.warning("router LLM timeout for user=%s", preferences.get("user_id"))
        return _finalize_no_match(preferences, log)
    except LLMError as e:
        llm_elapsed = _now_ms() - llm_started
        log.append(_log("llm", f"LLMError: {e.message}", llm_elapsed))
        _logger.warning("router LLM error user=%s code=%s", preferences.get("user_id"), e.code)
        return _finalize_no_match(preferences, log)
    except Exception as e:  # 最后兜底：任何异常都不向上抛
        llm_elapsed = _now_ms() - llm_started
        log.append(_log("llm", f"unexpected: {type(e).__name__}: {e}", llm_elapsed))
        _logger.exception("router LLM unexpected error user=%s", preferences.get("user_id"))
        return _finalize_no_match(preferences, log)

    llm_elapsed = _now_ms() - llm_started
    log.append(_log("llm", f"got response in {llm_elapsed}ms", llm_elapsed))

    try:
        parsed = parse_router_response(response.get("content", ""))
    except RouterResponseError as e:
        log.append(_log("llm", f"parse failed: {e}", 0))
        return _finalize_no_match(preferences, log)

    raw_cuisines = parsed["selected_cuisines"]
    valid_cuisines = [c for c in raw_cuisines if c in CUISINE_IDS]
    valid_cuisines = valid_cuisines[:MAX_SELECTED_CUISINES]

    if not valid_cuisines:
        log.append(_log("llm", "no valid cuisine_ids in response", 0))
        return _finalize_no_match(preferences, log)

    valid_cuisines = _apply_allergy_filter(valid_cuisines, preferences)
    if not valid_cuisines:
        return _finalize_all_filtered(log)

    reason = _clip_reason(parsed.get("routing_reason") or "")
    if not reason:
        reason = "今天为你挑了几家"

    return _finalize(
        cuisines=valid_cuisines,
        reason=reason,
        preferences=preferences,
        log=log,
    )


# 仅暴露给 tests 的"私有"助手（保证不破坏模块面）。mypy 看得到、用户用不到。
__all__ = [
    "ALL_CUISINES_FILTERED",
    "EMPTY_MESSAGE",
    "MAX_SELECTED_CUISINES",
    "NO_CUISINE_MATCHED",
    "ROUTER_LLM_TIMEOUT_SECONDS",
    "_apply_allergy_filter",
    "_clip_reason",
    "_finalize_no_match",
    "_is_meaningful",
    "_merge_rule_cuisines",
    "_neutral_preferences",
    "_top1_weighted",
    "route_cuisines",
]
