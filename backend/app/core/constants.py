"""Shared domain constants — single source of truth across schemas / agents / services.

Per project SDD: keep validation enums here so that:
- `schemas/preferences.py` validates cuisine_weights keys, allergy values,
  spice tolerance and temperature preference against these constants.
- `agents/cuisines/registry.py` builds the 14-expert registry from `CUISINE_IDS`.
- `agents/cuisines/enums.py` re-exports for backward compatibility with F003 §3.2.

Avoids the schemas → agents reverse dependency noted in the M1 Phase 1 plan.
"""
from __future__ import annotations

# F003 §3.2 — 14 cuisine identifiers, order matters for stable UI ordering.
CUISINE_IDS: tuple[str, ...] = (
    "sichuan",
    "cantonese",
    "shandong",
    "suzhou",
    "zhejiang",
    "fujian",
    "hunan",
    "anhui",
    "japanese",
    "western",
    "western_fastfood",
    "chinese_fastfood",
    "snacks",
    "dessert_drinks",
)

# F001 §3.1 — 11 allergy values.
ALLERGY_VALUES: frozenset[str] = frozenset(
    {
        "peanut",       # 花生
        "tree_nut",     # 坚果（杏仁 / 腰果等）
        "shellfish",    # 虾蟹贝
        "fish",
        "egg",
        "soy",
        "wheat",        # 含麸质
        "dairy",
        "sesame",
        "alcohol",
        "fried_food",   # 油炸
    }
)

# F001 §3.2 — spice tolerance range (inclusive).
SPICE_TOLERANCE_RANGE: tuple[int, int] = (0, 3)

# F001 §3.4 — temperature preference values.
TEMPERATURE_VALUES: frozenset[str] = frozenset({"cold", "room", "hot"})

# F003 §8.1 — unified LLM model across all 14 cuisine experts.
DEFAULT_LLM_MODEL: str = "MiniMax-M3"
