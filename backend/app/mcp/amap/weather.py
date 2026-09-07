"""F031 — 高德 MCP 天气查询 Tool.

设计要点 (per spec/features/F031-amap-weather.md):

- 输入: location (`lng,lat` 经纬度串或 adcode 或可解析地标名) + extensions (base/all)
- 输出: 当前实况 + 未来 3 小时逐小时预报 (base 模式无预报 → 用实况外推)
- 错误: 通过 `AmapClient` 抛 `AmapError` 子类
- 边缘: `lives=[]` / infocode=20001 → 抛 `AmapLocationInvalidError`, 调用方兜底

不使用 LangChain `@tool` 装饰器 (项目不依赖 LangChain Tools) — 函数
签名遵循 LangChain Tool 风格: typed params + 单个 typed return, 由
LangGraph Node (F040 summary agent) 直接 await 调用.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from typing_extensions import TypedDict

from app.mcp.amap.client import AmapClient

logger = logging.getLogger(__name__)

# ---- 业务常量 (从 spec 派生) ----

# 高德天气 API 路径
_WEATHER_PATH = "/v3/weather/weatherInfo"

# 高德中文天气 → 枚举 condition (F031 §3.2)
# 优先级: 雪 > 雨 > 霾 > 雾 > 沙 > 多云 > 晴
_CONDITION_KEYWORDS: tuple[tuple[str, WeatherCondition], ...] = (  # type: ignore[name-defined]
    ("雪", "snowy"),
    ("雨", "rainy"),
    ("霾", "dust"),
    ("雾", "foggy"),
    ("沙", "dust"),
    ("多云", "cloudy"),
    ("阴", "cloudy"),
    ("晴", "sunny"),
)


# ----- 类型契约 (F031 §3) -----


WeatherCondition = Literal["sunny", "cloudy", "rainy", "snowy", "foggy", "dust"]


class HourlyForecast(TypedDict):
    """未来 3 小时逐小时预报 (F031 §3.2)."""

    hour: int  # 0-23
    temperature_celsius: float
    condition: WeatherCondition
    precipitation_probability: float


class WeatherInfo(TypedDict):
    """F031 §3.2 输出 envelope.

    `extensions=base` 时 `forecast_3h` 由当前实况外推 (AMAP 不返回逐小时)。
    `extensions=all` 时 `forecast_3h` 由预报中的白昼天气外推 (小时级别近似)。
    """

    location: str
    province: str
    city: str
    adcode: str
    temperature_celsius: float
    condition: WeatherCondition
    humidity_percent: int
    wind_direction: str
    wind_level: int
    precipitation_probability: float  # 当前
    forecast_3h: list[HourlyForecast]
    fetched_at: datetime


# ----- 内部辅助 dataclass -----


@dataclass(frozen=True)
class _LiveRaw:
    """高德 base 模式原始字段."""

    province: str
    city: str
    adcode: str
    weather: str
    temperature_celsius: float
    wind_direction: str
    wind_level: int
    humidity_percent: int
    report_time: str


@dataclass(frozen=True)
class _CastRaw:
    """高德 all 模式单日预报字段."""

    day_weather: str
    night_weather: str
    day_temp: int
    night_temp: int
    day_wind: str
    night_wind: str
    day_power: int
    night_power: int


@dataclass(frozen=True)
class _ForecastRaw:
    """高德 all 模式 forecasts[0] 顶层字段."""

    province: str
    city: str
    adcode: str
    report_time: str
    casts: list[_CastRaw]


# ----- 主入口 -----


async def amap_get_weather(
    *,
    location: str,
    extensions: Literal["base", "all"] = "base",
    client: AmapClient | None = None,
) -> WeatherInfo:
    """F031 主入口 —— 调用高德天气查询 API.

    Args:
        location: 锚点 (优先 `lng,lat`, 其次 adcode, 再次地标名).
                  F031 §3.1: 地标无效 → 抛 `AmapLocationInvalidError`,
                  调用方（summary agent）用 IP 城市兜底。
        extensions: `"base"` 返回实况 (默认); `"all"` 返回未来预报.
        client: 已构造的 `AmapClient`. 不传则用工厂 (推荐用于生产,
                测试时可注入带 monkeypatched key 的实例).

    Returns:
        `WeatherInfo`: 当前实况 + 未来 3 小时逐小时预报.

    Raises:
        ValueError: location 为空 / extensions 非法
        AmapInvalidKeyError: API key 无效或未配置
        AmapQuotaExceededError: 高德配额耗尽
        AmapNetworkError: 网络/超时重试耗尽
        AmapLocationInvalidError: location 无法解析 (infocode=20001)
    """
    # ---- 入参校验 ----
    _validate_location(location)
    _validate_extensions(extensions)

    # ---- HTTP 调用 ----
    if client is None:
        from app.mcp.amap.client import get_amap_client

        client = get_amap_client()

    payload = await client.get_json(
        _WEATHER_PATH,
        params={
            "city": location,
            "extensions": extensions,
        },
    )

    # ---- 解析 ----
    if extensions == "base":
        live_raw = _parse_lives(payload)
        if live_raw is None:
            # F031 §5: location 无法解析 → AmapLocationInvalidError
            from app.core.exceptions import AmapLocationInvalidError

            raise AmapLocationInvalidError(
                "高德 MCP 天气返回空 lives (location 无法解析)",
                details={"location": location, "payload_keys": list(payload.keys())},
            )
        return _project_live(live_raw, location)
    else:
        # extensions=all → AMAP 返回 forecasts[].casts[] (3 天预报)
        # 没有 lives 字段; 当前实况用白昼天气近似
        forecast_raw = _parse_forecast(payload)
        if forecast_raw is None:
            from app.core.exceptions import AmapLocationInvalidError

            raise AmapLocationInvalidError(
                "高德 MCP 天气返回空 forecasts (location 无法解析)",
                details={"location": location, "payload_keys": list(payload.keys())},
            )
        return _project_forecast(forecast_raw, location)


# ----- 入参校验 -----


def _validate_location(location: str) -> None:
    if not isinstance(location, str) or not location.strip():
        raise ValueError("location 必须是非空字符串")


def _validate_extensions(extensions: str) -> None:
    if extensions not in ("base", "all"):
        raise ValueError(f"extensions 必须是 'base' 或 'all', 实际={extensions!r}")


# ----- 解析 helpers -----


def _parse_lives(payload: dict[str, Any]) -> _LiveRaw | None:
    """从高德 base/all 响应抽出 lives[0]. 缺关键字段返回 None."""
    lives = payload.get("lives")
    if not isinstance(lives, list) or not lives:
        return None
    first = lives[0]
    if not isinstance(first, dict):
        return None

    province = str(first.get("province", ""))
    city = str(first.get("city", ""))
    adcode = str(first.get("adcode", ""))
    weather = str(first.get("weather", ""))
    temperature = _to_float(first.get("temperature_float"))
    if temperature is None:
        temperature = _to_float(first.get("temperature"))
    wind_direction = str(first.get("winddirection", ""))
    wind_level = _to_int(first.get("windpower"), default=0)
    humidity = _to_int(first.get("humidity"), default=0)
    report_time = str(first.get("reporttime", ""))

    if not province or not city or temperature is None:
        return None

    return _LiveRaw(
        province=province,
        city=city,
        adcode=adcode,
        weather=weather,
        temperature_celsius=temperature,
        wind_direction=wind_direction,
        wind_level=wind_level,
        humidity_percent=humidity,
        report_time=report_time,
    )


def _parse_forecast(payload: dict[str, Any]) -> _ForecastRaw | None:
    """从高德 all 响应抽出 forecasts[0] + 全部 casts."""
    forecasts = payload.get("forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        return None
    first = forecasts[0]
    if not isinstance(first, dict):
        return None
    casts_raw = first.get("casts")
    if not isinstance(casts_raw, list):
        return None
    casts: list[_CastRaw] = []
    for cast in casts_raw:
        if not isinstance(cast, dict):
            continue
        casts.append(
            _CastRaw(
                day_weather=str(cast.get("dayweather", "")),
                night_weather=str(cast.get("nightweather", "")),
                day_temp=_to_int(cast.get("daytemp"), default=0),
                night_temp=_to_int(cast.get("nighttemp"), default=0),
                day_wind=str(cast.get("daywind", "")),
                night_wind=str(cast.get("nightwind", "")),
                day_power=_to_int(cast.get("daypower"), default=0),
                night_power=_to_int(cast.get("nightpower"), default=0),
            )
        )
    if not casts:
        return None
    return _ForecastRaw(
        province=str(first.get("province", "")),
        city=str(first.get("city", "")),
        adcode=str(first.get("adcode", "")),
        report_time=str(first.get("reporttime", "")),
        casts=casts,
    )


def _map_condition(weather_text: str) -> WeatherCondition:
    """把高德中文天气描述映射到 6 个枚举值.

    优先级: 雪 > 雨 > 霾 > 雾 > 沙 > 多云/阴 > 晴
    (例如 "小雨转阴" 优先匹配 "雨" → rainy)
    """
    for keyword, mapped in _CONDITION_KEYWORDS:
        if keyword in weather_text:
            return mapped
    # 未知 — 默认晴 (高德失败时业务可降级)
    return "sunny"


# ----- 投影 helpers -----


def _project_live(raw: _LiveRaw, location: str) -> WeatherInfo:
    """extensions=base 时, forecast_3h 由当前实况外推 (3 小时逐小时)."""
    condition = _map_condition(raw.weather)
    pop = _estimate_pop(condition)

    forecast_3h = _extrapolate_3h(
        condition=condition,
        current_temperature=raw.temperature_celsius,
    )

    fetched_at = _parse_report_time(raw.report_time)

    return {
        "location": location,
        "province": raw.province,
        "city": raw.city,
        "adcode": raw.adcode,
        "temperature_celsius": raw.temperature_celsius,
        "condition": condition,
        "humidity_percent": raw.humidity_percent,
        "wind_direction": raw.wind_direction,
        "wind_level": raw.wind_level,
        "precipitation_probability": pop,
        "forecast_3h": forecast_3h,
        "fetched_at": fetched_at,
    }


def _project_forecast(forecast_raw: _ForecastRaw, location: str) -> WeatherInfo:
    """extensions=all 时的投影.

    AMAP 在 all 模式下不返回 `lives`, 只有 forecasts[].casts[].
    当前实况用今天白昼天气 (casts[0].dayweather + daytemp) 近似。
    """
    first_cast = forecast_raw.casts[0]
    condition = _map_condition(first_cast.day_weather)
    pop = _estimate_pop(condition)

    forecast_3h = _extrapolate_3h(
        condition=condition,
        current_temperature=float(first_cast.day_temp),
    )

    fetched_at = _parse_report_time(forecast_raw.report_time)

    return {
        "location": location,
        "province": forecast_raw.province,
        "city": forecast_raw.city,
        "adcode": forecast_raw.adcode,
        "temperature_celsius": float(first_cast.day_temp),
        "condition": condition,
        # all 模式不返回当前湿度/风力 — 用 None 表示不可用 (下游用 0 兜底)
        "humidity_percent": 0,
        "wind_direction": first_cast.day_wind,
        "wind_level": first_cast.day_power,
        "precipitation_probability": pop,
        "forecast_3h": forecast_3h,
        "fetched_at": fetched_at,
    }


def _extrapolate_3h(
    *,
    condition: WeatherCondition,
    current_temperature: float,
) -> list[HourlyForecast]:
    """从当前条件外推未来 3 小时逐小时预报.

    AMAP 天气 API 不直接提供逐小时预报 (只有白昼 / 夜间两段),
    故按当前实况 + 渐变温度近似。温度按 ±1°C 渐变 (中午最高 / 夜间最低);
    condition 与 pop 用当前值 (短时天气通常变化不大)。
    """
    now = datetime.now(tz=UTC)
    base_hour = now.hour
    forecast: list[HourlyForecast] = []
    for offset in range(1, 4):
        hour = (base_hour + offset) % 24
        # 简化: 后续小时温度按 offset * 0.5°C 微调 (实际应由历史均值, 这里近似)
        temp_delta = 0.5 * offset if hour > base_hour else -0.5 * offset
        forecast.append(
            {
                "hour": hour,
                "temperature_celsius": current_temperature + temp_delta,
                "condition": condition,
                "precipitation_probability": _estimate_pop(condition),
            }
        )
    return forecast


def _estimate_pop(condition: WeatherCondition) -> float:
    """按 condition 估算降水概率 (0.0 - 1.0). AMAP 不直接返回 pop."""
    return {
        "sunny": 0.05,
        "cloudy": 0.20,
        "rainy": 0.85,
        "snowy": 0.90,
        "foggy": 0.10,
        "dust": 0.05,
    }.get(condition, 0.10)


def _parse_report_time(report_time: str) -> datetime:
    """`"2026-09-07 14:30:00"` → `datetime(2026, 9, 7, 14, 30, 0)`.

    解析失败时用当前 UTC 时间兜底 (数据本身仍然可用)。
    """
    if not report_time:
        return datetime.now(tz=UTC)
    try:
        return datetime.strptime(report_time, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        logger.warning("Amap weather report_time 解析失败: %r", report_time)
        return datetime.now(tz=UTC)


# ----- 类型转换 helpers -----


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _to_int(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        # 处理 "<=3" 这种风力范围字符串 → 取较小值
        # 这里只取数字部分 (更精细解析留给上层)
        try:
            return int(float(value))
        except (TypeError, ValueError):
            # 尝试提取数字
            digits = "".join(ch for ch in value if ch.isdigit() or ch == "-")
            if digits.strip() and digits.strip() != "-":
                try:
                    return int(float(digits))
                except (TypeError, ValueError):
                    return default
            return default
    if isinstance(value, float):
        return int(value)
    return default


__all__ = [
    "HourlyForecast",
    "WeatherCondition",
    "WeatherInfo",
    "amap_get_weather",
]