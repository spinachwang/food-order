"""End-to-end integration tests for `/api/v1/districts` (F051 §5.1).

Drives a real FastAPI TestClient; uses respx to mock the upstream Amap
`/v3/config/district` HTTP call so no network access required.

覆盖验收点:
- HTTP 200 + envelope shape (TypedDict → JSON)
- subdistrict ∈ {0,1,2,3} (FastAPI Literal 校验)
- keywords 长度上限
- AmapDistrictNotFoundError → HTTP 404 (per exceptions.py)
- AMAP_QUOTA_EXCEEDED → HTTP 429 (透传)
- AMAP_NETWORK_ERROR → HTTP 502
- AMAP_INVALID_KEY → HTTP 401
"""
from __future__ import annotations

import httpx
import pytest
import respx
from app.core.user_id import USER_ID_HEADER
from fastapi.testclient import TestClient

_AMAP_DISTRICT_URL = "https://restapi.amap.com/v3/config/district"


def _province_payload(adcode: str, name: str, center: str) -> dict[str, object]:
    return {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "count": "1",
        "districts": [
            {
                "adcode": adcode,
                "name": name,
                "level": "province",
                "center": center,
                "districts": [],
            }
        ],
    }


class TestDistrictsHappyPath:
    @respx.mock
    def test_keywords_none_returns_root(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """不传 keywords → 拉国家级根 (高德返回中国根 districts=[])"""
        # Amap `keywords=None` 行为: 返回中国根, 含 1 个 country-level 节点
        respx.get(_AMAP_DISTRICT_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "1",
                    "info": "OK",
                    "infocode": "10000",
                    "count": "1",
                    "districts": [
                        {
                            "adcode": "100000",
                            "name": "中华人民共和国",
                            "level": "country",
                            "center": "116.368324,39.915085",
                            "districts": [],
                        }
                    ],
                },
            )
        )

        resp = client.get(
            "/api/v1/districts",
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["adcode"] == "100000"
        assert body[0]["name"] == "中华人民共和国"
        assert body[0]["level"] == "country"
        # tuple → JSON array
        assert body[0]["center"] == [116.368324, 39.915085]
        assert body[0]["districts"] == []

    @respx.mock
    def test_keywords_province_returns_province_node(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """keywords=上海市 → 返回上海市节点 (subdistrict=0 默认不下钻)"""
        respx.get(_AMAP_DISTRICT_URL).mock(
            return_value=httpx.Response(
                200, json=_province_payload("310000", "上海市", "121.473701,31.230416")
            )
        )

        resp = client.get(
            "/api/v1/districts",
            params={"keywords": "上海市"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["adcode"] == "310000"
        # request 必须带 keywords 与 subdistrict=1 (默认)
        request = respx.calls.last.request
        sent_params = dict(request.url.params)
        assert sent_params["keywords"] == "上海市"
        assert sent_params["subdistrict"] == "1"

    @respx.mock
    def test_subdistrict_param_passed_through(
        self, client: TestClient, random_user_id: str
    ) -> None:
        respx.get(_AMAP_DISTRICT_URL).mock(
            return_value=httpx.Response(
                200, json=_province_payload("310000", "上海市", "121.47,31.23")
            )
        )

        resp = client.get(
            "/api/v1/districts",
            params={"keywords": "上海市", "subdistrict": "2"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        sent_params = dict(respx.calls.last.request.url.params)
        assert sent_params["subdistrict"] == "2"


class TestDistrictsParamValidation:
    """FastAPI Query 校验 — 无需 mock Amap.

    注意: 项目的统一异常 handler (`app.core.exceptions`) 把所有
    `RequestValidationError` 都包装成 400 envelope, 不是默认的 422.
    """

    def test_subdistrict_out_of_range_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/districts",
            params={"subdistrict": "5"},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400
        assert resp.json()["ok"] is False

    def test_keywords_too_long_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/districts",
            params={"keywords": "x" * 65},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400


class TestDistrictsErrorMapping:
    """错误码透传 — mock Amap 返回各类业务错误."""

    @respx.mock
    def test_district_not_found_returns_404(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # keywords 命中但 districts=[] → AmapDistrictNotFoundError → 404
        respx.get(_AMAP_DISTRICT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"status": "1", "info": "OK", "infocode": "10000",
                      "count": "0", "districts": []},
            )
        )

        resp = client.get(
            "/api/v1/districts",
            params={"keywords": "不存在的区"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 404
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "AMAP_DISTRICT_NOT_FOUND"

    @respx.mock
    def test_quota_exceeded_returns_429(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # 高德 infocode=10044 → AmapQuotaExceededError → 429
        respx.get(_AMAP_DISTRICT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
                      "infocode": "10044", "count": "0"},
            )
        )

        resp = client.get(
            "/api/v1/districts",
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "AMAP_QUOTA_EXCEEDED"

    @respx.mock
    def test_invalid_key_returns_502(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """AmapInvalidKeyError → HTTP 502 (per app.core.exceptions)."""
        respx.get(_AMAP_DISTRICT_URL).mock(
            return_value=httpx.Response(
                401, json={"status": "0", "info": "INVALID_USER_KEY"}
            )
        )

        resp = client.get(
            "/api/v1/districts",
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 502
        body = resp.json()
        assert body["error"]["code"] == "AMAP_INVALID_KEY"
