"""BaseCuisineExpert — F003 §3.1 抽象类.

Per F003 §2 acceptance: every cuisine expert inherits `BaseCuisineExpert` and
registers into `CUISINE_REGISTRY`. We use `ABC` (not `Protocol`) because the
spec §2 explicitly says "抽象类".

TODO(M2): `matched_allergies` field on `CuisineExpertOutput` is up for review —
see F003 §7. If the field is dropped, remove from `parse_output` and from the
prompt template.

Phase 1 vs Phase 2 evolution:
- Phase 1 stub: subclasses inherit `run()` which raises `NotImplementedError`.
- Phase 2 (F040 完工 + F003 后端端到端, 2026-09-07): `BaseCuisineExpert.run()`
  默认实现真正调 `LLMProvider.complete`, 14 个菜系一律走 base 实现.
  子类 (如需要) 可 override 添加菜系专属 prompt 段落.
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC
from typing import cast

from pydantic import ValidationError

from app.agents.cuisines.prompts.base import render_base_prompt
from app.agents.llm.factory import get_llm_provider
from app.agents.llm.types import ChatRequest, ChatResponse, Message
from app.agents.state import AgentState, CuisineExpertInput, CuisineExpertOutput
from app.core.constants import NEUTRAL_CUISINE_WEIGHT
from app.core.exceptions import LLMError

_logger = logging.getLogger(__name__)


class BaseCuisineExpert(ABC):
    """Abstract base for all 14 cuisine experts."""

    cuisine_id: str        # subclass MUST set
    display_name: str      # subclass MUST set (中文显示名)
    llm_model: str = "MiniMax-M3"  # F003 §8.1 — unified model
    prompt_fragment: str = ""      # 菜系专属 prompt 片段

    # LLM 调用的硬上限 — 整个 graph 不允许被单 cuisine 卡 30 秒
    _LLM_TIMEOUT_SECONDS: float = 10.0

    def build_prompt(self, inp: CuisineExpertInput) -> str:
        """Default: render public template + this cuisine's fragment.

        Subclasses may override to add cuisine-specific shaping.
        """
        return render_base_prompt(self.display_name, self.prompt_fragment, inp)

    def parse_output(self, raw: str) -> CuisineExpertOutput:
        """F003 §3.3 — JSON parse; on failure retry once, then degrade.

        Retry semantics (per spec): the provider layer handles transport-level
        retries (HTTP 5xx, 429, timeout). This method handles the parse-level
        retry exactly once (the `for _ in range(2)` loop). After 2 failed parse
        attempts we return `_fallback_output` rather than raising — the rest
        of the workflow (router + summary agent) is responsible for skipping
        nodes whose `keywords` is empty.
        """
        for _ in range(2):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            try:
                return {
                    "cuisine_id": self.cuisine_id,
                    "conclusion": str(data.get("conclusion", "")),
                    "keywords": [
                        str(k)
                        for k in data.get("keywords", [])
                        if isinstance(k, (str, int))
                    ],
                    "matched_allergies": [
                        str(a)
                        for a in data.get("matched_allergies", [])
                        if isinstance(a, (str, int))
                    ],
                }
            except ValidationError:
                continue
        return _fallback_output(self.cuisine_id)

    async def run(self, state: AgentState) -> dict[str, object]:
        """LangGraph Node entry point.

        默认实现: 从 state 抽 `CuisineExpertInput` → build prompt → 调 LLM →
        parse_output → 返回 dict. 14 个菜系一律走这条路; 子类只在需要追加
        菜系专属 prompt shaping 时 override.

        LLM 失败 / 解析失败 / 超时 → 返回 `_fallback_output` 的 dict (而非抛),
        让 `cuisine_fanout` 把 keywords=[] 当作"该菜系不可推荐"处理 (F040 §7).
        """
        inp = self._extract_input(state)
        prompt = self.build_prompt(inp)
        llm = get_llm_provider()

        try:
            request: ChatRequest = {
                "messages": [
                    cast(Message, {"role": "system", "content": self._system_prompt()}),
                    cast(Message, {"role": "user", "content": prompt}),
                ],
                "temperature": 0.3,
                "max_tokens": 600,
            }
            response: ChatResponse = await asyncio_wait_with_timeout(
                llm.complete(request), timeout=self._LLM_TIMEOUT_SECONDS
            )
            raw = (response.get("content") or "") if isinstance(response, dict) else ""
        except LLMError as exc:
            # F003 §3.3: LLM 失败 → 不抛, 返回 fallback. cuisine_fanout 看到
            # keywords=[] 会跳过该菜系 + 追加 errors entry.
            _logger.warning(
                "cuisine[%s] LLM failed code=%s msg=%s",
                self.cuisine_id, exc.code, exc.message,
            )
            return cast(dict[str, object], _fallback_output_dict(self.cuisine_id))
        except Exception as exc:
            _logger.warning(
                "cuisine[%s] run unexpected error: %s",
                self.cuisine_id, type(exc).__name__,
            )
            return cast(dict[str, object], _fallback_output_dict(self.cuisine_id))

        return cast(dict[str, object], self.parse_output(raw))

    # ----- 内部 helper -----

    def _system_prompt(self) -> str:
        """System prompt — 强调"严格 JSON 输出" + 中文硬约束."""
        return (
            f"你是 {self.display_name} 推荐专家. "
            "请基于用户输入 + 偏好, 输出**严格 JSON** "
            "(无 markdown 围栏, 无多余文字), 不要解释."
        )

    def _extract_input(self, state: AgentState) -> CuisineExpertInput:
        """从 `AgentState` 抽出 `CuisineExpertInput` — 防御缺字段."""
        prefs = state.get("user_preferences") or {
            "user_id": str(state.get("user_id", "")),
            "cuisine_weights": {},
            "allergies": [],
            "spice_tolerance": 0,
            "temperature_preference": "room",
            "default_location": None,
            "budget_lunch_min": None,
            "budget_lunch_max": None,
        }
        # 填 cuisine_weights 缺 key 的中性值 (与 router 一致)
        if isinstance(prefs, dict) and "cuisine_weights" in prefs:
            weights = prefs["cuisine_weights"]
            if isinstance(weights, dict):
                weights.setdefault(self.cuisine_id, NEUTRAL_CUISINE_WEIGHT)

        spice = 0
        if isinstance(prefs, dict):
            raw_spice = prefs.get("spice_tolerance")
            if isinstance(raw_spice, int) and not isinstance(raw_spice, bool):
                spice = raw_spice

        budget_min = _budget_to_float(
            prefs.get("budget_lunch_min") if isinstance(prefs, dict) else None
        )
        budget_max = _budget_to_float(
            prefs.get("budget_lunch_max") if isinstance(prefs, dict) else None
        )

        location = state.get("location_override")
        if not isinstance(location, str) or not location.strip():
            location = prefs.get("default_location") if isinstance(prefs, dict) else None
        if not isinstance(location, str):
            location = None

        return cast(
            CuisineExpertInput,
            {
                "user_message": str(state.get("user_message", "")),
                "user_preferences": prefs,
                "location": location,
                "spice_tolerance": spice,
                "budget_min": budget_min,
                "budget_max": budget_max,
            },
        )


def _budget_to_float(value: object) -> float | None:
    """Decimal / int / float → float; None / 非法 → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    return None


def _fallback_output(cuisine_id: str) -> CuisineExpertOutput:
    """Returned when LLM output cannot be parsed after the single retry."""
    return {
        "cuisine_id": cuisine_id,
        "conclusion": "暂不可推荐",
        "keywords": [],
        "matched_allergies": [],
    }


def _fallback_output_dict(cuisine_id: str) -> dict[str, object]:
    """Dict 版本 for `run()` 直接返回给 LangGraph."""
    return {
        "cuisine_id": cuisine_id,
        "conclusion": "暂不可推荐",
        "keywords": [],
        "matched_allergies": [],
    }


# ---- 异步工具 ----


async def asyncio_wait_with_timeout(coro, *, timeout: float):
    """`asyncio.wait_for` 的薄包装 — 仅用于类型提示更友好."""
    return await asyncio.wait_for(coro, timeout=timeout)