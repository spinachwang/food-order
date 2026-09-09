"""F051 — 高德 /v3/place/text Tool 单测.

覆盖 [spec/features/F051-structured-address.md §5.3 / §9] 验收点:

- 默认 types="050000" (向后兼容 F030)
- types="商圈" / "商务住宅|地名地址信息" 自定义类别
- city="310100" → citylimit=true 强制 city 范围匹配
- offset 截断 (mock 返回 25 条, offset=5 → 只保留 5 条)
- 缺 poi_id / 缺 location → 丢弃该项
- mock 网络超时 / 401 → 对应 Amap 子类异常
- 入参 keywords 为空 / 越界 → ValueError
"""
from __future__ import annotations

import httpx
import pytest
import respx
from app.core.exceptions import (
    AmapInvalidKeyError,
    AmapNetworkError,
    AmapQuotaExceededError,
)
from app.mcp.amap.client import AmapClient
from app.mcp.amap.place_text import DEFAULT_TYPES, amap_search_places

_AMAP_URL = "https://restapi.amap.com/v3/place/text"


def _make_client(**overrides: object) -> AmapClient:
    defaults: dict[str, object] = {
        "api_key": "test-amap-key",
        "timeout_seconds": 0.5,
        "max_retries": 1,
        "base_url": "https://restapi.amap.com",
    }
    defaults.update(overrides)
    return AmapClient(**defaults)  # type: ignore[arg-type]


def _mock(respx_mock: respx.MockRouter, payload: dict[str, object]) -> None:
    respx_mock.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))


def _mock_with_assert(
    respx_mock: respx.MockRouter, payload: dict[str, object]
) -> respx.MockRouter:
    respx_mock.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))
    return respx_mock


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


class TestAmapSearchPlacesHappy:
    @pytest.mark.asyncio
    async def test_default_types_is_food_category(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """F030 §3.3 向后兼容: 不传 types → 默认 '050000' 餐饮服务大类."""
        route = respx_mock.get(_AMAP_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": [
                        {
                            "id": "B0FFFA48PBKB0FFFA48PBK0001",
                            "name": "海底捞",
                            "address": "上海市静安区南京西路 1788 号",
                            "type": "餐饮服务;中餐厅;火锅",
                            "location": "121.457000,31.229000",
                        }
                    ],
                },
            )
        )

        result = await amap_search_places(
            keywords="海底捞", client=_make_client()
        )

        assert len(result["pois"]) == 1
        assert result["pois"][0]["name"] == "海底捞"
        # 验证请求参数包含 DEFAULT_TYPES
        request = route.calls[0].request
        assert request.url.params["types"] == DEFAULT_TYPES
        assert request.url.params["types"] == "050000"

    @pytest.mark.asyncio
    async def test_custom_types_business_area(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """F051 §4.2 商圈搜索: types='商圈'."""
        route = respx_mock.get(_AMAP_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": [
                        {
                            "id": "B0FFFBUSINESSAREA00000000000",
                            "name": "南京西路商圈",
                            "address": "上海市静安区南京西路",
                            "type": "商圈;购物;综合商场",
                            "location": "121.457000,31.229000",
                        }
                    ],
                },
            )
        )

        result = await amap_search_places(
            keywords="南京西路",
            city="310100",
            types="商圈",
            client=_make_client(),
        )

        assert result["pois"][0]["name"] == "南京西路商圈"
        request = route.calls[0].request
        assert request.url.params["types"] == "商圈"
        assert request.url.params["city"] == "310100"
        assert request.url.params["citylimit"] == "true"

    @pytest.mark.asyncio
    async def test_community_search_types(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """F051 §4.2 小区搜索: types='商务住宅|地名地址信息'."""
        route = respx_mock.get(_AMAP_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": [
                        {
                            "id": "B0FFFCOMMUNITY00000000000000",
                            "name": "静安嘉里中心",
                            "address": "上海市静安区南京西路 1515 号",
                            "type": "商务住宅;楼宇;商住两用楼宇",
                            "location": "121.450000,31.228000",
                        }
                    ],
                },
            )
        )

        result = await amap_search_places(
            keywords="静安嘉里",
            city="310100",
            types="商务住宅|地名地址信息",
            client=_make_client(),
        )

        assert result["pois"][0]["name"] == "静安嘉里中心"
        request = route.calls[0].request
        assert request.url.params["types"] == "商务住宅|地名地址信息"

    @pytest.mark.asyncio
    async def test_offset_truncates_results(
        self, respx_mock: respx.MockRouter
    ) -> None:
        # 高德返回 25 条, offset=5 → 只保留前 5 条
        pois = [
            {
                "id": f"B0FFFA48PBKB0FFFA48PBK{i:04d}",
                "name": f"餐厅{i}",
                "address": f"地址{i}",
                "type": "餐饮服务",
                "location": "121.457000,31.229000",
            }
            for i in range(25)
        ]
        _mock(respx_mock, {"status": "1", "pois": pois})

        result = await amap_search_places(
            keywords="餐厅", offset=5, client=_make_client()
        )

        assert len(result["pois"]) == 5
        assert result["count"] == 25  # 高德原始条数保留

    @pytest.mark.asyncio
    async def test_no_city_no_citylimit_param(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """不传 city → 全国范围搜索, 不传 citylimit."""
        route = respx_mock.get(_AMAP_URL).mock(
            return_value=httpx.Response(200, json={"status": "1", "pois": []})
        )

        await amap_search_places(keywords="餐厅", client=_make_client())

        request = route.calls[0].request
        assert "city" not in request.url.params
        assert "citylimit" not in request.url.params


# ---------------------------------------------------------------------------
# 解析容错
# ---------------------------------------------------------------------------


class TestAmapSearchPlacesParsing:
    @pytest.mark.asyncio
    async def test_poi_without_id_is_dropped(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock(
            respx_mock,
            {
                "status": "1",
                "pois": [
                    {"name": "无名餐厅"},  # 缺 id → 丢弃
                    {
                        "id": "B0FFFA48PBKB0FFFA48PBK0001",
                        "name": "海底捞",
                        "address": "上海市静安区南京西路 1788 号",
                        "type": "餐饮服务",
                        "location": "121.457000,31.229000",
                    },
                ],
            },
        )

        result = await amap_search_places(
            keywords="餐厅", client=_make_client()
        )

        assert len(result["pois"]) == 1
        assert result["pois"][0]["name"] == "海底捞"

    @pytest.mark.asyncio
    async def test_poi_without_location_is_dropped(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock(
            respx_mock,
            {
                "status": "1",
                "pois": [
                    {
                        "id": "B0FFFA48PBKB0FFFA48PBK0001",
                        "name": "无坐标餐厅",
                        "address": "某处",
                        "type": "餐饮服务",
                        # location 缺失
                    },
                    {
                        "id": "B0FFFA48PBKB0FFFA48PBK0002",
                        "name": "有坐标餐厅",
                        "address": "某处",
                        "type": "餐饮服务",
                        "location": "121.457000,31.229000",
                    },
                ],
            },
        )

        result = await amap_search_places(
            keywords="餐厅", client=_make_client()
        )

        assert len(result["pois"]) == 1
        assert result["pois"][0]["name"] == "有坐标餐厅"

    @pytest.mark.asyncio
    async def test_empty_result_returns_zero_count(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock(respx_mock, {"status": "1", "pois": []})

        result = await amap_search_places(
            keywords="火星餐厅", client=_make_client()
        )

        assert result["pois"] == []
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# 错误码
# ---------------------------------------------------------------------------


class TestAmapSearchPlacesErrors:
    @pytest.mark.asyncio
    async def test_network_timeout_raises_network_error(
        self, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.get(_AMAP_URL).mock(side_effect=httpx.TimeoutException("timeout"))

        with pytest.raises(AmapNetworkError):
            await amap_search_places(keywords="餐厅", client=_make_client())

    @pytest.mark.asyncio
    async def test_unauthorized_raises_invalid_key(
        self, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.get(_AMAP_URL).mock(return_value=httpx.Response(401, json={}))

        with pytest.raises(AmapInvalidKeyError):
            await amap_search_places(keywords="餐厅", client=_make_client())

    @pytest.mark.asyncio
    async def test_quota_exceeded_raises_quota_error(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock(
            respx_mock,
            {
                "status": "0",
                "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
                "infocode": "10044",
                "pois": [],
            },
        )

        with pytest.raises(AmapQuotaExceededError):
            await amap_search_places(keywords="餐厅", client=_make_client())


# ---------------------------------------------------------------------------
# 入参校验
# ---------------------------------------------------------------------------


class TestAmapSearchPlacesValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", ["", "   "])
    async def test_empty_keywords_raises_value_error(self, bad: str) -> None:
        with pytest.raises(ValueError, match="keywords"):
            await amap_search_places(keywords=bad, client=_make_client())

    @pytest.mark.asyncio
    async def test_keywords_too_long_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="keywords"):
            await amap_search_places(
                keywords="x" * 100, client=_make_client()
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_offset", [0, 26, -1])
    async def test_offset_out_of_range(self, bad_offset: int) -> None:
        with pytest.raises(ValueError, match="offset"):
            await amap_search_places(
                keywords="餐厅", offset=bad_offset, client=_make_client()
            )

    @pytest.mark.asyncio
    async def test_types_too_long(self) -> None:
        with pytest.raises(ValueError, match="types"):
            await amap_search_places(
                keywords="餐厅",
                types="x" * 100,
                client=_make_client(),
            )
