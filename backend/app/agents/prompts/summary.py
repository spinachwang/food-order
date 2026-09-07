"""F040 §5 — 总结 Agent 的 LLM prompt 模板.

模板照搬 spec §5. 函数签名只关心"输入什么 + 输出什么" — 业务细节交给上层
`SummaryAgent` 在调用前准备好. 模板里嵌一段决策矩阵表 (`DECISION_MATRIX_TABLE`)
保持 spec 一致, 同时暴露 `build_decision_matrix_table()` 让测试可以单独验证表格.

不做 Pydantic / TypedDict — 上层已经把入参校验完了, 渲染层只负责拼字符串.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 决策矩阵表 (F040 §3.3, 用于嵌入 prompt 提示 LLM 引用)
# ---------------------------------------------------------------------------

DECISION_MATRIX_TABLE: str = """\
| 天气        | 距离 ≤500m | 距离 500-1500m | 距离 >1500m |
|-------------|-----------|----------------|-------------|
| 晴/多云/阴 (风≤5) | false     | false          | true        |
| 小雨/风 6 级     | true      | true           | true        |
| 中大雨/雪/沙尘/雾霾 | true      | true           | true        |
| 温度 ≥35℃ / ≤-5℃  | true      | true           | true        |"""


def build_decision_matrix_table() -> str:
    """Render the decision matrix table for embedding in the LLM prompt.

    Returns the same string as `DECISION_MATRIX_TABLE` so callers can treat
    it as either a constant or a function (e.g. if a future change wants
    i18n, this becomes the natural seam).
    """
    return DECISION_MATRIX_TABLE


# ---------------------------------------------------------------------------
# Prompt 模板 (F040 §5)
# ---------------------------------------------------------------------------

_TEMPLATE: str = """你是"午餐决策助手"的总结 Agent。基于上游所有信息给出最终推荐。

【用户偏好】
{preferences_summary}

【天气】
{weather_summary}

【菜系专家结论】
{cuisine_results_summary}

【餐厅候选】
{restaurant_summary}

【决策矩阵】
{DECISION_MATRIX_TABLE}

【任务】
1. 选出 score 最高的 1 家作为主推荐
2. 给出 ≥2 个备选（不同菜系优先）
3. 输出 `reason`：≤50 字，引用天气 / 距离 / 偏好 / 评分
4. 决定 `order_takeout`：基于决策矩阵

【输出格式】严格 JSON，不要多余文字：
{{
  "headline": "...",
  "cuisine_id": "...",
  "restaurant_id": "...",
  "restaurant_name": "...",
  "order_takeout": true|false,
  "reason": "...",
  "confidence": 0.85,
  "alternatives": [
    {{"cuisine_id": "...", "restaurant_id": "...", "restaurant_name": "...", "short_reason": "..."}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# 渲染函数
# ---------------------------------------------------------------------------


def _preferences_summary(prefs: dict[str, Any] | None) -> str:
    """Format preferences as a short multi-line block."""
    if not isinstance(prefs, dict):
        return "（未指定偏好）"
    allergies = prefs.get("allergies") or []
    allergy_str = ", ".join(str(a) for a in allergies) if allergies else "无"
    weights = prefs.get("cuisine_weights") or {}
    top = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_str = ", ".join(f"{k}={v}" for k, v in top) if top else "无"
    return (
        f"- 忌口：{allergy_str}\n"
        f"- 偏好最高的 3 个菜系：{top_str}"
    )


def _weather_summary(weather: dict[str, Any] | None) -> str:
    """Format weather (or fallback text when None / partial)."""
    if not isinstance(weather, dict) or not weather:
        return "（未获取天气，按默认 \"未知天气\" 走决策矩阵中庸档）"
    temp = weather.get("temperature_celsius")
    cond = weather.get("condition")
    wind = weather.get("wind_level")
    if temp is None or cond is None or wind is None:
        return "（天气信息不全，按未知处理）"
    return f"- 温度：{temp}℃\n- 天气：{cond}\n- 风力：{wind} 级"


def _cuisine_results_summary(
    cuisine_results: list[dict[str, Any]],
) -> str:
    """Format cuisine expert conclusions as a bullet list."""
    if not cuisine_results:
        return "（无菜系结论）"
    lines: list[str] = []
    for c in cuisine_results:
        cid = str(c.get("cuisine_id", ""))
        conc = str(c.get("conclusion", "")).strip()
        if not conc:
            conc = "（无结论）"
        lines.append(f"- [{cid}] {conc}")
    return "\n".join(lines)


def _restaurant_summary(
    restaurant_lists: dict[str, list[dict[str, Any]]],
    per_cuisine_limit: int = 3,
) -> str:
    """Format top-N restaurants per cuisine as a bullet list.

    Top-N 由上层已经按 `score_restaurant` 排好序 — 渲染层不再排序, 只裁剪.
    """
    if not restaurant_lists:
        return "（无餐厅候选）"
    lines: list[str] = []
    for cid, rests in restaurant_lists.items():
        for r in rests[:per_cuisine_limit]:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name", ""))
            distance = r.get("distance_meters")
            rating = r.get("rating")
            poi_id = str(r.get("poi_id", ""))
            lines.append(
                f"- [{cid}] {name} (poi={poi_id}, "
                f"距离={distance}m, 评分={rating})"
            )
    return "\n".join(lines) if lines else "（无餐厅候选）"


def render_summary_prompt(
    *,
    preferences: dict[str, Any] | None,
    weather: dict[str, Any] | None,
    cuisine_results: list[dict[str, Any]],
    restaurant_lists: dict[str, list[dict[str, Any]]],
) -> str:
    """Render the F040 §5 prompt template into a single user-role string.

    Returned string is intended to be wrapped into a `Message(role="user")`
    by the caller (`SummaryAgent`). 系统 prompt 由 `Message(role="system")`
    单独提供, 不在本函数内合并 — 调用方拥有最终拼装权.
    """
    return _TEMPLATE.format(
        preferences_summary=_preferences_summary(preferences),
        weather_summary=_weather_summary(weather),
        cuisine_results_summary=_cuisine_results_summary(cuisine_results),
        restaurant_summary=_restaurant_summary(restaurant_lists),
        DECISION_MATRIX_TABLE=build_decision_matrix_table(),
    )


__all__ = [
    "DECISION_MATRIX_TABLE",
    "build_decision_matrix_table",
    "render_summary_prompt",
]