"""BaseCuisineExpert — F003 §3.1 抽象类.

Per F003 §2 acceptance: every cuisine expert inherits `BaseCuisineExpert` and
registers into `CUISINE_REGISTRY`. We use `ABC` (not `Protocol`) because the
spec §2 explicitly says "抽象类".

TODO(M2): `matched_allergies` field on `CuisineExpertOutput` is up for review —
see F003 §7. If the field is dropped, remove from `parse_output` and from the
prompt template.
"""
from __future__ import annotations

import json
from abc import ABC

from pydantic import ValidationError

from app.agents.cuisines.prompts.base import render_base_prompt
from app.agents.state import AgentState, CuisineExpertInput, CuisineExpertOutput


class BaseCuisineExpert(ABC):
    """Abstract base for all 14 cuisine experts."""

    cuisine_id: str        # subclass MUST set
    display_name: str      # subclass MUST set (中文显示名)
    llm_model: str = "MiniMax-M3"  # F003 §8.1 — unified model
    prompt_fragment: str = ""      # 菜系专属 prompt 片段

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

        Not abstract — Phase 1 stubs inherit this default `NotImplementedError`
        and Phase 4 (F004 / F040) will override it with the real node body.
        """
        raise NotImplementedError


def _fallback_output(cuisine_id: str) -> CuisineExpertOutput:
    """Returned when LLM output cannot be parsed after the single retry."""
    return {
        "cuisine_id": cuisine_id,
        "conclusion": "暂不可推荐",
        "keywords": [],
        "matched_allergies": [],
    }
