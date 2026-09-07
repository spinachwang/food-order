"""F040 — `SummaryAgent` 编排层.

职责:
1. 检查降级条件 (F040 §7) — `cuisine_results` 空 / `restaurant_lists` 全空
2. 评分 + 排序 (F040 §4) — 取每菜系 top N, 按 `score_restaurant` 排分
3. 决策矩阵 (F040 §3.3) — `should_order_takeout`
4. LLM 拼装 (F040 §5) — 渲染 prompt → 调 provider → 解析回包
6. 兜底 (F040 §7) — LLM 失败 / 解析失败 → 确定性 reason

不直接和 LangGraph 交互 — 它只是普通的 Python 类, `nodes/summarize.py`
负责把它包成 LangGraph Node. 这样单测可以绕开 graph, 直接喂 state.

返回值是 `dict[str, object]` 而不是 TypedDict — 保持和现有 cuisine expert
输出口径一致 (`parse_output` / `_FALLBACK_RECOMMENDATION` 都是 dict),
让 SSE 层 + 测试都可以 duck-type 处理.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast

from app.agents.llm.base import LLMProvider
from app.agents.llm.types import ChatRequest, ChatResponse, Message
from app.agents.prompts.summary import render_summary_prompt
from app.agents.scoring import score_restaurant, should_order_takeout
from app.agents.state import AgentState, UserPreferencesDict
from app.core.request_id import get_request_id

_logger = logging.getLogger(__name__)

# ----- 降级文案 (F040 §7 NO_RESTAURANTS) -----

DEGRADED_HEADLINE: str = "今天没合适推荐，换个口味吧"

# 系统提示词 — 短, 强调"严格 JSON 输出"
_SYSTEM_PROMPT: str = (
    "你是午餐决策助手的总结 Agent. "
    "请基于用户给出的偏好 / 天气 / 餐厅候选 / 决策矩阵, "
    "输出**严格 JSON** (无 markdown 围栏, 无多余文字), 不要解释."
)

# LLM 调用的硬上限 — Summary Agent 不允许把整个 graph 卡 60 秒
_DEFAULT_LLM_TIMEOUT: float = 8.0

# 每菜系参与排序的候选数 — 避免 14×10=140 个候选全过 score
_PER_CUISINE_LIMIT: int = 5

# 备选上限 — spec §2 要求 ≥2, 这里硬限 2 避免 LLM 给一堆冗余
_MAX_ALTERNATIVES: int = 2


# ---------------------------------------------------------------------------
# 推荐结果 — 内部 dataclass, 输出 dict[str, object]
# ---------------------------------------------------------------------------


class _ScoredRestaurant:
    """中间态: (cuisine_id, restaurant, score). 不暴露给上层."""

    __slots__ = ("cuisine_id", "restaurant", "score")

    def __init__(
        self,
        cuisine_id: str,
        restaurant: dict[str, Any],
        score: float,
    ) -> None:
        self.cuisine_id = cuisine_id
        self.restaurant = restaurant
        self.score = score


# ---------------------------------------------------------------------------
# SummaryAgent
# ---------------------------------------------------------------------------


class SummaryAgent:
    """编排器: state → Recommendation dict.

    注入 `llm` 是为方便单测 (用 `FakeLLMProvider`); 生产由
    `nodes/summarize.py` 调 `get_llm_provider()` 后注入.
    """

    def __init__(
        self,
        *,
        llm: LLMProvider,
        model: str = "MiniMax-M3",
        timeout_seconds: float = _DEFAULT_LLM_TIMEOUT,
    ) -> None:
        self.llm = llm
        self.model = model
        self.timeout_seconds = timeout_seconds

    # ----- 公开入口 -----

    async def assemble(self, state: AgentState) -> dict[str, object]:
        """异步组装: 评分 → 决策矩阵 → 调 LLM → 合并.

        Returns:
            `dict[str, object]` — 直接可作为 LangGraph state 字段 `recommendation`
            写入 (`Recommendation` 兼容).

        为什么是 async: LLM provider (`MiniMaxProvider`) 内部 cache 的
        `httpx.AsyncClient` 绑定到 LangGraph 主 event loop. 之前 sync 实现
        用 `asyncio.run()` 在 worker thread 里跑, 触发了
        `RuntimeError: <AsyncClient> is bound to a different event loop`.
        现在直接在主 loop 上 `await`, 客户端复用同一个 loop.
        """
        cuisine_results = state.get("cuisine_results") or {}
        restaurant_lists = state.get("restaurant_lists") or {}
        weather = state.get("weather")
        preferences = state.get("user_preferences")

        # 1. 降级检查
        scored = self._rank_restaurants(cuisine_results, restaurant_lists, preferences)
        if not scored:
            return self._degraded_recommendation(weather)

        # 2. 主推荐 + 备选
        main = scored[0]
        alternatives = self._pick_alternatives(scored, main.cuisine_id)

        # 3. 决策矩阵
        order_takeout = self._decide_takeout(weather, main.restaurant)

        # 4. 拼装 base dict
        base: dict[str, object] = {
            "cuisine_id": main.cuisine_id,
            "restaurant_id": str(main.restaurant.get("poi_id", "")),
            "restaurant_name": str(main.restaurant.get("name", "")),
            "order_takeout": order_takeout,
            "alternatives": [
                {
                    "cuisine_id": a.cuisine_id,
                    "restaurant_id": str(a.restaurant.get("poi_id", "")),
                    "restaurant_name": str(a.restaurant.get("name", "")),
                    "short_reason": "",
                }
                for a in alternatives
            ],
        }

        # 5. 调 LLM 生成 reason / headline / confidence
        llm_payload = await self._call_llm(
            cuisine_results=cuisine_results,
            restaurant_lists=restaurant_lists,
            preferences=preferences,
            weather=weather,
            main=main,
            alternatives=alternatives,
            order_takeout=order_takeout,
        )

        # 6. 合并 LLM 输出 / 确定性兜底
        merged = self._merge_llm_output(base, llm_payload, main, alternatives, order_takeout)
        return merged

    # ----- 评分 / 排序 -----

    def _rank_restaurants(
        self,
        cuisine_results: dict[str, Any],
        restaurant_lists: dict[str, list[dict[str, Any]]],
        preferences: UserPreferencesDict | dict[str, Any] | None,
    ) -> list[_ScoredRestaurant]:
        """对所有 (cuisine, restaurant) 打分, 按 score 降序.

        - 每菜系取前 `_PER_CUISINE_LIMIT` 家 (避免极多候选拖慢排序)
        - 评分用 `score_restaurant` (F040 §4)
        - 返回值永远是 list (空 list 表示降级)
        """
        scored: list[_ScoredRestaurant] = []
        for cid, rests in restaurant_lists.items():
            if not isinstance(rests, list):
                continue
            cuisine_output = cuisine_results.get(cid) or {"cuisine_id": cid}
            for r in rests[:_PER_CUISINE_LIMIT]:
                if not isinstance(r, dict):
                    continue
                score = score_restaurant(
                    restaurant=cast(dict[str, Any], r),
                    cuisine_output=cuisine_output,
                    preferences=cast(Preferences, preferences),
                )
                scored.append(_ScoredRestaurant(cid, r, score))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored

    def _pick_alternatives(
        self,
        scored: list[_ScoredRestaurant],
        main_cuisine_id: str,
    ) -> list[_ScoredRestaurant]:
        """备选挑选: 尽量不同 cuisine_id, 上限 `_MAX_ALTERNATIVES`.

        - 不同 cuisine 优先 (F040 §2: "备选 cuisine_id 与主推荐不同")
        - 候选不足时少给
        """
        picked: list[_ScoredRestaurant] = []
        seen_cuis: set[str] = {main_cuisine_id}
        # 第一遍: 不同 cuisine
        for s in scored[1:]:
            if s.cuisine_id in seen_cuis:
                continue
            picked.append(s)
            seen_cuis.add(s.cuisine_id)
            if len(picked) >= _MAX_ALTERNATIVES:
                break
        return picked

    # ----- 决策矩阵 -----

    def _decide_takeout(
        self,
        weather: dict[str, Any] | None,
        main_restaurant: dict[str, Any],
    ) -> bool:
        """调 `should_order_takeout` 决策外卖.

        weather 缺失或字段不全 → 当作"未知天气"走中庸档 (false).
        """
        if not isinstance(weather, dict):
            return should_order_takeout(
                temperature_c=None, condition=None, wind_level=None,
                distance_m=self._distance_of(main_restaurant),
            )
        temp = weather.get("temperature_celsius")
        if not isinstance(temp, (int, float)) or isinstance(temp, bool):
            temp = None
        cond = weather.get("condition")
        if not isinstance(cond, str):
            cond = None
        wind = weather.get("wind_level")
        if not isinstance(wind, (int, float)) or isinstance(wind, bool):
            wind = None
        return should_order_takeout(
            temperature_c=cast(float | None, temp),
            condition=cond,
            wind_level=cast(int | None, wind),
            distance_m=self._distance_of(main_restaurant),
        )

    @staticmethod
    def _distance_of(restaurant: dict[str, Any]) -> int | None:
        d = restaurant.get("distance_meters")
        if isinstance(d, bool):
            return None
        if isinstance(d, (int, float)):
            return int(d)
        return None

    # ----- 降级输出 -----

    def _degraded_recommendation(
        self, weather: dict[str, Any] | None
    ) -> dict[str, object]:
        """F040 §7 NO_RESTAURANTS: 全 0 候选 → 降级文案."""
        return {
            "headline": DEGRADED_HEADLINE,
            "cuisine_id": "",
            "restaurant_id": "",
            "restaurant_name": "",
            "order_takeout": self._decide_takeout(weather, {}),
            "reason": "暂无合适餐厅推荐",
            "confidence": 0.0,
            "alternatives": [],
        }

    # ----- LLM 调用 -----

    async def _call_llm(
        self,
        *,
        cuisine_results: dict[str, Any],
        restaurant_lists: dict[str, list[dict[str, Any]]],
        preferences: Any,
        weather: Any,
        main: _ScoredRestaurant,
        alternatives: list[_ScoredRestaurant],
        order_takeout: bool,
    ) -> dict[str, Any] | None:
        """异步调 LLM, 失败/解析失败均返回 None.

        这里我们**故意不抛** — `_merge_llm_output` 会用确定性模板兜底.
        """
        try:
            user_text = render_summary_prompt(
                preferences=cast(dict[str, Any] | None, preferences),
                weather=cast(dict[str, Any] | None, weather),
                cuisine_results=list(cuisine_results.values()),
                restaurant_lists=restaurant_lists,
            )
        except Exception as exc:
            _logger.warning("summary prompt render failed: %s", exc)
            return None

        try:
            request_obj: ChatRequest = {
                "messages": [
                    cast(Message, {"role": "system", "content": _SYSTEM_PROMPT}),
                    cast(Message, {"role": "user", "content": user_text}),
                ],
                "temperature": 0.2,
                "max_tokens": 600,
            }
            response: ChatResponse = await asyncio.wait_for(
                self.llm.complete(request_obj), timeout=self.timeout_seconds
            )
        except Exception as exc:
            rid = get_request_id() or "-"
            _logger.warning(
                "summary LLM call failed rid=%s exc=%s",
                rid,
                type(exc).__name__,
            )
            return None

        raw = (response.get("content") or "") if isinstance(response, dict) else ""
        return self._parse_llm_response(raw)

    @staticmethod
    def _parse_llm_response(raw: str) -> dict[str, Any] | None:
        """解析 LLM 文本 → dict. 失败 / 非 dict → None."""
        if not raw or not raw.strip():
            return None
        # 兼容 LLM 偶尔包 markdown ```json ... ```
        text = raw.strip()
        if text.startswith("```"):
            # 去掉围栏
            text = text.strip("`")
            # 去掉可能的语言标记
            if "\n" in text:
                text = text.split("\n", 1)[1]
            text = text.rstrip("`").strip()
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return cast(dict[str, Any], data)

    # ----- 合并 -----

    def _merge_llm_output(
        self,
        base: dict[str, object],
        llm_payload: dict[str, Any] | None,
        main: _ScoredRestaurant,
        alternatives: list[_ScoredRestaurant],
        order_takeout: bool,
    ) -> dict[str, object]:
        """LLM 成功 → 用 LLM 输出; 失败 → 用确定性模板.

        永远保证 `headline` / `reason` / `confidence` / `alternatives` 字段齐全.
        决策矩阵 (`order_takeout`, `cuisine_id`, `restaurant_id`,
        `restaurant_name`) 永远用 `base` 里的硬逻辑 — LLM 不可覆盖.
        """
        merged: dict[str, object] = dict(base)

        # headline / reason / confidence 来自 LLM 或确定性兜底
        if llm_payload:
            headline = str(llm_payload.get("headline") or "").strip()
            reason = str(llm_payload.get("reason") or "").strip()
            confidence = llm_payload.get("confidence")
            alt_data = llm_payload.get("alternatives")
            if headline:
                merged["headline"] = headline[:80]
            if reason:
                merged["reason"] = reason[:120]
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                merged["confidence"] = float(max(0.0, min(1.0, confidence)))
            if isinstance(alt_data, list):
                # 用 LLM 给的 short_reason 填充 base 备选的文案; 但 base 的
                # `alternatives` 数量是硬指标 (F040 §2: ≥2) — LLM 的
                # `alternatives` 数量**不**覆盖 base 数量, 否则 LLM 给得少
                # 就把备选砍没了. 仅按 base 顺序匹配 short_reason.
                new_alts: list[dict[str, object]] = []
                for i, a in enumerate(alternatives):
                    short = ""
                    if i < len(alt_data) and isinstance(alt_data[i], dict):
                        short = str(alt_data[i].get("short_reason") or "").strip()
                    new_alts.append({
                        "cuisine_id": a.cuisine_id,
                        "restaurant_id": str(a.restaurant.get("poi_id", "")),
                        "restaurant_name": str(a.restaurant.get("name", "")),
                        "short_reason": short[:60],
                    })
                if new_alts:
                    merged["alternatives"] = new_alts

        # 兜底字段 (LLM 失败 / 缺字段时填默认值)
        if not merged.get("headline"):
            merged["headline"] = _deterministic_headline(main)
        if not merged.get("reason"):
            merged["reason"] = _deterministic_reason(main, order_takeout)
        if "confidence" not in merged or not isinstance(merged["confidence"], (int, float)):
            merged["confidence"] = _confidence_from_score(main.score)

        # 备选 short_reason 兜底
        alts_out = merged.get("alternatives") or []
        if isinstance(alts_out, list):
            for a in alts_out:
                if isinstance(a, dict) and not a.get("short_reason"):
                    a["short_reason"] = _deterministic_alt_reason(a)

        # 决策矩阵覆盖 LLM 的 order_takeout (F040 §3.3 硬阈值, 不让 LLM 推翻)
        merged["order_takeout"] = order_takeout

        # restaurant_id 兜底 — 如果 LLM 给的 id 不在候选里, 用评分最高的真实 id
        # (测试 TestSummaryAgentLLMIntegration.test_llm_picking_unknown_restaurant)
        if not merged.get("restaurant_id") or not _poi_id_exists(
            str(merged.get("restaurant_id")), [main, *alternatives]
        ):
            merged["restaurant_id"] = str(main.restaurant.get("poi_id", ""))
            merged["cuisine_id"] = main.cuisine_id
            merged["restaurant_name"] = str(main.restaurant.get("name", ""))

        return merged


# ---------------------------------------------------------------------------
# 确定性兜底 helper
# ---------------------------------------------------------------------------


def _deterministic_headline(main: _ScoredRestaurant) -> str:
    name = str(main.restaurant.get("name", "未知餐厅"))
    cid = main.cuisine_id or "未知菜系"
    return f"今天推荐：{name}（{cid}）"


def _deterministic_reason(main: _ScoredRestaurant, order_takeout: bool) -> str:
    """LLM 失败时用确定性模板拼 reason — ≤50 字."""
    parts: list[str] = []
    distance = main.restaurant.get("distance_meters")
    if isinstance(distance, (int, float)) and not isinstance(distance, bool):
        parts.append(f"距您 {int(distance)}m")
    rating = main.restaurant.get("rating")
    if isinstance(rating, (int, float)) and not isinstance(rating, bool):
        parts.append(f"评分 {rating:.1f}")
    if order_takeout:
        parts.append("建议外卖")
    else:
        parts.append("适合堂食")
    return ", ".join(parts) if parts else "推荐该餐厅"


def _deterministic_alt_reason(alt: dict[str, object]) -> str:
    cid = alt.get("cuisine_id") or "备选"
    return f"备选 {cid}"


def _confidence_from_score(score: float) -> float:
    if score >= 1.0:
        return 0.85
    if score >= 0.7:
        return 0.65
    return 0.45


def _poi_id_exists(
    poi_id: str, candidates: list[_ScoredRestaurant]
) -> bool:
    return any(str(r.restaurant.get("poi_id", "")) == poi_id for r in candidates)


__all__ = [
    "DEGRADED_HEADLINE",
    "SummaryAgent",
]


# 类型别名 (避免 mypy 在 cast 时抱怨)
Preferences = dict[str, Any]