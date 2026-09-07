"""F040 §3.3 + §4 — 纯函数: 决策矩阵 + 餐厅评分.

这个模块刻意保持**纯函数 + 无副作用**, 让单测可以 table-driven 测试所有边界.
不导入 LLM / langgraph / 数据库 / settings — 这些都在上层 (`summary.py`) 处理.

决策矩阵 (F040 §3.3):
    天气      \ 距离    | ≤500m   | 500-1500m | >1500m |
    晴/多云/阴 (风≤5)  | false   | false     | true   |
    小雨/风 6 级       | true    | true      | true   |
    中大雨/雪/沙尘/雾霾| true    | true      | true   |
    温度 ≥35℃ / ≤-5℃  | true    | true      | true   |

默认距离未知时按 "500-1500m" 中庸档处理.

评分 (F040 §4): 距离(0.4/0.2/0) + 评分(0.3/0.2/0.1/0) + 偏好×0.3.
"""
from __future__ import annotations

from typing import Any, cast

from app.core.constants import NEUTRAL_CUISINE_WEIGHT
from app.mcp.amap.restaurant import Restaurant

# ----- 决策矩阵常量 (F040 §3.3) -----

# 极端温度阈值
_EXTREME_HEAT_C: float = 35.0
_EXTREME_COLD_C: float = -5.0

# 风力阈值 (蒲福风级 ≥6 视为大风)
_STRONG_WIND_LEVEL: int = 6

# 距离边界 (米)
_NEAR_DISTANCE_M: int = 500
_MID_DISTANCE_M: int = 1500

# 恶劣天气条件 (any of → 直接外卖)
_BAD_CONDITIONS: frozenset[str] = frozenset({"rainy", "snowy", "foggy", "dust"})

# ----- 评分常量 (F040 §4) -----

MAX_PREFERENCE_BONUS: float = 0.3   # cuisine_weight × 0.3 上限
DEFAULT_DISTANCE_BUCKET_BONUS: float = 0.4   # ≤500m 加分
MID_DISTANCE_BUCKET_BONUS: float = 0.2      # 500-1500m 加分
DEFAULT_RATING_BONUS: float = 0.3            # ≥4.5 加分


# ---------------------------------------------------------------------------
# 决策矩阵 (F040 §3.3)
# ---------------------------------------------------------------------------


def should_order_takeout(
    *,
    temperature_c: float | None,
    condition: str | None,
    wind_level: int | None,
    distance_m: int | None,
) -> bool:
    """根据天气 + 距离决定 `order_takeout` 标记.

    Args:
        temperature_c: 当前温度 (℃). None 表示未知.
        condition: 天气状况 ("sunny" / "cloudy" / "rainy" / "snowy" /
            "foggy" / "dust" / ...). None 表示未知.
        wind_level: 蒲福风级 (0-12). None 表示未知.
        distance_m: 餐厅距离 (米). None 表示未知.

    Returns:
        True = 建议外卖; False = 可以出门吃.

    Notes:
        阈值严格按 spec §3.3 硬编码; 边界值 (35.0℃ / 500m / 1500m / 风 6 级)
        的归属参考 spec §9 决议 ("M1 用硬阈值, 不做平滑").
    """
    # 1. 极端温度 → 直接外卖 (无视其他条件)
    if temperature_c is not None and (
        temperature_c >= _EXTREME_HEAT_C or temperature_c <= _EXTREME_COLD_C
    ):
        return True

    # 2. 恶劣天气 → 直接外卖
    if condition in _BAD_CONDITIONS:
        return True

    # 3. 大风 → 直接外卖
    if wind_level is not None and wind_level >= _STRONG_WIND_LEVEL:
        return True

    # 4. 良好天气: 距离未知 → 默认中庸档 (≤1500m 视为 false)
    if distance_m is None:
        return False

    # 5. 良好天气: ≤1500m → 步行可达; >1500m → 距离太远, 外卖
    return distance_m > _MID_DISTANCE_M


# ---------------------------------------------------------------------------
# 评分函数 (F040 §4)
# ---------------------------------------------------------------------------


def _distance_bonus(distance_m: int | None) -> float:
    """距离加分: ≤500m → 0.4, 500-1500m → 0.2, >1500m → 0."""
    if distance_m is None:
        return 0.0
    if distance_m <= _NEAR_DISTANCE_M:
        return DEFAULT_DISTANCE_BUCKET_BONUS
    if distance_m <= _MID_DISTANCE_M:
        return MID_DISTANCE_BUCKET_BONUS
    return 0.0


def _rating_bonus(rating: float | None) -> float:
    """评分加分: ≥4.5 → 0.3, ≥4.0 → 0.2, ≥3.5 → 0.1, 否则 0. 缺失也算 0."""
    if rating is None:
        return 0.0
    if rating >= 4.5:
        return DEFAULT_RATING_BONUS
    if rating >= 4.0:
        return 0.2
    if rating >= 3.5:
        return 0.1
    return 0.0


def _preference_bonus(
    cuisine_id: str, cuisine_weights: dict[str, float] | None
) -> float:
    """偏好加分: cuisine_weights[cuisine_id] × 0.3; 缺失 → 中性 0.5 兜底.

    与 F002 router 保持一致 (`NEUTRAL_CUISINE_WEIGHT`) — 避免"新用户被
    永久歧视", 同时 `preferences.cuisine_weights` 永远是 dict 而非 None,
    所以 None 仅作防御.
    """
    weight = NEUTRAL_CUISINE_WEIGHT
    if cuisine_weights is not None:
        raw = cuisine_weights.get(cuisine_id)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            weight = float(raw)
    return weight * MAX_PREFERENCE_BONUS


def score_restaurant(
    *,
    restaurant: Restaurant | dict[str, Any],
    cuisine_output: dict[str, Any],
    preferences: dict[str, Any] | None,
) -> float:
    """F040 §4 — 综合评分 (0.0 - 1.0 量纲). 越大越推荐.

    Args:
        restaurant: 兼容 `Restaurant` TypedDict (`poi_id` / `name` /
            `distance_meters` / `rating` / ...). 字段缺失时按 0 计分.
        cuisine_output: 菜系专家输出 (`CuisineExpertOutput` TypedDict).
        preferences: `UserPreferencesDict`, 只读 `cuisine_weights` 字段.
            传 None 时按完全中性处理.

    Returns:
        评分, 范围 [0.0, 1.0] (实际最高 ≈ 0.4 + 0.3 + 0.3 = 1.0).

    Notes:
        不抛错 — 字段缺失 / 类型错误按 0 计分, 让上层 `SummaryAgent` 永远
        能拿到一个分数 (降级路径兜底).
    """
    distance_m = restaurant.get("distance_meters") if isinstance(restaurant, dict) else None
    if not isinstance(distance_m, (int, float)) or isinstance(distance_m, bool):
        distance_m = None
    else:
        distance_m = int(distance_m)

    rating = restaurant.get("rating") if isinstance(restaurant, dict) else None
    if not isinstance(rating, (int, float)) or isinstance(rating, bool):
        rating = None
    else:
        rating = float(rating)

    cuisine_id = (
        str(cuisine_output.get("cuisine_id", "")) if isinstance(cuisine_output, dict) else ""
    )

    cuisine_weights = (
        preferences.get("cuisine_weights") if isinstance(preferences, dict) else None
    )
    if not isinstance(cuisine_weights, dict):
        cuisine_weights = None
    else:
        cuisine_weights = cast(dict[str, float], cuisine_weights)

    return (
        _distance_bonus(distance_m)
        + _rating_bonus(rating)
        + _preference_bonus(cuisine_id, cuisine_weights)
    )


__all__ = [
    "DEFAULT_DISTANCE_BUCKET_BONUS",
    "DEFAULT_RATING_BONUS",
    "MAX_PREFERENCE_BONUS",
    "score_restaurant",
    "should_order_takeout",
]