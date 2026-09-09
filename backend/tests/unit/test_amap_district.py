"""F051 — 高德 /config/district Tool 单测.

覆盖 [spec/features/F051-structured-address.md §5.1 / §9] 验收点:

- keywords 不传 → 拉省级列表 (mock 返回 34 条 → 全部解析)
- keywords="上海市" subdistrict=1 → 返回上海市下辖区列表
- keywords="上海市" subdistrict=2 → 多下钻一级
- 解析空 center / 缺 adcode → 丢弃该项, 不抛错
- mock 网络超时 → 重试 1 次后抛 `AmapNetworkError`
- mock 401 → 抛 `AmapInvalidKeyError`
- mock keywords 命中但空结果 → 抛 `AmapDistrictNotFoundError`
- subdistrict / keywords 越界 → 抛 `ValueError`
"""
from __future__ import annotations

import httpx
import pytest
import respx
from app.core.exceptions import (
    AmapDistrictNotFoundError,
    AmapInvalidKeyError,
    AmapNetworkError,
    AmapQuotaExceededError,
)
from app.mcp.amap.client import AmapClient
from app.mcp.amap.district import amap_get_district

_AMAP_URL = "https://restapi.amap.com/v3/config/district"


def _make_client(**overrides: object) -> AmapClient:
    defaults: dict[str, object] = {
        "api_key": "test-amap-key",
        "timeout_seconds": 0.5,
        "max_retries": 1,
        "base_url": "https://restapi.amap.com",
    }
    defaults.update(overrides)
    return AmapClient(**defaults)  # type: ignore[arg-type]


def _mock_response(respx_mock: respx.MockRouter, payload: dict[str, object]) -> None:
    respx_mock.get(_AMAP_URL).mock(return_value=httpx.Response(200, json=payload))


def _mock_error_response(
    respx_mock: respx.MockRouter,
    *,
    status: int,
    body: dict[str, object] | None = None,
) -> None:
    respx_mock.get(_AMAP_URL).mock(
        return_value=httpx.Response(status, json=body or {})
    )


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


class TestAmapGetDistrictHappy:
    @pytest.mark.asyncio
    async def test_keywords_none_returns_province_list(self, respx_mock: respx.MockRouter) -> None:
        # 高德缺省: keywords 不传 → 返回"中国"根节点, subdistrict=1 拿 34 省级单位
        # wrapper 在 subdistrict>=1 时会展开 matched node 的子级, 所以 result
        # 直接是省级列表 (而非 country 节点).
        _mock_response(
            respx_mock,
            {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "districts": [
                    {
                        "adcode": "100000",
                        "name": "中华人民共和国",
                        "level": "country",
                        "center": "116.407394,39.904211",
                        "districts": [
                            {
                                "adcode": "110000",
                                "name": "北京市",
                                "level": "province",
                                "center": "116.407394,39.904211",
                                "districts": [],
                            },
                            {
                                "adcode": "310000",
                                "name": "上海市",
                                "level": "province",
                                "center": "121.473701,31.230416",
                                "districts": [],
                            },
                        ],
                    }
                ],
            },
        )

        result = await amap_get_district(client=_make_client())

        # 展开后顶层是省级, 而不是 country 节点
        assert len(result) == 2
        assert result[0]["name"] == "北京市"
        assert result[0]["level"] == "province"
        assert result[1]["name"] == "上海市"

    @pytest.mark.asyncio
    async def test_keywords_city_returns_districts(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock_response(
            respx_mock,
            {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "districts": [
                    {
                        "adcode": "310100",
                        "name": "上海市",
                        "level": "city",
                        "center": "121.473701,31.230416",
                        "districts": [
                            {
                                "adcode": "310106",
                                "name": "静安区",
                                "level": "district",
                                "center": "121.448380,31.228000",
                                "districts": [],
                            },
                            {
                                "adcode": "310101",
                                "name": "黄浦区",
                                "level": "district",
                                "center": "121.484270,31.231410",
                                "districts": [],
                            },
                        ],
                    }
                ],
            },
        )

        result = await amap_get_district(
            keywords="上海市", subdistrict=1, client=_make_client()
        )

        # subdistrict=1 → 展开 matched node 的子级 → 顶层是区级
        assert len(result) == 2
        assert result[0]["name"] == "静安区"
        assert result[0]["level"] == "district"
        assert result[0]["center"] == (121.448380, 31.228000)
        assert result[1]["name"] == "黄浦区"

    @pytest.mark.asyncio
    async def test_subdistrict_three_drills_down_to_street(
        self, respx_mock: respx.MockRouter
    ) -> None:
        # subdistrict=3: keywords='上海市' → 区 → 街道; wrapper 会展开两级,
        # 最终顶层是街道节点 (matched node = 区, .districts = [街道])
        _mock_response(
            respx_mock,
            {
                "status": "1",
                "districts": [
                    {
                        "adcode": "310106",
                        "name": "静安区",
                        "level": "district",
                        "center": "121.448380,31.228000",
                        "districts": [
                            {
                                "adcode": "310106001",
                                "name": "南京西路街道",
                                "level": "street",
                                "center": "121.457000,31.229000",
                                "districts": [],
                            }
                        ],
                    }
                ],
            },
        )

        result = await amap_get_district(
            keywords="上海市", subdistrict=3, client=_make_client()
        )

        # 单层展开: result = [街道], 因为 matched node 是区, 区.districts = [街道]
        assert len(result) == 1
        street = result[0]
        assert street["level"] == "street"
        assert street["name"] == "南京西路街道"

    @pytest.mark.asyncio
    async def test_subdistrict_zero_keeps_matched_node(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """F030 — adcode 反查坐标走 subdistrict=0 路径, 必须保留 matched node 自身."""
        _mock_response(
            respx_mock,
            {
                "status": "1",
                "districts": [
                    {
                        "adcode": "310101",
                        "name": "黄浦区",
                        "level": "district",
                        "center": "121.484270,31.231410",
                        "districts": [
                            {"adcode": "310101001", "name": "南京东路街道",
                             "level": "street", "center": "0,0", "districts": []},
                        ],
                    }
                ],
            },
        )

        result = await amap_get_district(
            keywords="310101", subdistrict=0, client=_make_client()
        )

        assert len(result) == 1
        matched = result[0]
        assert matched["adcode"] == "310101"
        assert matched["level"] == "district"
        # 关键: matched node 的 center 是顶层 (供 adcode → coord 用)
        assert matched["center"] == (121.484270, 31.231410)
        # 子级原样保留, 但调用方在 subdistrict=0 路径不读它
        assert len(matched["districts"]) == 1


# ---------------------------------------------------------------------------
# 解析容错
# ---------------------------------------------------------------------------


class TestAmapGetDistrictParsing:
    @pytest.mark.asyncio
    async def test_missing_center_defaults_to_zero(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock_response(
            respx_mock,
            {
                "status": "1",
                "districts": [
                    {
                        "adcode": "310000",
                        "name": "上海市",
                        "level": "province",
                        # center 字段缺失
                        "districts": [],
                    }
                ],
            },
        )

        # subdistrict=0 跳过 unwrap, 保留 matched node 自身, 方便测试字段解析
        result = await amap_get_district(subdistrict=0, client=_make_client())

        assert result[0]["center"] == (0.0, 0.0)

    @pytest.mark.asyncio
    async def test_item_missing_adcode_is_dropped(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock_response(
            respx_mock,
            {
                "status": "1",
                "districts": [
                    {"name": "无名省", "level": "province"},  # 缺 adcode → 丢弃
                    {
                        "adcode": "310000",
                        "name": "上海市",
                        "level": "province",
                        "center": "121.473701,31.230416",
                        "districts": [],
                    },
                ],
            },
        )

        # subdistrict=0 跳过 unwrap, 直接验证字段解析 (而非级联结果)
        result = await amap_get_district(subdistrict=0, client=_make_client())

        assert len(result) == 1
        assert result[0]["name"] == "上海市"

    @pytest.mark.asyncio
    async def test_unknown_level_falls_back_to_district(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock_response(
            respx_mock,
            {
                "status": "1",
                "districts": [
                    {
                        "adcode": "999999",
                        "name": "未来行政区",
                        "level": "unknown_future_level",
                        "center": "0.0,0.0",
                        "districts": [],
                    }
                ],
            },
        )

        # subdistrict=0 跳过 unwrap, 验证 level 字段回退
        result = await amap_get_district(subdistrict=0, client=_make_client())

        assert result[0]["level"] == "district"


# ---------------------------------------------------------------------------
# 错误码
# ---------------------------------------------------------------------------


class TestAmapGetDistrictErrors:
    @pytest.mark.asyncio
    async def test_keywords_miss_raises_district_not_found(
        self, respx_mock: respx.MockRouter
    ) -> None:
        # 高德在 keywords 未命中时通常返回 status=1 + 空 districts
        _mock_response(
            respx_mock,
            {"status": "1", "info": "OK", "infocode": "10000", "districts": []},
        )

        with pytest.raises(AmapDistrictNotFoundError) as exc:
            await amap_get_district(
                keywords="火星殖民地", client=_make_client()
            )
        assert exc.value.code == "AMAP_DISTRICT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_network_timeout_raises_amap_network_error(
        self, respx_mock: respx.MockRouter
    ) -> None:
        respx_mock.get(_AMAP_URL).mock(side_effect=httpx.TimeoutException("timeout"))

        with pytest.raises(AmapNetworkError):
            await amap_get_district(client=_make_client())

    @pytest.mark.asyncio
    async def test_unauthorized_raises_invalid_key(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock_error_response(respx_mock, status=401)

        with pytest.raises(AmapInvalidKeyError):
            await amap_get_district(client=_make_client())

    @pytest.mark.asyncio
    async def test_quota_exceeded_body_raises_quota(
        self, respx_mock: respx.MockRouter
    ) -> None:
        _mock_response(
            respx_mock,
            {
                "status": "0",
                "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
                "infocode": "10044",
                "districts": [],
            },
        )

        with pytest.raises(AmapQuotaExceededError):
            await amap_get_district(client=_make_client())


# ---------------------------------------------------------------------------
# 入参校验
# ---------------------------------------------------------------------------


class TestAmapGetDistrictValidation:
    @pytest.mark.asyncio
    async def test_subdistrict_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="subdistrict"):
            await amap_get_district(
                subdistrict=4,  # type: ignore[arg-type]
                client=_make_client(),
            )

    @pytest.mark.asyncio
    async def test_keywords_too_long(self) -> None:
        with pytest.raises(ValueError, match="keywords"):
            await amap_get_district(
                keywords="x" * 100, client=_make_client()
            )
