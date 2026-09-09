"""F051 — 高德 /geocode/regeo Tool 单测.

覆盖 [spec/features/F051-structured-address.md §5.2 / §9] 验收点:

- 合法 "lng,lat" → 解析 + 投影到 RegeoInfo
- addressComponent 嵌套解析 (province / city / district / adcode)
- 细粒度字段: street (街道) / community (小区) / door_no (门牌号) / poi_id
- extensions=all 才会返回细粒度 + pois[]; extensions=base 仅返回地址段
- location 字段解析失败 → fallback 用入参 lng/lat
- 空 regeocode → 抛 `AmapLocationInvalidError`
- mock 网络超时 / 401 / 配额 → 对应 Amap 子类异常
- 入参格式非法 / 越界 → ValueError
"""
from __future__ import annotations

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
from app.mcp.amap.regeo import amap_regeo

_AMAP_URL = "https://restapi.amap.com/v3/geocode/regeo"


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


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


class TestAmapRegeoHappy:
    @pytest.mark.asyncio
    async def test_parses_full_response(self, respx_mock: respx.MockRouter) -> None:
        """完整响应: 含 township + neighborhood + streetNumber + pois[] → 全部细粒度字段解析."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "regeocode": {
                    "formatted_address": "浙江省杭州市钱塘区河庄街道兴耀·岚漫之城7栋",
                    "addressComponent": {
                        "province": "浙江省",
                        "city": "杭州市",
                        "district": "钱塘区",
                        "adcode": "330114",
                        "township": "河庄街道",
                        "neighborhood": {
                            "name": "兴耀·岚漫之城",
                            "type": "住宅区",
                            "location": "120.481281,30.315226",
                        },
                        "streetNumber": {
                            "street": "河庄街道",
                            "number": "7栋",
                            "location": "120.481281,30.315226",
                            "direction": "东",
                            "distance": "0",
                        },
                    },
                    "pois": [
                        {
                            "id": "B0FFGKABCD1234567890",
                            "name": "兴耀·岚漫之城",
                            "type": "商务住宅;住宅区;住宅小区",
                            "address": "浙江省杭州市钱塘区河庄街道",
                            "location": "120.481281,30.315226",
                        }
                    ],
                    "location": "121.481281,30.315226",
                },
            },
        )

        result = await amap_regeo(
            location="121.481281,30.315226", client=_make_client()
        )

        assert result["province"] == "浙江省"
        assert result["city"] == "杭州市"
        assert result["district"] == "钱塘区"
        assert result["adcode"] == "330114"
        assert result["formatted_address"] == "浙江省杭州市钱塘区河庄街道兴耀·岚漫之城7栋"
        # 经纬度来自 streetNumber.location (AMAP 优先; 缺时 fallback 入参)
        assert result["longitude"] == 121.481281
        assert result["latitude"] == 30.315226
        # 细粒度: 街道优先 township, 小区来自 neighborhood, 门牌号 + poi_id 都填
        assert result["street"] == "河庄街道"
        assert result["community"] == "兴耀·岚漫之城"
        assert result["door_no"] == "7栋"
        assert result["poi_id"] == "B0FFGKABCD1234567890"

    @pytest.mark.asyncio
    async def test_location_fallback_to_input_coords(
        self, respx_mock: respx.MockRouter
    ) -> None:
        # 高德偶发不返回 location 字段 → fallback 用入参
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                        "formatted_address": "上海市黄浦区",
                        "addressComponent": {
                            "province": "上海市",
                            "city": "上海市",
                            "district": "黄浦区",
                            "adcode": "310101",
                        },
                        # location 字段缺失; township / neighborhood / pois 也无
                },
            },
        )

        result = await amap_regeo(
            location="121.484270,31.231410", client=_make_client()
        )

        assert result["longitude"] == 121.484270
        assert result["latitude"] == 31.231410
        assert result["district"] == "黄浦区"
        # 细粒度字段全缺失 → 全部 None (而不是空串)
        assert result["street"] is None
        assert result["community"] is None
        assert result["door_no"] is None
        assert result["poi_id"] is None

    @pytest.mark.asyncio
    async def test_missing_address_component_fields_default_to_empty(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                        "formatted_address": "未知区域",
                        "addressComponent": {},  # 字段全缺
                },
            },
        )

        result = await amap_regeo(
            location="100.0,30.0", client=_make_client()
        )

        assert result["province"] == ""
        assert result["city"] == ""
        assert result["district"] == ""
        assert result["adcode"] == ""
        assert result["formatted_address"] == "未知区域"
        # 细粒度字段 → 全部 None
        assert result["street"] is None
        assert result["community"] is None
        assert result["door_no"] is None
        assert result["poi_id"] is None


# ---------------------------------------------------------------------------
# 错误码
# ---------------------------------------------------------------------------


class TestAmapRegeoErrors:
    @pytest.mark.asyncio
    async def test_empty_regeocode_raises_location_invalid(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock(
            respx_mock,
            {"status": "1", "info": "OK", "infocode": "10000", "regeocode": None},
        )

        with pytest.raises(AmapLocationInvalidError):
            await amap_regeo(
                location="121.0,31.0", client=_make_client()
            )

    @pytest.mark.asyncio
    async def test_network_timeout_raises_network_error(
        self, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.get(_AMAP_URL).mock(side_effect=httpx.TimeoutException("timeout"))

        with pytest.raises(AmapNetworkError):
            await amap_regeo(location="121.0,31.0", client=_make_client())

    @pytest.mark.asyncio
    async def test_unauthorized_raises_invalid_key(
        self, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.get(_AMAP_URL).mock(return_value=httpx.Response(401, json={}))

        with pytest.raises(AmapInvalidKeyError):
            await amap_regeo(location="121.0,31.0", client=_make_client())

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
                "regeocode": None,
            },
        )

        with pytest.raises(AmapQuotaExceededError):
            await amap_regeo(location="121.0,31.0", client=_make_client())


# ---------------------------------------------------------------------------
# 入参校验
# ---------------------------------------------------------------------------


class TestAmapRegeoValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_input",
        [
            "",  # 空串
            "121.0",  # 缺 lat
            "121.0,31.0,50.0",  # 多一段
            "abc,def",  # 非数字
            "121.5;31.0",  # 错分隔符
            "  ,  ",  # 仅分隔符
        ],
    )
    async def test_invalid_format_raises_value_error(self, bad_input: str) -> None:
        with pytest.raises(ValueError, match="location"):
            await amap_regeo(location=bad_input, client=_make_client())

    @pytest.mark.asyncio
    async def test_longitude_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="经度"):
            await amap_regeo(location="181.0,31.0", client=_make_client())

    @pytest.mark.asyncio
    async def test_latitude_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="纬度"):
            await amap_regeo(location="121.0,91.0", client=_make_client())

    @pytest.mark.asyncio
    async def test_boundary_values_accepted(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                        "formatted_address": "边界点",
                        "addressComponent": {
                            "province": "x",
                            "city": "y",
                            "district": "z",
                            "adcode": "000000",
                        },
                },
            },
        )

        # 经度 -180 / 纬度 -90 边界值
        result = await amap_regeo(
            location="-180.0,-90.0", client=_make_client()
        )
        assert result["longitude"] == -180.0
        assert result["latitude"] == -90.0


# ---------------------------------------------------------------------------
# 细粒度字段解析 (F051 §3.2 StructuredAddress 街道/小区/POI/门牌号)
# ---------------------------------------------------------------------------


class TestAmapRegeoGranularFields:
    """新增细粒度字段: street / community / door_no / poi_id.

    这些字段源于 AMAP `extensions=all` 才返回的 `addressComponent.township` /
    `addressComponent.neighborhood` / `addressComponent.streetNumber` /
    `pois[]` 数组. 高德偶发缺失 — 必须 None-safe.
    """

    @pytest.mark.asyncio
    async def test_extensions_all_is_requested(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """细粒度字段依赖 extensions=all. base 仅返回地址段, 无法解析."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "formatted_address": "x",
                    "addressComponent": {"adcode": "310106"},
                },
            },
        )

        await amap_regeo(location="121.0,31.0", client=_make_client())

        sent = dict(respx.calls.last.request.url.params)
        assert sent["extensions"] == "all"

    @pytest.mark.asyncio
    async def test_street_prefers_township_over_streetNumber(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """street 优先级: township > streetNumber.street (前者更精确, 是街道名)."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {
                        "adcode": "330114",
                        "township": "河庄街道",
                        "streetNumber": {
                            "street": "另一条路",  # 应被 township 覆盖
                            "number": "5号",
                        },
                    },
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        assert result["street"] == "河庄街道"
        assert result["door_no"] == "5号"

    @pytest.mark.asyncio
    async def test_street_falls_back_to_streetNumber_street(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """township 缺失时, 用 streetNumber.street 兜底."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {
                        "adcode": "310106",
                        # township 缺失
                        "streetNumber": {
                            "street": "南京西路",
                            "number": "1788号",
                        },
                    },
                },
            },
        )

        result = await amap_regeo(location="121.0,31.0", client=_make_client())
        assert result["street"] == "南京西路"
        assert result["door_no"] == "1788号"

    @pytest.mark.asyncio
    async def test_poi_id_picks_first_valid_poi(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """`pois[0].id` 第一个合规 POI id 即采纳 (短/长均接受, AMAP 实际 8-12 位)."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {"adcode": "330114"},
                    "pois": [
                        {"id": "B0I6KCBRAM"},  # 11 位 (AMAP 主流)
                        {"id": "B0FFGKABCD1234567890"},  # 20 位 (早期风格)
                    ],
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        assert result["poi_id"] == "B0I6KCBRAM"

    @pytest.mark.asyncio
    async def test_poi_id_drops_invalid_format(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """AMAP 偶发返回不合规 id (空 / 太短 / 含特殊字符) — 直接丢弃, poi_id = None."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {"adcode": "330114"},
                    "pois": [
                        {"id": ""},  # 空
                        {"id": "short"},  # 长度不够 (< 8 位)
                        {"id": "lower-case-id-20+chars"},  # 含小写字母
                    ],
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        assert result["poi_id"] is None

    @pytest.mark.asyncio
    async def test_poi_id_accepts_short_amap_format(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """AMAP 实际 POI id 形如 `B0I6KCBRAM` (11 位) — 必须采纳, 不被正则误杀."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {"adcode": "330114"},
                    "pois": [{"id": "B0I6KCBRAM"}],
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        assert result["poi_id"] == "B0I6KCBRAM"

    @pytest.mark.asyncio
    async def test_community_from_neighborhood_name(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """community ← addressComponent.neighborhood.name."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {
                        "adcode": "330114",
                        "neighborhood": {
                            "name": "兴耀·岚漫之城",
                            "type": "住宅区",
                        },
                    },
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        assert result["community"] == "兴耀·岚漫之城"

    @pytest.mark.asyncio
    async def test_empty_neighborhood_name_yields_none(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """neighborhood 存在但 name 空 → community = None (不返回空串)."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {
                        "adcode": "330114",
                        "neighborhood": {"name": "", "type": "x"},
                    },
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        assert result["community"] is None

    @pytest.mark.asyncio
    async def test_community_falls_back_to_poi_when_neighborhood_empty(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """AMAP 实际: 小区名常塞在 `pois[0].name` (type 是住宅小区),
        `addressComponent.neighborhood.name` 是空数组. 必须 fallback, 否则丢失.

        兜底条件: POI type 必须命中住宅/小区分类 (避免把"海底捞"当成小区名).
        """
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {
                        "adcode": "330114",
                        "neighborhood": {"name": [], "type": []},  # AMAP 空信号
                    },
                    "pois": [
                        {
                            "id": "B0I6KCBRAM",
                            "name": "兴耀·岚漫之城",
                            "type": "商务住宅;住宅区;住宅小区",
                        }
                    ],
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        assert result["community"] == "兴耀·岚漫之城"
        assert result["poi_id"] == "B0I6KCBRAM"

    @pytest.mark.asyncio
    async def test_community_fallback_skips_non_residential_poi(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """POI type 不是住宅小区 (例如海底捞火锅店) → 不当作 community 兜底."""
        _mock(
            respx_mock,
            {
                "status": "1",
                "regeocode": {
                    "addressComponent": {
                        "adcode": "330114",
                        "neighborhood": {"name": [], "type": []},
                    },
                    "pois": [
                        {
                            "id": "B0FFFOOD123",
                            "name": "海底捞",
                            "type": "餐饮服务;中餐厅",
                        }
                    ],
                },
            },
        )

        result = await amap_regeo(location="120.0,30.0", client=_make_client())
        # community 没有兜底 → None (但 poi_id 仍采纳, 因为 id 格式合规)
        assert result["community"] is None
        assert result["poi_id"] == "B0FFFOOD123"
