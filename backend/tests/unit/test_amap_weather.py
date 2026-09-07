"""F031 — 高德天气查询单测.

覆盖 [spec/features/F031-amap-weather.md §2 / §6] 验收点:

- mock 晴天返回 → `condition="sunny"`、`pop=0.05`
- mock 雨天返回 → `condition="rainy"`、`pop=0.85`
- mock 雪天 / 多云 / 雾 / 霾 → 各类 condition 映射正确
- mock 预报返回 (`extensions=all`) → `forecast_3h` 含 3 项
- mock 无效 location → 抛 `AmapLocationInvalidError`
- mock 401 / 10001 → `AmapInvalidKeyError`
- mock 10044 → `AmapQuotaExceededError`
- mock 网络超时 → 重试 1 次后抛 `AmapNetworkError`
- 入参校验: location 为空 → ValueError

不重复 F030 已经覆盖的内容 (AmapClient 构造 / 工厂 / 重试协议)。
本文件只断言 **F031 天气查询 Tool** 的契约本身。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx
from app.core.exceptions import (
    AmapInvalidKeyError,
    AmapLocationInvalidError,
    AmapNetworkError,
    AmapQuotaExceededError,
)
from app.mcp.amap.client import AmapClient
from app.mcp.amap.weather import amap_get_weather

# ---------------------------------------------------------------------------
# Fixture loader — 复用 backend/tests/fixtures/amap_weather_responses.json
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
_FIXTURE_PATH = _FIXTURES_DIR / "amap_weather_responses.json"


def _load_fixture(name: str) -> dict[str, object]:
    """从 fixture JSON 读出指定 key 的负载。"""
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    payload = data[name]
    assert isinstance(payload, dict)
    return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AMAP_BASE_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


def _make_client(**overrides: object) -> AmapClient:
    """构造一个测试用 AmapClient；timeout 默认 0.5s 加速失败。"""
    defaults: dict[str, object] = {
        "api_key": "test-amap-key",
        "timeout_seconds": 0.5,
        "max_retries": 1,
        "base_url": "https://restapi.amap.com",
    }
    defaults.update(overrides)
    return AmapClient(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestAmapGetWeatherHappyPath — 各天气状况的 condition 映射
# ---------------------------------------------------------------------------


class TestAmapGetWeatherHappyPath:
    @respx.mock
    @pytest.mark.asyncio
    async def test_sunny_returns_condition_sunny_and_low_pop(self) -> None:
        # F031 §2: 晴天 condition=sunny, pop≈0.05
        payload = _load_fixture("sunny_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert result["condition"] == "sunny"
        assert result["temperature_celsius"] == pytest.approx(23.0)
        assert result["humidity_percent"] == 38
        assert result["wind_level"] == 3
        assert result["wind_direction"] == "西南"
        assert result["precipitation_probability"] == pytest.approx(0.05)
        assert result["province"] == "北京"
        assert result["city"] == "北京市"
        assert result["adcode"] == "110000"
        assert result["location"] == "110000"

    @respx.mock
    @pytest.mark.asyncio
    async def test_rainy_returns_condition_rainy_and_high_pop(self) -> None:
        # F031 §2: 雨天 condition=rainy, pop≈0.85
        payload = _load_fixture("rainy_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="310000",
            client=_make_client(),
        )

        assert result["condition"] == "rainy"
        assert result["temperature_celsius"] == pytest.approx(18.5)
        assert result["humidity_percent"] == 92
        assert result["precipitation_probability"] == pytest.approx(0.85)

    @respx.mock
    @pytest.mark.asyncio
    async def test_snowy_returns_condition_snowy(self) -> None:
        # F031 §3.2: 雪 → snowy
        payload = _load_fixture("snowy_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="230100",
            client=_make_client(),
        )

        assert result["condition"] == "snowy"
        assert result["temperature_celsius"] == pytest.approx(-5.0)
        assert result["humidity_percent"] == 78

    @respx.mock
    @pytest.mark.asyncio
    async def test_cloudy_returns_condition_cloudy(self) -> None:
        payload = _load_fixture("cloudy_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="440300",
            client=_make_client(),
        )

        assert result["condition"] == "cloudy"
        assert result["precipitation_probability"] == pytest.approx(0.20)

    @respx.mock
    @pytest.mark.asyncio
    async def test_foggy_returns_condition_foggy(self) -> None:
        # F031 §3.2: 雾 → foggy
        payload = _load_fixture("foggy_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="320100",
            client=_make_client(),
        )

        assert result["condition"] == "foggy"
        assert result["humidity_percent"] == 96

    @respx.mock
    @pytest.mark.asyncio
    async def test_dust_returns_condition_dust(self) -> None:
        # F031 §3.2: 霾 → dust
        payload = _load_fixture("dust_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert result["condition"] == "dust"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetched_at_is_datetime(self) -> None:
        # F031 §3.2: fetched_at 必须是 datetime
        payload = _load_fixture("sunny_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert isinstance(result["fetched_at"], datetime)


# ---------------------------------------------------------------------------
# TestAmapGetWeatherQueryParams — 验证发出的 query string
# ---------------------------------------------------------------------------


class TestAmapGetWeatherQueryParams:
    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_expected_query_params_base(self) -> None:
        payload = _load_fixture("sunny_base")
        route = respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        await amap_get_weather(
            location="110000",
            extensions="base",
            client=_make_client(),
        )

        request = route.calls.last.request
        params = dict(request.url.params)
        assert params["key"] == "test-amap-key"
        assert params["city"] == "110000"
        assert params["extensions"] == "base"
        assert params["output"] == "JSON"

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_expected_query_params_all(self) -> None:
        # extensions=all → 预报模式 (F031 §3)
        payload = _load_fixture("forecast_all")
        route = respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        await amap_get_weather(
            location="110000",
            extensions="all",
            client=_make_client(),
        )

        request = route.calls.last.request
        params = dict(request.url.params)
        assert params["extensions"] == "all"


# ---------------------------------------------------------------------------
# TestAmapGetWeatherForecast — 预报字段解析
# ---------------------------------------------------------------------------


class TestAmapGetWeatherForecast:
    @respx.mock
    @pytest.mark.asyncio
    async def test_extensions_all_returns_forecast_3h_with_three_hours(self) -> None:
        # F031 §3.2: forecast_3h 是未来 3 小时逐小时预报
        payload = _load_fixture("forecast_all")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            extensions="all",
            client=_make_client(),
        )

        forecast = result["forecast_3h"]
        assert isinstance(forecast, list)
        assert len(forecast) == 3
        # 每项必须含 hour / temperature_celsius / condition / pop
        for entry in forecast:
            assert "hour" in entry
            assert "temperature_celsius" in entry
            assert "condition" in entry
            assert "precipitation_probability" in entry
            assert isinstance(entry["hour"], int)
            assert 0 <= entry["hour"] <= 23
            assert isinstance(entry["condition"], str)
            assert isinstance(entry["temperature_celsius"], (int, float))


# ---------------------------------------------------------------------------
# TestAmapGetWeatherEdgeCases — 空 lives / 缺字段
# ---------------------------------------------------------------------------


class TestAmapGetWeatherEdgeCases:
    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_lives_returns_location_invalid(self) -> None:
        # F031 §5: 地标无法解析 → AmapLocationInvalidError
        payload = _load_fixture("empty_lives")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        with pytest.raises(AmapLocationInvalidError):
            await amap_get_weather(
                location="某个不存在的地标",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_temperature_float_falls_back_to_int_string(self) -> None:
        # 某些老版高德没有 temperature_float, 只有 temperature 字符串
        payload = {
            "status": "1",
            "count": "1",
            "info": "OK",
            "infocode": "10000",
            "lives": [
                {
                    "province": "北京",
                    "city": "北京市",
                    "adcode": "110000",
                    "weather": "晴",
                    "temperature": "23",  # 只有整数字符串
                    "winddirection": "西南",
                    "windpower": "3",
                    "humidity": "38",
                    "reporttime": "2026-09-07 14:30:00",
                }
            ],
        }
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert result["temperature_celsius"] == pytest.approx(23.0)

    @respx.mock
    @pytest.mark.asyncio
    async def test_extensions_all_with_empty_forecasts_returns_location_invalid(self) -> None:
        # extensions=all 模式返回空 forecasts → 抛 AmapLocationInvalidError
        empty_payload = {
            "status": "1",
            "count": "0",
            "info": "OK",
            "infocode": "10000",
            "forecasts": [],
        }
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=empty_payload))

        with pytest.raises(AmapLocationInvalidError):
            await amap_get_weather(
                location="某个不存在的adcode",
                extensions="all",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_extensions_all_missing_forecasts_field_returns_location_invalid(self) -> None:
        # extensions=all 模式但响应中没有 forecasts 字段 → 抛 AmapLocationInvalidError
        bad_payload = {
            "status": "1",
            "count": "0",
            "info": "OK",
            "infocode": "10000",
        }
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=bad_payload))

        with pytest.raises(AmapLocationInvalidError):
            await amap_get_weather(
                location="某个不存在的adcode",
                extensions="all",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_unknown_weather_text_falls_back_to_sunny(self) -> None:
        # 未知天气文字 → 默认 sunny (F031 §5 降级策略)
        payload = {
            "status": "1",
            "count": "1",
            "info": "OK",
            "infocode": "10000",
            "lives": [
                {
                    "province": "北京",
                    "city": "北京市",
                    "adcode": "110000",
                    "weather": "未知天气",  # 未在映射表中
                    "temperature": "23",
                    "winddirection": "西南",
                    "windpower": "3",
                    "humidity": "38",
                    "reporttime": "2026-09-07 14:30:00",
                }
            ],
        }
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert result["condition"] == "sunny"

    @respx.mock
    @pytest.mark.asyncio
    async def test_partial_keyword_matching_in_weather_text(self) -> None:
        # F031: 高德可能返回 "小雨转阴" 复合描述 → 优先级匹配 (雨 > 阴)
        payload = {
            "status": "1",
            "count": "1",
            "info": "OK",
            "infocode": "10000",
            "lives": [
                {
                    "province": "北京",
                    "city": "北京市",
                    "adcode": "110000",
                    "weather": "小雨转阴",
                    "temperature": "18",
                    "winddirection": "东",
                    "windpower": "3",
                    "humidity": "85",
                    "reporttime": "2026-09-07 14:30:00",
                }
            ],
        }
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert result["condition"] == "rainy"

    @respx.mock
    @pytest.mark.asyncio
    async def test_malformed_report_time_falls_back_to_now(self) -> None:
        # reporttime 解析失败 → 用当前时间兜底, 但其他字段仍正确返回
        payload = {
            "status": "1",
            "count": "1",
            "info": "OK",
            "infocode": "10000",
            "lives": [
                {
                    "province": "北京",
                    "city": "北京市",
                    "adcode": "110000",
                    "weather": "晴",
                    "temperature": "23",
                    "winddirection": "西南",
                    "windpower": "3",
                    "humidity": "38",
                    "reporttime": "malformed-time",  # 解析失败
                }
            ],
        }
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert isinstance(result["fetched_at"], datetime)
        # 其他字段不受影响
        assert result["temperature_celsius"] == pytest.approx(23.0)

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_numeric_windpower_extracts_digits(self) -> None:
        # windpower 可能返回 "<=3" / "3-4" 等范围字符串, 应提取数字部分
        payload = {
            "status": "1",
            "count": "1",
            "info": "OK",
            "infocode": "10000",
            "lives": [
                {
                    "province": "北京",
                    "city": "北京市",
                    "adcode": "110000",
                    "weather": "晴",
                    "temperature": "23",
                    "winddirection": "西南",
                    "windpower": "≤3",  # 中文 unicode 范围符号
                    "humidity": "38",
                    "reporttime": "2026-09-07 14:30:00",
                }
            ],
        }
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            client=_make_client(),
        )

        assert result["wind_level"] == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_extensions_all_returns_correct_forecast_3h(self) -> None:
        # extensions=all 时 forecast_3h 用今天白昼天气 (晴)
        payload = _load_fixture("forecast_all")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_get_weather(
            location="110000",
            extensions="all",
            client=_make_client(),
        )

        # today cast[0] 是 晴 → sunny
        assert result["condition"] == "sunny"
        assert result["temperature_celsius"] == pytest.approx(28.0)
        # city / province / adcode 来自 forecasts[0]
        assert result["province"] == "北京"
        assert result["city"] == "北京市"
        assert result["adcode"] == "110000"


# ---------------------------------------------------------------------------
# TestAmapGetWeatherErrorMapping — 错误码透传 (F031 §5)
# ---------------------------------------------------------------------------


class TestAmapGetWeatherErrorMapping:
    @respx.mock
    @pytest.mark.asyncio
    async def test_401_raises_amap_invalid_key(self) -> None:
        # F031 §5: AMAP_INVALID_KEY — HTTP 401
        respx.get(_AMAP_BASE_URL).mock(
            return_value=httpx.Response(401, json={"status": "0", "info": "INVALID_USER_KEY"})
        )

        with pytest.raises(AmapInvalidKeyError):
            await amap_get_weather(
                location="110000",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_body_infocode_10001_raises_amap_invalid_key(self) -> None:
        # F031 §5: AMAP_INVALID_KEY — body infocode=10001
        payload = _load_fixture("invalid_key")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        with pytest.raises(AmapInvalidKeyError):
            await amap_get_weather(
                location="110000",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_body_infocode_10044_raises_amap_quota(self) -> None:
        # F031 §5: AMAP_QUOTA_EXCEEDED
        payload = _load_fixture("quota_exceeded")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        with pytest.raises(AmapQuotaExceededError):
            await amap_get_weather(
                location="110000",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_body_infocode_20001_raises_location_invalid(self) -> None:
        # F031 §5: AMAP_LOCATION_INVALID — body infocode=20001 (城市/区域编码不存在)
        payload = _load_fixture("location_invalid")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        with pytest.raises(AmapLocationInvalidError):
            await amap_get_weather(
                location="不存在的adcode",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_http_429_raises_amap_quota(self) -> None:
        # F031 §5: HTTP 429 也映射到 AMAP_QUOTA_EXCEEDED
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(429, json={"error": "rate"}))
        with pytest.raises(AmapQuotaExceededError):
            await amap_get_weather(
                location="110000",
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_network_timeout_retries_then_raises_amap_network_error(self) -> None:
        # F031 §5: AMAP_NETWORK_ERROR — 重试 1 次后抛错
        from unittest.mock import AsyncMock, patch

        respx.get(_AMAP_BASE_URL).mock(side_effect=httpx.ReadTimeout("timeout"))

        with (
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
            pytest.raises(AmapNetworkError),
        ):
            await amap_get_weather(
                location="110000",
                client=_make_client(max_retries=1),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_timeout_succeeds_after_retry(self) -> None:
        # F031 §5: 重试 1 次后成功
        from unittest.mock import AsyncMock, patch

        respx.get(_AMAP_BASE_URL).mock(
            side_effect=[
                httpx.ReadTimeout("first try"),
                httpx.Response(200, json=_load_fixture("sunny_base")),
            ]
        )

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            result = await amap_get_weather(
                location="110000",
                client=_make_client(max_retries=1),
            )

        assert result["condition"] == "sunny"


# ---------------------------------------------------------------------------
# TestAmapGetWeatherParamValidation — 入参合法性
# ---------------------------------------------------------------------------


class TestAmapGetWeatherParamValidation:
    @pytest.mark.asyncio
    async def test_empty_location_rejected(self) -> None:
        # F031 §3.1: location 是必填地标 / 经纬度
        with pytest.raises(ValueError, match="location"):
            await amap_get_weather(
                location="",
                client=_make_client(),
            )

    @pytest.mark.asyncio
    async def test_whitespace_only_location_rejected(self) -> None:
        with pytest.raises(ValueError, match="location"):
            await amap_get_weather(
                location="   ",
                client=_make_client(),
            )

    @pytest.mark.asyncio
    async def test_invalid_extensions_rejected(self) -> None:
        # F031 §3: extensions 必须是 base 或 all
        with pytest.raises(ValueError, match="extensions"):
            await amap_get_weather(
                location="110000",
                extensions="hourly",  # type: ignore[arg-type]
                client=_make_client(),
            )


# ---------------------------------------------------------------------------
# TestAmapGetWeatherSLA — F031 §2: 调用 1 秒内返回
# ---------------------------------------------------------------------------


class TestAmapGetWeatherSLA:
    @respx.mock
    @pytest.mark.asyncio
    async def test_mocked_call_responds_under_500ms(self) -> None:
        # F031 §2: 调用 1 秒内返回 (mock 模式应远低于此)
        import time

        payload = _load_fixture("sunny_base")
        respx.get(_AMAP_BASE_URL).mock(return_value=httpx.Response(200, json=payload))

        started = time.monotonic()
        await amap_get_weather(
            location="110000",
            client=_make_client(),
        )
        elapsed_ms = (time.monotonic() - started) * 1000
        assert elapsed_ms < 500, f"mock 调用耗时 {elapsed_ms:.1f}ms 超过 500ms"