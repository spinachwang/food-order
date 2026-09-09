"""F051 §3.1 — `StructuredAddress` Pydantic v2 schema.

用户结构化默认地址，前端选址组件（[F051 §4 AddressPickerDialog](../../features/F051-structured-address.md)）
的最终产出。底层 adcode 由前端从高德 `/config/district` + `place/text` 实时
获取，避免字符串解析回退。

字段约束（F051 §3.2）：

| 字段                  | 约束                                  |
|-----------------------|---------------------------------------|
| `province_adcode`     | 6 位数字 adcode                       |
| `city_adcode`         | 6 位数字 adcode（Amap weather 锚点）  |
| `district_adcode`     | 6 位数字 adcode（Amap place/around）  |
| `poi_id`              | 高德 POI id（`B0FF...` 形式）         |
| `province`/`city`/... | 中文/字母/数字/空格/`·`，长度 ≤ 32    |
| `door_no`             | 任意字符，长度 ≤ 64                   |
| `longitude`/`latitude`| 经度 [-180, 180] / 纬度 [-90, 90]     |
|                       | （Amap place/around 锚点，geolocation 一次性捕获后持久化） |

校验失败时使用与 `preferences.py` 相同的 `<CODE>|<message>|<details-json>`
编码 ValueError，由 [app/core/exceptions.py _request_validation_error_handler]
解码为标准 envelope，HTTP 400。

调用方：被 `app.schemas.preferences._PreferencesBase.default_location` 嵌入，
构成 `PUT /api/v1/preferences` 请求体的核心字段。
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas._validation_error import _validation_error

# ----- 字段约束正则 (F051 §3.2 白名单) -----

# 6 位数字 adcode (省级 / 市级 / 区级共用同一格式)
_ADCODE_PATTERN = re.compile(r"^[0-9]{6}$")
# 高德 POI id (例 "B0I6KCBRAM" / "B0FFGKABCD1234567890"): 8-32 位大写字母+数字
# AMAP 实际 id 长度 8-12 字符为主, 长 id 是早期风格的遗留; 兼容两段历史.
_POI_ID_PATTERN = re.compile(r"^[A-Z0-9]{8,32}$")
# 人类可读字段: 中文 / 字母 / 数字 / 空格 / 中点 `·`
_NAME_PATTERN = re.compile(r"^[一-龥一-鿿A-Za-z0-9 ·]{1,32}$")
# door_no: 任意字符，长度 ≤ 64
_DOOR_NO_MAX = 64
_NAME_MAX = 32
# 经度 / 纬度合法范围 (地理坐标系 WGS-84). 范围严格遵循 GIS 行业惯例,
# 与高德 GCJ-02 坐标系取值范围一致 (中国境内 lng ∈ [73, 135], lat ∈ [3, 53]).
_LNG_MIN, _LNG_MAX = -180.0, 180.0
_LAT_MIN, _LAT_MAX = -90.0, 90.0


class StructuredAddress(BaseModel):
    """F051 §3.1 — 用户结构化默认地址.

    必填字段：`province` / `province_adcode` / `city` / `city_adcode`.
    其他字段（`district` / `district_adcode` / `street` / `community` /
    `poi_id` / `door_no` / `longitude` / `latitude`）可选 — 用户可只选到
    城市级; longitude / latitude 是 regeo 一次性捕获的原始坐标, 供
    search_restaurants 直接当 place/around 锚点, 避免 district_adcode →
    区中心点的精度损失。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # ---- 必填：省级 ----
    province: str
    province_adcode: str

    # ---- 必填：市级（同时是 Amap weather 的查询锚点）----
    city: str
    city_adcode: str

    # ---- 可选：区级（Amap place/around 的查询锚点）----
    district: str | None = None
    district_adcode: str | None = None

    # ---- 可选：街道 / 商圈 / 小区 / 楼宇 ----
    street: str | None = None
    community: str | None = None
    poi_id: str | None = None

    # ---- 可选：门牌号 / 楼层 / 房间号 ----
    door_no: str | None = None

    # ---- 可选：原始经纬度（geolocation 一次性捕获，Amap place/around 锚点）----
    # 来自 regeo 调用的同一坐标 (lng, lat)。持久化后, search_restaurants 直接
    # 用它当 place/around 的 location, 不再走 district_adcode → 区中心点 fallback,
    # 避免「整个区只搜到 1.5km 内 POI」的精度损失。
    longitude: float | None = None
    latitude: float | None = None

    # ----- field validators (F051 §3.2 白名单) -----

    @field_validator("province_adcode", "city_adcode", "district_adcode")
    @classmethod
    def _check_adcode(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _ADCODE_PATTERN.match(v):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                "adcode 必须是 6 位数字",
                {"field_pattern": "^[0-9]{6}$", "value": v},
            )
        return v

    @field_validator("poi_id")
    @classmethod
    def _check_poi_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _POI_ID_PATTERN.match(v):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                "poi_id 必须是 20-32 位大写字母+数字",
                {"field_pattern": "^[A-Z0-9]{20,32}$", "value": v},
            )
        return v

    @field_validator("province", "city", "district", "street", "community")
    @classmethod
    def _check_name_field(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) > _NAME_MAX or not _NAME_PATTERN.match(v):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                f"名称字段长度必须在 1-{_NAME_MAX} 且仅含中文/字母/数字/空格/·",
                {"field_pattern": r"^[一-鿿A-Za-z0-9 ·]{1,32}$", "value": v},
            )
        return v

    @field_validator("door_no")
    @classmethod
    def _check_door_no(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) > _DOOR_NO_MAX:
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                f"door_no 长度必须 ≤ {_DOOR_NO_MAX}",
                {"max_length": _DOOR_NO_MAX, "actual_length": len(v)},
            )
        return v

    @field_validator("longitude", mode="before")
    @classmethod
    def _check_longitude(cls, v: object) -> float | None:
        # mode='before' — 在 Pydantic 自动把 "121.45" 强转 float 之前先拦截,
        # 保证非法类型能直接报错 (而不是先变成 121.45 然后通过范围校验).
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                "longitude 必须是数字",
                {"value_type": type(v).__name__, "value": v},
            )
        v_f = float(v)
        if not (_LNG_MIN <= v_f <= _LNG_MAX):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                f"longitude 必须在 [{_LNG_MIN}, {_LNG_MAX}], 实际={v_f}",
                {"min": _LNG_MIN, "max": _LNG_MAX, "value": v_f},
            )
        return v_f

    @field_validator("latitude", mode="before")
    @classmethod
    def _check_latitude(cls, v: object) -> float | None:
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                "latitude 必须是数字",
                {"value_type": type(v).__name__, "value": v},
            )
        v_f = float(v)
        if not (_LAT_MIN <= v_f <= _LAT_MAX):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                f"latitude 必须在 [{_LAT_MIN}, {_LAT_MAX}], 实际={v_f}",
                {"min": _LAT_MIN, "max": _LAT_MAX, "value": v_f},
            )
        return v_f

    # ----- cross-field：district / district_adcode 必须成对出现（F051 §3.1）-----
    #           + longitude / latitude 必须同生同灭（高精度锚点单独使用无意义）

    def model_post_init(self, __context: object) -> None:
        """district 与 district_adcode 必须同生同灭 — 任一非空则另一个必非空.
        longitude / latitude 同样: 单独一个坐标无法定位, 必须成对.
        """
        district, district_adcode = self.district, self.district_adcode
        if (district is None) != (district_adcode is None):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                "district 与 district_adcode 必须同时设置或同时为空",
                {
                    "district": district,
                    "district_adcode": district_adcode,
                },
            )
        if (self.longitude is None) != (self.latitude is None):
            raise _validation_error(
                "INVALID_STRUCTURED_ADDRESS",
                "longitude 与 latitude 必须同时设置或同时为空",
                {
                    "longitude": self.longitude,
                    "latitude": self.latitude,
                },
            )


def is_valid_adcode(value: str | None) -> bool:
    """便捷判断：value 是否是 6 位数字 adcode.

    给 Node 层（fetch_weather / search_restaurants）使用，避免重新
    引入正则 import。
    """
    if not isinstance(value, str):
        return False
    return bool(_ADCODE_PATTERN.match(value.strip()))


__all__ = ["StructuredAddress", "is_valid_adcode"]