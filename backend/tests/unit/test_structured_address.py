"""Unit tests for `app.schemas.structured_address` — Pydantic v2 validation (F051 §3.2).

覆盖:
- 必填字段缺失 → 抛 Pydantic ValidationError
- adcode 正则 (6 位数字)
- poi_id 正则 (8-32 位大写字母+数字 — AMAP 实际 id 长度 8-12 为主)
- 名称字段正则 (中文/字母/数字/空格/·) + 长度 ≤ 32
- door_no 长度 ≤ 64
- cross-field: district 与 district_adcode 必须同生同灭
- is_valid_adcode 工具函数
- 整对象嵌套进 PreferencesUpdate 时, 错误码透传为 `INVALID_STRUCTURED_ADDRESS`
"""
from __future__ import annotations

import pytest
from app.schemas.preferences import PreferencesUpdate
from app.schemas.structured_address import StructuredAddress, is_valid_adcode
from pydantic import ValidationError


def _decode(ve: ValidationError) -> tuple[str, str, str]:
    """解码 Pydantic ValidationError 中的首个 `<CODE>|<message>|<details>`."""
    for error in ve.errors():
        ctx = error.get("ctx") or {}
        raw = ctx.get("error")
        if isinstance(raw, ValueError):
            parts = str(raw).split("|", maxsplit=2)
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]
    raise AssertionError(f"No encoded ValueError found in {ve.errors()}")


# ---------- 最小有效对象 ----------


class TestMinimalValid:
    """仅必填字段 (省 + 市) 即可构造; 其余字段可空."""

    def test_minimal_required_fields_only(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
        )
        assert addr.province == "上海市"
        assert addr.city_adcode == "310100"
        assert addr.district is None
        assert addr.district_adcode is None
        assert addr.community is None
        assert addr.poi_id is None
        assert addr.door_no is None

    def test_full_object_round_trip(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            district="静安区",
            district_adcode="310106",
            street="南京西路",
            community="静安嘉里中心",
            poi_id="B0FFFAB6J2ABCDEFGHIJ",
            door_no="B2 楼 305",
        )
        dumped = addr.model_dump()
        assert dumped["province"] == "上海市"
        assert dumped["poi_id"] == "B0FFFAB6J2ABCDEFGHIJ"
        assert dumped["door_no"] == "B2 楼 305"

    def test_whitespace_stripped(self) -> None:
        addr = StructuredAddress(
            province="  上海市  ",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
        )
        assert addr.province == "上海市"


# ---------- 必填字段缺失 ----------


class TestRequiredFields:
    def test_missing_province_adcode(self) -> None:
        with pytest.raises(ValidationError):
            StructuredAddress(  # type: ignore[call-arg]
                province="上海市",
                city="上海市",
                city_adcode="310100",
            )

    def test_missing_city_adcode(self) -> None:
        with pytest.raises(ValidationError):
            StructuredAddress(  # type: ignore[call-arg]
                province="上海市",
                province_adcode="310000",
                city="上海市",
            )

    def test_empty_province_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuredAddress(
                province="",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
            )


# ---------- adcode 正则 ----------


class TestAdcodePattern:
    @pytest.mark.parametrize("good", ["110000", "310100", "310106", "440100", "999999"])
    def test_valid_adcode_accepted(self, good: str) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode=good,
            city="上海市",
            city_adcode="310100",
        )
        assert addr.province_adcode == good

    @pytest.mark.parametrize("bad", ["11000", "1100000", "abc123", "11 000", "11-000"])
    def test_invalid_adcode_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode=bad,
                city="上海市",
                city_adcode="310100",
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"


# ---------- poi_id 正则 ----------


class TestPoiIdPattern:
    @pytest.mark.parametrize(
        "good",
        [
            "B0I6KCBRAM",  # AMAP 实际风格 (11 位) — F051 §3.2 兼容
            "B0FFGKABCD1234567890",  # 早期长 id (20 位)
            "A" * 8,  # 下边界
            "A" * 20,
            "0" * 32,  # 上边界
            "B0FFFA48PBKB0FFFA48P",  # 20 位混合字母数字
        ],
    )
    def test_valid_poi_id_accepted(self, good: str) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            poi_id=good,
        )
        assert addr.poi_id == good

    @pytest.mark.parametrize(
        "bad",
        [
            "B0FFFAB6J2ABCDEFGHI!",  # 含特殊字符
            "b0fffab6j2abcdefghij",  # 小写字母
            "B0FFFA4",  # 太短 (7 位, < 8 位下限)
            "B" * 33,  # 太长 (33 位)
            "B0FF FAB6J2ABCDEFGHIJ",  # 含空格
        ],
    )
    def test_invalid_poi_id_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                poi_id=bad,
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"


# ---------- 名称字段正则 ----------


class TestNamePattern:
    def test_chinese_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            community="静安嘉里中心",
        )
        assert addr.community == "静安嘉里中心"

    def test_english_accepted(self) -> None:
        addr = StructuredAddress(
            province="北京市",
            province_adcode="110000",
            city="北京市",
            city_adcode="110100",
            community="Beijing CBD Tower",
        )
        assert addr.community == "Beijing CBD Tower"

    def test_middle_dot_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            community="上海·静安嘉里中心",
        )
        assert addr.community == "上海·静安嘉里中心"

    def test_special_char_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                community="国贸三期!",  # 含感叹号
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    def test_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                community="静" * 33,  # 33 字, 超过 32 上限
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    def test_boundary_32_chars_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            community="静" * 32,
        )
        assert len(addr.community or "") == 32


# ---------- door_no 长度 ----------


class TestDoorNoPattern:
    def test_normal_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            door_no="B2 楼 305",
        )
        assert addr.door_no == "B2 楼 305"

    def test_boundary_64_chars_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            door_no="x" * 64,
        )
        assert len(addr.door_no or "") == 64

    def test_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                door_no="x" * 65,
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"


# ---------- 经纬度字段 (F051 §6.4 — regeo 一次性捕获的原始坐标) ----------


class TestCoordFields:
    def test_lng_lat_accepted(self) -> None:
        """F051 §6.4: regeo 返回的 (lng, lat) 直接落库, 供 search_restaurants
        当 place/around 锚点."""
        addr = StructuredAddress(
            province="浙江省",
            province_adcode="330000",
            city="杭州市",
            city_adcode="330100",
            district="钱塘区",
            district_adcode="330114",
            longitude=121.450000,
            latitude=30.230000,
        )
        assert addr.longitude == 121.45
        assert addr.latitude == 30.23

    def test_negative_lng_lat_accepted(self) -> None:
        """西半球 / 南半球坐标 (虽然本项目用不上, 但 schema 允许)."""
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            longitude=-122.4194,  # 旧金山
            latitude=37.7749,
        )
        assert addr.longitude == -122.4194

    def test_boundary_longitude_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            longitude=180.0,
            latitude=90.0,
        )
        assert addr.longitude == 180.0
        assert addr.latitude == 90.0

    def test_lng_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                longitude=181.0,  # 越界
                latitude=30.0,
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    def test_lat_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                longitude=121.0,
                latitude=91.0,  # 越界
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    def test_string_longitude_rejected(self) -> None:
        """防止 schema 校验失效时字符串流入 (Node 端 `_resolve_structured_coord`
        才会发现, 但应在前置 schema 直接拦)."""
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                longitude="121.45",  # type: ignore[arg-type]
                latitude=30.23,
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"


# ---------- cross-field: district / district_adcode 成对 ----------
#                   + longitude / latitude 成对 (F051 §6.4)


class TestDistrictCoupled:
    def test_both_set_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            district="静安区",
            district_adcode="310106",
        )
        assert addr.district == "静安区"
        assert addr.district_adcode == "310106"

    def test_both_none_accepted(self) -> None:
        addr = StructuredAddress(
            province="北京市",
            province_adcode="110000",
            city="北京市",
            city_adcode="110100",
        )
        assert addr.district is None
        assert addr.district_adcode is None

    def test_only_district_set_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                district="静安区",
                # district_adcode 缺省
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    def test_only_district_adcode_set_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                district_adcode="310106",
                # district 缺省
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    # ---- F051 §6.4: longitude / latitude 必须同生同灭 ----

    def test_lng_lat_both_set_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            longitude=121.45,
            latitude=30.23,
        )
        assert addr.longitude == 121.45

    def test_lng_lat_both_none_accepted(self) -> None:
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
        )
        assert addr.longitude is None
        assert addr.latitude is None

    def test_only_longitude_set_rejected(self) -> None:
        """单独一个坐标无法定位, 必须成对."""
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                longitude=121.45,
                # latitude 缺省
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    def test_only_latitude_set_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                latitude=30.23,
                # longitude 缺省
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"


# ---------- 嵌套到 PreferencesUpdate ----------


class TestNestedInPreferencesUpdate:
    def test_structured_address_accepted(self) -> None:
        payload = PreferencesUpdate(
            default_location=StructuredAddress(
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                district="静安区",
                district_adcode="310106",
            )
        )
        assert payload.default_location is not None
        assert payload.default_location.city_adcode == "310100"

    def test_invalid_structured_address_returns_invalid_structured_code(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(
                default_location=StructuredAddress(
                    province="上海市",
                    province_adcode="31000",  # 5 位, 非法
                    city="上海市",
                    city_adcode="310100",
                )
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_STRUCTURED_ADDRESS"

    def test_none_default_location_accepted(self) -> None:
        payload = PreferencesUpdate(default_location=None)
        assert payload.default_location is None

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuredAddress(  # type: ignore[call-arg]
                province="上海市",
                province_adcode="310000",
                city="上海市",
                city_adcode="310100",
                unknown_field="x",
            )


# ---------- is_valid_adcode 工具函数 ----------


class TestIsValidAdcode:
    @pytest.mark.parametrize("good", ["110000", "310100", "440100"])
    def test_valid(self, good: str) -> None:
        assert is_valid_adcode(good) is True

    @pytest.mark.parametrize("bad", ["11000", "1100000", "abc", "11 000", ""])
    def test_invalid(self, bad: str) -> None:
        assert is_valid_adcode(bad) is False

    @pytest.mark.parametrize("non_string", [None, 110000, 110000.0, ["110000"], {"x": 1}])
    def test_non_string(self, non_string: object) -> None:
        assert is_valid_adcode(non_string) is False  # type: ignore[arg-type]

    def test_whitespace_stripped(self) -> None:
        assert is_valid_adcode("  110000  ") is True