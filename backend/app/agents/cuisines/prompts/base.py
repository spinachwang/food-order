"""Public prompt template — F003 §4 + §8.2 hard constraint (中文 only).

`render_base_prompt` is the shared rendering function used by every cuisine
expert's default `build_prompt`. It composes:

    {header + user message + preferences block + task + JSON schema + 硬约束 + cuisine fragment}

Subclasses can override `build_prompt` entirely if they need different shaping
(e.g. add a "忌口映射" section that uses known allergy→cuisine conflicts).
"""
from __future__ import annotations

from decimal import Decimal

from app.agents.state import CuisineExpertInput

_TEMPLATE = """你是一位 {cuisine_display_name} 推荐专家。

【用户输入】
{message}

【用户偏好】
- 不吃 / 忌口：{allergies_str}
- 辣度承受：{spice_tolerance_str}
- 预算：{budget_str}
- 默认位置：{location_str}

【你的任务】
1. 输出一句话结论（≤30 字）：今天是否适合推荐 {cuisine_display_name}，若有代表性菜品则点名
2. 输出 3-5 个高德搜索关键词（含菜系词 + 代表性菜名 + 风味词）

【输出格式】严格 JSON，不要多余文字：
{{
  "conclusion": "...",
  "keywords": ["...", "...", "..."],
  "matched_allergies": ["..."]
}}

【硬约束】所有 keywords 必须使用中文，禁止英文（F003 §8.2）。

【该菜系要点】（由各菜系 spec 自填）
{cuisine_extras}
"""


def render_base_prompt(
    cuisine_display_name: str,
    cuisine_extras: str,
    inp: CuisineExpertInput,
) -> str:
    """Render the standard F003 §4 prompt for a given cuisine + input."""
    prefs = inp["user_preferences"]
    return _TEMPLATE.format(
        cuisine_display_name=cuisine_display_name,
        message=inp["user_message"],
        allergies_str=_join_allergies(prefs.get("allergies")),
        spice_tolerance_str=_spice_label(int(prefs.get("spice_tolerance", 0))),
        budget_str=_budget_label(
            prefs.get("budget_lunch_min"), prefs.get("budget_lunch_max")
        ),
        location_str=prefs.get("default_location") or "未指定",
        cuisine_extras=(cuisine_extras or "").strip() or "（无）",
    )


def _join_allergies(allergies: list[str] | None) -> str:
    return ", ".join(allergies) if allergies else "无"


def _spice_label(v: int) -> str:
    return {0: "不吃辣", 1: "微辣", 2: "中辣", 3: "重辣"}.get(v, f"未知({v})")


def _budget_label(
    lo: Decimal | float | int | None, hi: Decimal | float | int | None
) -> str:
    lo_s = _money(lo)
    hi_s = _money(hi)
    if lo_s is None and hi_s is None:
        return "不限"
    if lo_s is None:
        return f"{hi_s} 元以下"
    if hi_s is None:
        return f"{lo_s} 元以上"
    return f"{lo_s}-{hi_s} 元"


def _money(v: Decimal | float | int | None) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return format(v, "f")
    return f"{float(v):g}"
