"""F030 — 高德周边搜索（餐厅）单测.

覆盖 [spec/features/F030-amap-restaurant-search.md §2 / §6] 验收点:

- mock 高德返回 10 条 → 解析正确，距离 / 评分 / 价格 / 经纬度保留
- mock 返回 0 条 → `partial=true`，不抛错
- mock 缺评分 / 缺价格字段 → 不抛错，字段降级为 None
- mock 网络超时 → 重试 1 次后抛 `AmapNetworkError`
- mock 401 → 抛 `AmapInvalidKeyError`
- mock 200 但 `status=0` (CUQPS_HAS_EXCEEDED_THE_LIMIT) → 抛 `AmapQuotaExceededError`
- mock 高德返回『距离 > 3km』POI → 被剔除，不进 results
- mock 返回顺序乱序 → 按 (距离 / max_distance) + (rating / 5) 加权排序

不重复 F031 / F002 / F003 已经覆盖的内容（错误码家族 / Node 接口）。
本文件只断言 **F030 餐厅搜索 Tool** 的契约本身。
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from app.core.exceptions import (
    AmapInvalidKeyError,
    AmapNetworkError,
    AmapQuotaExceededError,
)
from app.mcp.amap.client import AmapClient
from app.mcp.amap.restaurant import amap_search_restaurants

# ---------------------------------------------------------------------------
# Fixture loader — 复用 backend/tests/fixtures/amap_restaurant_responses.json
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
_FIXTURE_PATH = _FIXTURES_DIR / "amap_restaurant_responses.json"


def _load_fixture(name: str) -> dict[str, object]:
    """从 fixture JSON 读出指定 key 的负载（仍带原始字符串字段）。"""
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    payload = data[name]
    assert isinstance(payload, dict)
    return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AMAP_URL = "https://restapi.amap.com/v3/place/around"
_AMAP_PARAMS_DEFAULT: dict[str, object] = {
    "key": "test-amap-key",
    "keywords": "火锅",
    "location": "116.433840,39.908740",
    "radius": "1500",
    "offset": "10",
    "page": "1",
    "extensions": "all",
    "types": "050000",
    "output": "JSON",
}


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


def _sample_query() -> dict[str, object]:
    """F030 §3.1 默认查询：keyword=火锅 + 国贸锚点 + 1.5km。"""
    return {
        "keywords": ["火锅"],
        "location": "116.433840,39.908740",
        "radius_meters": 1500,
        "min_rating": 3.5,
        "max_results": 10,
    }


# ---------------------------------------------------------------------------
# TestAmapClientConstruction — 客户端构造契约
# ---------------------------------------------------------------------------


class TestAmapClientConstruction:
    def test_requires_api_key(self) -> None:
        # F030 §6: 启动时校验 key 存在
        with pytest.raises(ValueError, match="api_key"):
            AmapClient(api_key="", timeout_seconds=1.0)

    def test_default_timeout_when_not_specified(self) -> None:
        client = AmapClient(api_key="k", timeout_seconds=2.0)
        assert client.timeout_seconds == 2.0

    def test_default_max_retries_is_one(self) -> None:
        # F030 §5: 网络/超时重试 1 次（即最多 2 次尝试）
        client = AmapClient(api_key="k", timeout_seconds=1.0)
        assert client.max_retries == 1

    def test_strips_trailing_slash_from_base_url(self) -> None:
        client = AmapClient(api_key="k", timeout_seconds=1.0, base_url="https://restapi.amap.com/")
        assert client.base_url == "https://restapi.amap.com"


# ---------------------------------------------------------------------------
# TestAmapSearchRestaurantsHappyPath — 10 条 POI 全字段解析
# ---------------------------------------------------------------------------


class TestAmapSearchRestaurantsHappyPath:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_10_pois_with_full_fields(self) -> None:
        # Arrange
        payload = _load_fixture("happy_path_10_pois")
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        # Act
        result = await amap_search_restaurants(
            keywords=["火锅"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=3.5,
            max_results=10,
            client=_make_client(),
        )

        # Assert — 整体 envelope
        assert result["partial"] is False
        assert result["raw_count"] == 10
        assert len(result["restaurants"]) == 10

        # Assert — 第一条（最近、评分最高 = 海底捞）
        first = result["restaurants"][0]
        assert first["poi_id"] == "B0FFFDDCFE"
        assert first["name"] == "海底捞(国贸店)"
        assert first["address"] == "北京市朝阳区建国门外大街1号"
        assert first["distance_meters"] == 235
        assert first["rating"] == pytest.approx(4.8)
        assert first["avg_price"] == Decimal("120")
        assert first["cuisine_tags"] == ["火锅", "川菜", "服务好"]
        # 经纬度是 (lng, lat) 元组
        assert first["location"] == (116.433840, 39.908740)

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_expected_query_params(self) -> None:
        # Arrange
        payload = _load_fixture("empty_result")
        route = respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        # Act
        await amap_search_restaurants(
            keywords=["火锅", "川菜"],
            location="116.433840,39.908740",
            radius_meters=2000,
            min_rating=4.0,
            max_results=10,
            client=_make_client(),
        )

        # Assert — 验证 query string 的字段
        request = route.calls.last.request
        url = request.url
        params = dict(url.params)
        assert params["key"] == "test-amap-key"
        # 高德 keywords 支持 | 分隔
        assert params["keywords"] == "火锅|川菜"
        assert params["location"] == "116.433840,39.908740"
        assert params["radius"] == "2000"
        assert params["types"] == "050000"
        assert params["offset"] == "10"
        assert params["extensions"] == "all"

    @respx.mock
    @pytest.mark.asyncio
    async def test_partial_false_when_at_least_three_results(self) -> None:
        # 10 条 → partial=false
        payload = _load_fixture("happy_path_10_pois")
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_search_restaurants(
            keywords=["火锅"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=3.5,
            max_results=10,
            client=_make_client(),
        )

        assert result["partial"] is False
        assert result["raw_count"] == 10


# ---------------------------------------------------------------------------
# TestAmapSearchRestaurantsEdgeCases — 0 条 / 缺字段 / 超距离
# ---------------------------------------------------------------------------


class TestAmapSearchRestaurantsEdgeCases:
    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_result_returns_partial_true_not_raise(self) -> None:
        # F030 §2 / §5: AMAP_NO_RESULT → restaurants=[], partial=true
        payload = _load_fixture("empty_result")
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_search_restaurants(
            keywords=["某个完全找不到的菜"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=3.5,
            max_results=10,
            client=_make_client(),
        )

        assert result["partial"] is True
        assert result["restaurants"] == []
        assert result["raw_count"] == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_rating_and_cost_degrade_to_none(self) -> None:
        # F030 §9 待澄清: 评分字段缺失时降权，不剔除 → rating=None
        payload = _load_fixture("happy_path_with_missing_rating_and_cost")
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_search_restaurants(
            keywords=["火锅"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=0.0,  # 关掉过滤以确保所有 POI 都进入解析
            max_results=10,
            client=_make_client(),
        )

        assert result["raw_count"] == 3
        assert len(result["restaurants"]) == 3
        # 缺评分的 POI → rating=None；缺价格的 POI → avg_price=None
        for r in result["restaurants"]:
            assert r["poi_id"] in {"B0FFFE0100", "B0FFFE0101", "B0FFFE0102"}
        no_rating = next(r for r in result["restaurants"] if r["poi_id"] == "B0FFFE0100")
        assert no_rating["rating"] is None
        assert no_rating["avg_price"] is None
        only_rating = next(r for r in result["restaurants"] if r["poi_id"] == "B0FFFE0101")
        assert only_rating["rating"] == pytest.approx(3.9)
        assert only_rating["avg_price"] is None
        only_cost = next(r for r in result["restaurants"] if r["poi_id"] == "B0FFFE0102")
        assert only_cost["rating"] is None
        assert only_cost["avg_price"] == Decimal("60")

    @respx.mock
    @pytest.mark.asyncio
    async def test_distance_above_3km_is_dropped(self) -> None:
        # F030 §2: 距离 > 3km 的剔除
        far_payload = {
            "status": "1",
            "count": "2",
            "info": "OK",
            "infocode": "10000",
            "pois": [
                {
                    "id": "FAR_OK",
                    "name": "近店",
                    "type": "餐饮服务;中餐厅",
                    "address": "x",
                    "location": "116.440000,39.910000",
                    "distance": "1500",
                    "biz_ext": {"rating": "4.0", "cost": "80"},
                },
                {
                    "id": "FAR_DROP",
                    "name": "远店",
                    "type": "餐饮服务;中餐厅",
                    "address": "x",
                    "location": "116.510000,39.940000",
                    "distance": "7500",  # 7.5km → 必须剔除
                    "biz_ext": {"rating": "5.0", "cost": "80"},
                },
            ],
        }
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=far_payload))

        result = await amap_search_restaurants(
            keywords=["火锅"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=0.0,
            max_results=10,
            client=_make_client(),
        )

        ids = {r["poi_id"] for r in result["restaurants"]}
        assert "FAR_OK" in ids
        assert "FAR_DROP" not in ids, "距离 > 3km 必须被剔除 (F030 §2)"

    @respx.mock
    @pytest.mark.asyncio
    async def test_results_sorted_by_distance_then_rating(self) -> None:
        # F030 §2 / §4: 按 (距离 / max_distance) + (rating / 5) 加权排序
        # 距离近 + 评分高的应当排前；这里海底捞(235m, 4.8) vs 凑凑(278m, 4.5)
        payload = _load_fixture("happy_path_10_pois")
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_search_restaurants(
            keywords=["火锅"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=0.0,
            max_results=10,
            client=_make_client(),
        )

        # 排序后的第一条应当是『最近 + 评分高』的海底捞（235m, 4.8）
        assert result["restaurants"][0]["poi_id"] == "B0FFFDDCFE"
        # 距离必须单调递增（平局按评分降序）
        distances = [r["distance_meters"] for r in result["restaurants"]]
        assert distances == sorted(distances), f"结果必须按 distance 升序排列, 实际={distances}"

    @respx.mock
    @pytest.mark.asyncio
    async def test_min_rating_filters_out_low_rated(self) -> None:
        payload = _load_fixture("happy_path_10_pois")
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await amap_search_restaurants(
            keywords=["火锅"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=4.6,  # 只保留 ≥ 4.6 的店
            max_results=10,
            client=_make_client(),
        )

        for r in result["restaurants"]:
            assert r["rating"] is not None and r["rating"] >= 4.6

    @respx.mock
    @pytest.mark.asyncio
    async def test_two_results_still_marks_partial(self) -> None:
        # F030 §2: 不足 3 家时返回所有可用 + 标记 partial=true
        two_payload = {
            "status": "1",
            "count": "2",
            "info": "OK",
            "infocode": "10000",
            "pois": [
                {
                    "id": "OK_1",
                    "name": "A",
                    "type": "餐饮服务",
                    "address": "x",
                    "location": "116.430000,39.910000",
                    "distance": "200",
                    "biz_ext": {"rating": "4.5", "cost": "80"},
                },
                {
                    "id": "OK_2",
                    "name": "B",
                    "type": "餐饮服务",
                    "address": "y",
                    "location": "116.431000,39.910500",
                    "distance": "400",
                    "biz_ext": {"rating": "4.2", "cost": "70"},
                },
            ],
        }
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=two_payload))

        result = await amap_search_restaurants(
            keywords=["火锅"],
            location="116.433840,39.908740",
            radius_meters=1500,
            min_rating=0.0,
            max_results=10,
            client=_make_client(),
        )

        assert len(result["restaurants"]) == 2
        assert result["partial"] is True


# ---------------------------------------------------------------------------
# TestAmapErrorMapping — 错误码透传 (F030 §5)
# ---------------------------------------------------------------------------


class TestAmapErrorMapping:
    @respx.mock
    @pytest.mark.asyncio
    async def test_401_raises_amap_invalid_key(self) -> None:
        # F030 §5: AMAP_INVALID_KEY
        payload = _load_fixture("invalid_key_401")
        # 高德 invalid key 在协议层是 200 + status=0 + infocode=10001；但某些
        # 网关也会回 401。两种都要映射到 AmapInvalidKeyError。
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        with pytest.raises(AmapInvalidKeyError):
            await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_status_raises_amap_invalid_key_when_marker(self) -> None:
        # F030 §5: AMAP_INVALID_KEY 也可由 HTTP 401 触发
        respx.get(_AMAP_URL).mock(
            return_value=httpx.Response(401, json={"status": "0", "info": "INVALID_USER_KEY"})
        )

        with pytest.raises(AmapInvalidKeyError):
            await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_quota_exceeded_in_body_raises_amap_quota(self) -> None:
        # F030 §5: AMAP_QUOTA_EXCEEDED — 高德通常 200 + status=0 + infocode=10044
        payload = _load_fixture("quota_exceeded_429_response_status")
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))

        with pytest.raises(AmapQuotaExceededError):
            await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_http_429_raises_amap_quota(self) -> None:
        # F030 §5: HTTP 429 也映射到 AMAP_QUOTA_EXCEEDED
        respx.get(_AMAP_URL).mock(return_value=httpx.Response(429, json={"error": "rate"}))
        with pytest.raises(AmapQuotaExceededError):
            await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_network_timeout_retries_then_raises_amap_network_error(self) -> None:
        # F030 §5: AMAP_NETWORK_ERROR — 重试 1 次后抛错
        from unittest.mock import AsyncMock, patch

        respx.get(_AMAP_URL).mock(side_effect=httpx.ReadTimeout("timeout"))

        with (
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
            pytest.raises(AmapNetworkError),
        ):
            await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(max_retries=1),
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_timeout_succeeds_after_retry(self) -> None:
        # F030 §5: 重试 1 次后成功
        from unittest.mock import AsyncMock, patch

        respx.get(_AMAP_URL).mock(
            side_effect=[
                httpx.ReadTimeout("first try"),
                httpx.Response(200, json=_load_fixture("happy_path_10_pois")),
            ]
        )

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
            result = await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(max_retries=1),
            )

        assert len(result["restaurants"]) == 10
        assert result["partial"] is False


# ---------------------------------------------------------------------------
# TestAmapClientFactory — 工厂函数与配置注入
# ---------------------------------------------------------------------------


class TestAmapClientFactory:
    def test_get_amap_client_uses_settings_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # F030 §6: AMAP_API_KEY 从 .env 读；缺失则 fail-fast
        from app.core.config import get_settings
        from app.mcp.amap.client import get_amap_client, reset_amap_client_cache

        reset_amap_client_cache()
        get_settings.cache_clear()
        monkeypatch.setenv("AMAP_API_KEY", "env-test-key")
        monkeypatch.setenv("AMAP_TIMEOUT_SECONDS", "1.5")

        try:
            client = get_amap_client()
            assert client._api_key == "env-test-key"
            assert client.timeout_seconds == 1.5
        finally:
            reset_amap_client_cache()
            get_settings.cache_clear()


# ---------------------------------------------------------------------------
# TestAmapSearchRestaurantsParamValidation — 入参合法性
# ---------------------------------------------------------------------------


class TestAmapSearchRestaurantsParamValidation:
    @pytest.mark.asyncio
    async def test_empty_keywords_rejected(self) -> None:
        with pytest.raises(ValueError, match="keywords"):
            await amap_search_restaurants(
                keywords=[],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(),
            )

    @pytest.mark.asyncio
    async def test_too_many_keywords_rejected(self) -> None:
        # F030 §3.1: keywords 1-5 个
        with pytest.raises(ValueError, match="keywords"):
            await amap_search_restaurants(
                keywords=["a", "b", "c", "d", "e", "f"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=10,
                client=_make_client(),
            )

    @pytest.mark.asyncio
    async def test_radius_out_of_range_rejected(self) -> None:
        # 半径 > 5000m 无意义（spec 隐含 3km 剔除上限）
        with pytest.raises(ValueError, match="radius_meters"):
            await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=10000,
                min_rating=3.5,
                max_results=10,
                client=_make_client(),
            )

    @pytest.mark.asyncio
    async def test_max_results_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_results"):
            await amap_search_restaurants(
                keywords=["火锅"],
                location="116.433840,39.908740",
                radius_meters=1500,
                min_rating=3.5,
                max_results=50,
                client=_make_client(),
            )
