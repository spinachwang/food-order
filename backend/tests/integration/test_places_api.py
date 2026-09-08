"""End-to-end integration tests for `/api/v1/places/search` (F051 §5.3).

Drives a real FastAPI TestClient; uses respx to mock the upstream Amap
`/v3/place/text` HTTP call.

覆盖验收点:
- HTTP 200 + TypedDict envelope (`pois` + `count`)
- keywords 必填 (FastAPI Query ... → 缺则 422)
- keywords/types/city 长度上限
- offset ∈ [1, 25]
- city 限定时, request 带 citylimit=true (wrapper 行为)
- AMAP_QUOTA_EXCEEDED / AMAP_LOCATION_INVALID 透传
"""
from __future__ import annotations

import httpx
import pytest
import respx
from app.core.user_id import USER_ID_HEADER
from fastapi.testclient import TestClient

_AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"


def _poi(poi_id: str, name: str, location: str = "121.45,31.23") -> dict[str, object]:
    return {
        "id": poi_id,
        "name": name,
        "address": "上海市静安区南京西路xxx号",
        "type": "商务住宅;楼宇",
        "location": location,
    }


def _ok_payload(pois: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "count": str(len(pois)),
        "pois": pois,
    }


class TestPlacesSearchHappyPath:
    @respx.mock
    def test_keywords_only_returns_national(
        self, client: TestClient, random_user_id: str
    ) -> None:
        respx.get(_AMAP_PLACE_TEXT_URL).mock(
            return_value=httpx.Response(
                200, json=_ok_payload([_poi("B0FFFAB6J2ABCDEFGHIJ", "静安嘉里中心")])
            )
        )

        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "静安嘉里中心"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert len(body["pois"]) == 1
        first = body["pois"][0]
        assert first["poi_id"] == "B0FFFAB6J2ABCDEFGHIJ"
        assert first["name"] == "静安嘉里中心"
        # tuple → JSON array
        assert first["location"] == [121.45, 31.23]
        # types 缺省 = "050000" (餐饮服务大类), city 缺省 → 无 citylimit
        sent = dict(respx.calls.last.request.url.params)
        assert sent["keywords"] == "静安嘉里中心"
        assert sent["types"] == "050000"
        assert sent["offset"] == "10"
        assert "city" not in sent
        assert "citylimit" not in sent

    @respx.mock
    def test_city_param_adds_citylimit(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """city 限定时 wrapper 自动加 citylimit=true (强制只在 city 内匹配)"""
        respx.get(_AMAP_PLACE_TEXT_URL).mock(
            return_value=httpx.Response(200, json=_ok_payload([]))
        )

        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "南京西路", "city": "310100", "types": "商圈"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        sent = dict(respx.calls.last.request.url.params)
        assert sent["city"] == "310100"
        assert sent["citylimit"] == "true"
        assert sent["types"] == "商圈"

    @respx.mock
    def test_offset_passed_through(
        self, client: TestClient, random_user_id: str
    ) -> None:
        respx.get(_AMAP_PLACE_TEXT_URL).mock(
            return_value=httpx.Response(200, json=_ok_payload([]))
        )

        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "x", "offset": "25"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        sent = dict(respx.calls.last.request.url.params)
        assert sent["offset"] == "25"

    @respx.mock
    def test_empty_result_returns_envelope_not_404(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """F051 §5.3: count=0 → pois=[], 不抛错 (与 F030 一致)"""
        respx.get(_AMAP_PLACE_TEXT_URL).mock(
            return_value=httpx.Response(200, json=_ok_payload([]))
        )

        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "不存在的POI"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["pois"] == []
        assert body["count"] == 0


class TestPlacesSearchParamValidation:
    """FastAPI Query 校验 — 400 envelope (per project unified handler)."""

    def test_missing_keywords_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/places/search",
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400

    def test_empty_keywords_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        """min_length=1 强制 keywords 非空."""
        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": ""},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400

    def test_keywords_too_long_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "x" * 65},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400

    def test_offset_too_small_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "x", "offset": "0"},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400

    def test_offset_too_large_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "x", "offset": "26"},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400

    def test_types_too_long_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "x", "types": "t" * 65},
            headers={USER_ID_HEADER: random_user_id},
        )
        assert resp.status_code == 400


class TestPlacesSearchErrorMapping:
    @respx.mock
    def test_quota_exceeded_returns_429(
        self, client: TestClient, random_user_id: str
    ) -> None:
        respx.get(_AMAP_PLACE_TEXT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
                      "infocode": "10044"},
            )
        )

        resp = client.get(
            "/api/v1/places/search",
            params={"keywords": "x"},
            headers={USER_ID_HEADER: random_user_id},
        )

        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "AMAP_QUOTA_EXCEEDED"
