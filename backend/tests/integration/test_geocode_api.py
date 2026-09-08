"""End-to-end integration tests for `/api/v1/geocode/regeo` (F051 §5.2).

Drives a real FastAPI TestClient; uses respx to mock the upstream Amap
`/v3/geocode/regeo` HTTP call.

覆盖验收点:
- HTTP 200 + RegeoInfo TypedDict → JSON
- location 必填 (FastAPI Query ...)
- location 必须是 "lng,lat" 格式 (wrapper 校验)
- AMAP_LOCATION_INVALID / AMAP_QUOTA_EXCEEDED 透传
"""
from __future__ import annotations

import httpx
import pytest
import respx
from app.core.user_id import USER_ID_HEADER
from fastapi.testclient import TestClient

_AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"


def _ok_payload(
    province: str = "上海市",
    city: str = "上海市",
    district: str = "静安区",
    adcode: str = "310106",
    lng: str = "121.473701",
    lat: str = "31.230416",
) -> dict[str, object]:
    return {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "regeocodes": [
            {
                "formatted_address": f"{province}{city}{district}南京西路xxx号",
                "addressComponent": {
                    "province": province,
                    "city": city,
                    "district": district,
                    "adcode": adcode,
                },
                "location": f"{lng},{lat}",
            }
        ],
    }


class TestGeocodeRegoHappyPath:
    @respx.mock
    def test_valid_location_returns_regeo(
        self, client: TestClient, random_user_id: str
    ) -> None:
        respx.get(_AMAP_REGEO_URL).mock(
            return_value=httpx.Response(200, json=_ok_payload())
        )

        resp = client.get(
            "/api/v1/geocode/regeo",
            params={"location": "121.473701,31.230416"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["province"] == "上海市"
        assert body["city"] == "上海市"
        assert body["district"] == "静安区"
        assert body["adcode"] == "310106"
        assert body["longitude"] == pytest.approx(121.473701)
        assert body["latitude"] == pytest.approx(31.230416)
        assert "南京西路" in body["formatted_address"]

    @respx.mock
    def test_request_sends_location_param(
        self, client: TestClient, random_user_id: str
    ) -> None:
        respx.get(_AMAP_REGEO_URL).mock(
            return_value=httpx.Response(200, json=_ok_payload())
        )

        resp = client.get(
            "/api/v1/geocode/regeo",
            params={"location": "116.43,39.91"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        sent = dict(respx.calls.last.request.url.params)
        # wrapper 重新格式化为 "lng,lat"
        assert "location" in sent
        assert "extensions" in sent
        assert sent["extensions"] == "base"


class TestGeocodeRegoParamValidation:
    """FastAPI Query 校验 + wrapper ValueError → 400 envelope (`VALIDATION_ERROR`)."""

    def test_missing_location_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/geocode/regeo",
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400
        assert resp.json()["ok"] is False

    def test_invalid_location_format_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """wrapper `_LOCATION_PATTERN` 不匹配 → ValueError → 400 `VALIDATION_ERROR`."""
        resp = client.get(
            "/api/v1/geocode/regeo",
            params={"location": "not-a-coord"},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "lng,lat" in body["error"]["message"]

    def test_out_of_range_longitude_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/geocode/regeo",
            params={"location": "999.0,31.0"},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


class TestGeocodeRegoErrorMapping:
    @respx.mock
    def test_location_invalid_returns_502(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """高德返回空 regeocodes → AmapLocationInvalidError → HTTP 502."""
        respx.get(_AMAP_REGEO_URL).mock(
            return_value=httpx.Response(
                200,
                json={"status": "1", "info": "OK", "infocode": "10000",
                      "regeocodes": []},
            )
        )

        resp = client.get(
            "/api/v1/geocode/regeo",
            params={"location": "121.47,31.23"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 502
        body = resp.json()
        assert body["error"]["code"] == "AMAP_LOCATION_INVALID"

    @respx.mock
    def test_quota_exceeded_returns_429(
        self, client: TestClient, random_user_id: str
    ) -> None:
        respx.get(_AMAP_REGEO_URL).mock(
            return_value=httpx.Response(
                200,
                json={"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
                      "infocode": "10044"},
            )
        )

        resp = client.get(
            "/api/v1/geocode/regeo",
            params={"location": "121.47,31.23"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "AMAP_QUOTA_EXCEEDED"
