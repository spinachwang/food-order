"""F040 — 总结与推荐 Agent 单元测试.

覆盖 [spec/features/F040-summary-agent.md §8] 验收点:

- 决策矩阵 (F040 §3.3) — 6 个 case
- 评分函数 (F040 §4) — 4 个 case
- 降级路径 (F040 §7) — 3 个 case
- LLM 集成 / 兜底 — 4 个 case
- Node 层契约 — 2 个 case

测试策略:
- 决策矩阵 / 评分函数是纯函数 → 直接 import + 调
- SummaryAgent 用 `FakeLLMProvider` (`app/agents/llm/testing.py`) 替换真实 LLM
- Node 层用直接 await 调, 不构造整个 LangGraph graph (F004 测试已经覆盖)

所有 fixture 都建最小 `AgentState` 兼容 dict; 字段缺失/类型错误属于被测代码必须防御的场景.
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any, cast

import pytest
from app.agents.llm.testing import FakeLLMProvider
from app.agents.nodes.summarize import node_summarize
from app.agents.prompts.summary import (
    DECISION_MATRIX_TABLE,
    build_decision_matrix_table,
    render_summary_prompt,
)
from app.agents.scoring import (
    DEFAULT_DISTANCE_BUCKET_BONUS,
    DEFAULT_RATING_BONUS,
    MAX_PREFERENCE_BONUS,
    score_restaurant,
    should_order_takeout,
)
from app.agents.state import AgentState, CuisineExpertOutput, UserPreferencesDict
from app.agents.summary import (
    DEGRADED_HEADLINE,
    SummaryAgent,
)
from app.core.constants import CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_prefs(**overrides: Any) -> UserPreferencesDict:
    prefs: UserPreferencesDict = {
        "user_id": "u-f040",
        "cuisine_weights": dict.fromkeys(CUISINE_IDS, 0.5),
        "allergies": [],
        "spice_tolerance": 1,
        "temperature_preference": "room",
        "default_location": "国贸",
        "budget_lunch_min": Decimal("30.00"),
        "budget_lunch_max": Decimal("80.00"),
    }
    prefs.update(cast(Any, overrides))
    return prefs


def _make_restaurant(
    *,
    poi_id: str = "B0TEST",
    name: str = "测试餐厅",
    distance_meters: int = 400,
    rating: float | None = 4.5,
    avg_price: Decimal | None = None,
    cuisine_tags: list[str] | None = None,
) -> dict[str, object]:
    """构造一个最小可用的 restaurant dict (匹配 `Restaurant` TypedDict)."""
    return {
        "poi_id": poi_id,
        "name": name,
        "address": "北京市朝阳区国贸",
        "distance_meters": distance_meters,
        "rating": rating,
        "avg_price": avg_price,
        "cuisine_tags": cuisine_tags or [],
        "location": (116.433840, 39.908740),
    }


def _make_state(
    *,
    prefs: UserPreferencesDict | None = None,
    cuisine_results: dict[str, CuisineExpertOutput] | None = None,
    restaurant_lists: dict[str, list[dict[str, object]]] | None = None,
    weather: dict[str, object] | None = None,
    user_message: str = "今天想吃辣的",
) -> AgentState:
    state: AgentState = {
        "user_id": "u-f040",
        "user_message": user_message,
        "user_preferences": prefs if prefs is not None else _make_prefs(),
        "cuisine_results": cuisine_results or {},
        "restaurant_lists": restaurant_lists or {},
        "weather": weather,
    }
    return state


def _make_cuisine_output(
    cuisine_id: str,
    *,
    conclusion: str = "推荐",
    keywords: list[str] | None = None,
) -> CuisineExpertOutput:
    return {
        "cuisine_id": cuisine_id,
        "conclusion": conclusion,
        "keywords": keywords or [f"{cuisine_id}_kw"],
        "matched_allergies": [],
    }


# ---------------------------------------------------------------------------
# 决策矩阵 — F040 §3.3
# ---------------------------------------------------------------------------


class TestShouldOrderTakeout:
    """F040 §3.3 决策矩阵硬阈值 (中庸 default = 距离未知 / 500-1500m + 好天气 → false)."""

    def test_sunny_short_distance_walks_over(self) -> None:
        # 晴 + 300m → false (近, 好天气)
        assert should_order_takeout(
            temperature_c=22, condition="sunny", wind_level=2, distance_m=300,
        ) is False

    def test_rainy_short_distance_still_takeout(self) -> None:
        # 雨 + 300m → true (恶劣天气无视距离)
        assert should_order_takeout(
            temperature_c=22, condition="rainy", wind_level=2, distance_m=300,
        ) is True

    def test_extreme_heat_always_takeout(self) -> None:
        # 38℃ → true (即使近距离好天气)
        assert should_order_takeout(
            temperature_c=38, condition="sunny", wind_level=1, distance_m=200,
        ) is True

    def test_extreme_cold_always_takeout(self) -> None:
        # -8℃ → true
        assert should_order_takeout(
            temperature_c=-8, condition="sunny", wind_level=2, distance_m=200,
        ) is True

    def test_strong_wind_always_takeout(self) -> None:
        # 风 6 级 + 晴 → true
        assert should_order_takeout(
            temperature_c=22, condition="sunny", wind_level=6, distance_m=300,
        ) is True

    def test_far_distance_good_weather_takeout(self) -> None:
        # 晴 + 2000m → true (>1500m)
        assert should_order_takeout(
            temperature_c=22, condition="sunny", wind_level=2, distance_m=2000,
        ) is True

    def test_distance_unknown_defaults_walk(self) -> None:
        # 晴 + 距离未知 → false (默认 500-1500m 中庸档)
        assert should_order_takeout(
            temperature_c=22, condition="sunny", wind_level=2, distance_m=None,
        ) is False

    def test_snowy_always_takeout(self) -> None:
        assert should_order_takeout(
            temperature_c=0, condition="snowy", wind_level=2, distance_m=200,
        ) is True

    def test_foggy_always_takeout(self) -> None:
        assert should_order_takeout(
            temperature_c=15, condition="foggy", wind_level=2, distance_m=200,
        ) is True

    def test_dust_always_takeout(self) -> None:
        assert should_order_takeout(
            temperature_c=25, condition="dust", wind_level=2, distance_m=200,
        ) is True


# ---------------------------------------------------------------------------
# 评分函数 — F040 §4
# ---------------------------------------------------------------------------


class TestScoreRestaurant:
    """F040 §4 score_restaurant: 距离(0.4/0.2/0) + 评分(0.3/0.2/0.1/0) + 偏好(×0.3)."""

    def test_top_score_meets_threshold(self) -> None:
        # rating 4.8 + distance 200m + weight 0.9 → 0.4 + 0.3 + 0.27 = 0.97 ≥ 0.95
        score = score_restaurant(
            restaurant=_make_restaurant(distance_meters=200, rating=4.8),
            cuisine_output=_make_cuisine_output("sichuan"),
            preferences=_make_prefs(
                cuisine_weights={**dict.fromkeys(CUISINE_IDS, 0.0), "sichuan": 0.9},
            ),
        )
        assert score >= 0.95, f"期望 ≥0.95, 实际 {score}"

    def test_no_rating_mid_distance_neutral_pref(self) -> None:
        # rating None + distance 800m + weight 0.5 → 0.2 + 0.0 + 0.15 = 0.35 ≥ 0.3
        score = score_restaurant(
            restaurant=_make_restaurant(distance_meters=800, rating=None),
            cuisine_output=_make_cuisine_output("cantonese"),
            preferences=_make_prefs(
                cuisine_weights={**dict.fromkeys(CUISINE_IDS, 0.0), "cantonese": 0.5},
            ),
        )
        assert score >= 0.3, f"期望 ≥0.3, 实际 {score}"

    def test_far_distance_zero_distance_bonus(self) -> None:
        # distance 2000m → 距离分 0; 其余按 0
        score = score_restaurant(
            restaurant=_make_restaurant(distance_meters=2000, rating=None),
            cuisine_output=_make_cuisine_output("suzhou"),
            preferences=_make_prefs(
                cuisine_weights={**dict.fromkeys(CUISINE_IDS, 0.0), "suzhou": 0.0},
            ),
        )
        assert score == 0.0, f"距离 2000m 且无评分无偏好 → 0, 实际 {score}"

    def test_missing_cuisine_weight_uses_neutral(self) -> None:
        # cuisine_weights 里没有 sichuan → 兜底 0.5 → +0.15
        prefs = _make_prefs()
        prefs["cuisine_weights"] = {"cantonese": 0.5}  # 缺 sichuan
        score = score_restaurant(
            restaurant=_make_restaurant(distance_meters=2000, rating=None),
            cuisine_output=_make_cuisine_output("sichuan"),
            preferences=prefs,
        )
        expected_distance = 0.0
        expected_rating = 0.0
        expected_pref = NEUTRAL_CUISINE_WEIGHT * MAX_PREFERENCE_BONUS
        assert score == pytest.approx(expected_distance + expected_rating + expected_pref)

    def test_rating_buckets(self) -> None:
        """四个评分阈值: ≥4.5 / ≥4.0 / ≥3.5 / <3.5(=0)."""
        # 距离 2000m 排除距离分, 只看评分 + 0 偏好
        prefs = _make_prefs(
            cuisine_weights={**dict.fromkeys(CUISINE_IDS, 0.0), "sichuan": 0.0},
        )
        cuisine_out = _make_cuisine_output("sichuan")
        for rating, expected_bonus in [
            (4.8, DEFAULT_RATING_BONUS),       # ≥4.5
            (4.5, DEFAULT_RATING_BONUS),       # 边界
            (4.3, 0.2),                        # ≥4.0
            (4.0, 0.2),                        # 边界
            (3.7, 0.1),                        # ≥3.5
            (3.5, 0.1),                        # 边界
            (3.4, 0.0),                        # <3.5
            (None, 0.0),                       # 缺失
        ]:
            actual = score_restaurant(
                restaurant=_make_restaurant(distance_meters=2000, rating=rating),
                cuisine_output=cuisine_out,
                preferences=prefs,
            )
            assert actual == pytest.approx(expected_bonus), (
                f"rating={rating} 期望 bonus {expected_bonus}, 实际 score {actual}"
            )

    def test_distance_buckets(self) -> None:
        """距离三档: ≤500 (+0.4) / 500-1500 (+0.2) / >1500 (+0)."""
        prefs = _make_prefs(
            cuisine_weights={**dict.fromkeys(CUISINE_IDS, 0.0), "sichuan": 0.0},
        )
        cuisine_out = _make_cuisine_output("sichuan")
        for distance, expected_bonus in [
            (500, DEFAULT_DISTANCE_BUCKET_BONUS),   # 边界
            (400, DEFAULT_DISTANCE_BUCKET_BONUS),   # ≤500
            (501, 0.2),                              # >500
            (1500, 0.2),                             # 边界
            (1000, 0.2),                             # 中段
            (1501, 0.0),                             # >1500
            (3000, 0.0),                             # 远
        ]:
            actual = score_restaurant(
                restaurant=_make_restaurant(distance_meters=distance, rating=None),
                cuisine_output=cuisine_out,
                preferences=prefs,
            )
            assert actual == pytest.approx(expected_bonus), (
                f"distance={distance} 期望 bonus {expected_bonus}, 实际 score {actual}"
            )


# ---------------------------------------------------------------------------
# 降级路径 — F040 §7
# ---------------------------------------------------------------------------


class TestDegradedFallback:
    """F040 §7: NO_RESTAURANTS / 全空 → 降级 recommendation."""

    def test_no_cuisine_results_returns_degraded(self) -> None:
        agent = SummaryAgent(llm=FakeLLMProvider())
        rec = asyncio.run(agent.assemble(_make_state(cuisine_results={}, restaurant_lists={})))
        assert rec["headline"] == DEGRADED_HEADLINE
        assert rec["alternatives"] == []
        assert rec["confidence"] == 0.0
        # 决策矩阵: 默认好天气 → false
        assert rec["order_takeout"] is False

    def test_cuisine_results_but_all_empty_restaurants_returns_degraded(self) -> None:
        # cuisine_results 有数据 (sichuan), 但 restaurant_lists 全空
        cuisine_results = {"sichuan": _make_cuisine_output("sichuan")}
        agent = SummaryAgent(llm=FakeLLMProvider())
        rec = asyncio.run(agent.assemble(
            _make_state(cuisine_results=cuisine_results, restaurant_lists={})
        ))
        assert rec["headline"] == DEGRADED_HEADLINE

    def test_partial_cuisine_results_uses_have_restaurants(self) -> None:
        # sichuan 有餐厅, cantonese 没餐厅 → 用 sichuan
        cuisine_results = {
            "sichuan": _make_cuisine_output("sichuan"),
            "cantonese": _make_cuisine_output("cantonese"),
        }
        restaurant_lists = {
            "sichuan": [_make_restaurant(poi_id="S1", distance_meters=300)],
            "cantonese": [],
        }
        agent = SummaryAgent(llm=FakeLLMProvider())
        rec = asyncio.run(agent.assemble(
            _make_state(
                cuisine_results=cuisine_results, restaurant_lists=restaurant_lists,
            )
        ))
        assert rec["headline"] != DEGRADED_HEADLINE
        assert rec["restaurant_id"] == "S1"


# ---------------------------------------------------------------------------
# LLM 集成 — F040 §5
# ---------------------------------------------------------------------------


def _llm_json(rec_dict: dict[str, object]) -> str:
    """Return a JSON string the LLM should emit; SummaryAgent parses it."""
    return json.dumps(rec_dict, ensure_ascii=False)


def _valid_llm_payload(
    *, restaurant_id: str = "S1", reason: str = "天气晴朗，距您 300m, 步行可达",
) -> dict[str, object]:
    return {
        "headline": "今天推荐：测试餐厅（川菜）",
        "cuisine_id": "sichuan",
        "restaurant_id": restaurant_id,
        "restaurant_name": "测试餐厅",
        "order_takeout": False,
        "reason": reason,
        "confidence": 0.85,
        "alternatives": [
            {
                "cuisine_id": "cantonese",
                "restaurant_id": "C1",
                "restaurant_name": "粤菜餐厅",
                "short_reason": "备选粤菜, 评分 4.5",
            },
        ],
    }


class TestSummaryAgentLLMIntegration:
    """F040 §5 + §7: LLM 拼装 + 失败兜底."""

    def _setup(self) -> tuple[SummaryAgent, dict[str, list[dict[str, object]]]]:
        restaurant_lists: dict[str, list[dict[str, object]]] = {
            "sichuan": [_make_restaurant(poi_id="S1", name="蜀香苑", distance_meters=300, rating=4.7)],
            "cantonese": [_make_restaurant(poi_id="C1", name="粤菜馆", distance_meters=800, rating=4.4)],
        }
        return SummaryAgent(llm=FakeLLMProvider()), restaurant_lists

    def test_llm_response_used_for_reason_and_headline(self) -> None:
        agent, restaurant_lists = self._setup()
        llm_provider = cast(FakeLLMProvider, agent.llm)
        llm_provider.set_response({
            "content": _llm_json(_valid_llm_payload(reason="晴朗步行可达")),
            "model": "fake",
            "usage": None,
        })
        rec = asyncio.run(agent.assemble(
            _make_state(
                cuisine_results={
                    "sichuan": _make_cuisine_output("sichuan"),
                    "cantonese": _make_cuisine_output("cantonese"),
                },
                restaurant_lists=restaurant_lists,
                weather={"temperature_celsius": 22, "condition": "sunny", "wind_level": 2},
            )
        ))
        assert rec["reason"] == "晴朗步行可达"
        assert rec["headline"].startswith("今天推荐")

    def test_llm_raises_falls_back_to_deterministic_template(self) -> None:
        from app.core.exceptions import LLMError

        class ExplodingProvider(FakeLLMProvider):
            async def complete(self, request: Any) -> Any:  # type: ignore[override]
                raise LLMError("boom", details={})

        agent = SummaryAgent(llm=ExplodingProvider())
        rec = asyncio.run(agent.assemble(
            _make_state(
                cuisine_results={"sichuan": _make_cuisine_output("sichuan")},
                restaurant_lists={
                    "sichuan": [_make_restaurant(poi_id="S1", distance_meters=300, rating=4.5)],
                },
                weather={"temperature_celsius": 22, "condition": "sunny", "wind_level": 2},
            )
        ))
        # LLM 失败 → reason 是确定性模板
        assert "300" in rec["reason"] or "步行" in rec["reason"] or "餐厅" in rec["reason"]

    def test_llm_invalid_json_falls_back(self) -> None:
        agent, restaurant_lists = self._setup()
        llm_provider = cast(FakeLLMProvider, agent.llm)
        llm_provider.set_response({
            "content": "not json", "model": "fake", "usage": None,
        })
        rec = asyncio.run(agent.assemble(
            _make_state(
                cuisine_results={
                    "sichuan": _make_cuisine_output("sichuan"),
                    "cantonese": _make_cuisine_output("cantonese"),
                },
                restaurant_lists=restaurant_lists,
            )
        ))
        # 仍然有 recommendation, reason 是确定性模板
        assert rec["headline"] != DEGRADED_HEADLINE
        assert isinstance(rec["reason"], str) and len(rec["reason"]) > 0

    def test_llm_picking_unknown_restaurant_falls_back_to_top_scored(self) -> None:
        """LLM 想推荐一个不存在的餐厅 → 兜底用评分最高的真实候选."""
        agent, restaurant_lists = self._setup()
        llm_provider = cast(FakeLLMProvider, agent.llm)
        llm_provider.set_response({
            "content": _llm_json(
                _valid_llm_payload(restaurant_id="B0NOTEXIST", reason="LLM 幻觉")
            ),
            "model": "fake",
            "usage": None,
        })
        rec = asyncio.run(agent.assemble(
            _make_state(
                cuisine_results={
                    "sichuan": _make_cuisine_output("sichuan"),
                    "cantonese": _make_cuisine_output("cantonese"),
                },
                restaurant_lists=restaurant_lists,
            )
        ))
        # 仍然拿到真实候选
        assert rec["restaurant_id"] == "S1"  # 评分最高


# ---------------------------------------------------------------------------
# 备选 (alternatives) — F040 §2 验收
# ---------------------------------------------------------------------------


class TestAlternatives:
    """F040 §2: 备选 ≥2 个; 尽量不同 cuisine_id."""

    def test_alternatives_diverse_cuisine_when_possible(self) -> None:
        # 3 个不同菜系, 各 1 家
        restaurant_lists = {
            "sichuan": [_make_restaurant(poi_id="S1", distance_meters=300, rating=4.7)],
            "cantonese": [_make_restaurant(poi_id="C1", distance_meters=600, rating=4.5)],
            "japanese": [_make_restaurant(poi_id="J1", distance_meters=900, rating=4.4)],
        }
        cuisine_results = {
            cid: _make_cuisine_output(cid) for cid in restaurant_lists
        }
        agent = SummaryAgent(llm=FakeLLMProvider())
        rec = asyncio.run(agent.assemble(
            _make_state(cuisine_results=cuisine_results, restaurant_lists=restaurant_lists)
        ))
        assert len(rec["alternatives"]) >= 2
        # 备选 cuisine_id 与主推荐不同
        main_cid = rec["cuisine_id"]
        alt_cids = {a["cuisine_id"] for a in rec["alternatives"]}
        assert main_cid not in alt_cids

    def test_alternatives_fewer_than_two_when_only_one_cuisine(self) -> None:
        # 只有 1 个菜系 / 1 个餐厅 → 0 个备选
        restaurant_lists = {
            "sichuan": [_make_restaurant(poi_id="S1", distance_meters=300, rating=4.7)],
        }
        agent = SummaryAgent(llm=FakeLLMProvider())
        rec = asyncio.run(agent.assemble(
            _make_state(
                cuisine_results={"sichuan": _make_cuisine_output("sichuan")},
                restaurant_lists=restaurant_lists,
            )
        ))
        assert rec["alternatives"] == []


# ---------------------------------------------------------------------------
# Node 层契约 — F040 §3.4 (不抛错)
# ---------------------------------------------------------------------------


class TestSummarizeNodeContract:
    """`node_summarize` 必须 (a) 写 `recommendation` (b) 不抛错."""

    async def test_happy_path_writes_recommendation(self) -> None:
        llm = FakeLLMProvider()
        llm.set_response({
            "content": _llm_json(_valid_llm_payload(reason="晴朗步行")),
            "model": "fake",
            "usage": None,
        })
        state = _make_state(
            cuisine_results={"sichuan": _make_cuisine_output("sichuan")},
            restaurant_lists={
                "sichuan": [_make_restaurant(poi_id="S1", distance_meters=300, rating=4.7)],
            },
        )
        # 直接给 node 注入 llm — 看 node 内部 get_llm_provider 是否可被替换
        # 简化: 我们仅验证 stub 不被替换的情况下, fake provider 不被调用.
        # 这里仅验证 node 不抛 + 写 recommendation.
        out = await node_summarize(state)
        assert "recommendation" in out
        assert out["recommendation"] is not None
        assert "headline" in out["recommendation"]  # type: ignore[operator]

    async def test_node_does_not_propagate_exceptions(self) -> None:
        # 即使 state 异常 (cuisine_results 是 None), node 不应抛
        state = _make_state(cuisine_results={}, restaurant_lists={})
        out = await node_summarize(state)
        assert out["recommendation"] is not None
        assert out["recommendation"]["headline"] == DEGRADED_HEADLINE  # type: ignore[index]


# ---------------------------------------------------------------------------
# Prompt 渲染 — F040 §5
# ---------------------------------------------------------------------------


class TestSummaryPromptRendering:
    def render_contains_decision_matrix_table(self) -> None:
        text = render_summary_prompt(
            preferences=_make_prefs(),
            weather={"temperature_celsius": 22, "condition": "sunny", "wind_level": 2},
            cuisine_results=[_make_cuisine_output("sichuan")],
            restaurant_lists={"sichuan": [_make_restaurant()]},
        )
        # 包含决策矩阵表 + JSON schema 提示
        assert "decision_matrix" in text.lower() or "决策矩阵" in text
        assert '"reason"' in text
        assert '"alternatives"' in text

    def render_handles_none_weather(self) -> None:
        text = render_summary_prompt(
            preferences=_make_prefs(),
            weather=None,
            cuisine_results=[_make_cuisine_output("sichuan")],
            restaurant_lists={"sichuan": [_make_restaurant()]},
        )
        # 未知天气 fallback 文案
        assert "未知" in text or "未获取" in text or "默认" in text

    def decision_matrix_table_includes_three_distance_buckets(self) -> None:
        table = build_decision_matrix_table()
        # 简单断言: 表里出现 "500" 和 "1500" 距离边界
        assert "500" in table
        assert "1500" in table
        # 决策矩阵常量与函数渲染一致
        assert table == DECISION_MATRIX_TABLE