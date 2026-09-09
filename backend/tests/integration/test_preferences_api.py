"""End-to-end integration tests for `/api/v1/preferences` (F001 + F051).

Drives a real FastAPI TestClient with:
- The `UserIdMiddleware` running (anonymous UUID generation + cookie).
- Exception handlers producing the standard envelope.
- `get_db` overridden to use the MySQL test schema (per-test SAVEPOINT).

F051 升级 (2026-09-08):
- `default_location` 字段类型为 `StructuredAddress | None` (PUT) / dict (GET).
- PUT 校验失败 → 400 `INVALID_STRUCTURED_ADDRESS`.
- 老字符串 `default_location` (F051 升级前数据) → GET 时回填 None,
  不抛 400 (`TestLegacyStringCompat`).
"""
from __future__ import annotations

from app.core.user_id import USER_ID_COOKIE, USER_ID_HEADER
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class TestGetPreferences:
    def test_anonymous_request_returns_defaults_with_uuid_cookie(
        self, client: TestClient
    ) -> None:
        # Act
        resp = client.get("/api/v1/preferences")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["user_id"]  # non-empty UUID string
        assert data["cuisine_weights"]  # at least one entry
        assert data["temperature_preference"] == "room"
        assert data["spice_tolerance"] == 0
        assert data["allergies"] == []
        assert data["default_location"] is None

        set_cookie = resp.headers.get("set-cookie", "")
        assert USER_ID_COOKIE in set_cookie

    def test_explicit_header_overrides_cookie(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # Arrange
        client.get("/api/v1/preferences")  # anonymous → cookie set

        # Act
        resp = client.get(
            "/api/v1/preferences", headers={USER_ID_HEADER: random_user_id}
        )

        # Assert
        assert resp.json()["data"]["user_id"] == random_user_id


class TestPutPreferences:
    def test_full_overwrite_round_trip(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # Act
        put_resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={
                "cuisine_weights": {"sichuan": 0.9, "cantonese": 0.2},
                "allergies": ["peanut", "shellfish"],
                "spice_tolerance": 2,
                "temperature_preference": "hot",
                "default_location": {
                    "province": "上海市",
                    "province_adcode": "310000",
                    "city": "上海市",
                    "city_adcode": "310100",
                    "district": "静安区",
                    "district_adcode": "310106",
                    "community": "静安嘉里中心",
                    "poi_id": "B0FFFAB6J2ABCDEFGHIJ",
                    "door_no": "B2",
                },
                "budget_lunch_min": "20.00",
                "budget_lunch_max": "60.00",
            },
        )

        # Assert: PUT succeeded
        assert put_resp.status_code == 200
        body = put_resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["user_id"] == random_user_id
        assert data["cuisine_weights"]["sichuan"] == 0.9
        assert data["allergies"] == ["peanut", "shellfish"]
        assert data["spice_tolerance"] == 2
        assert data["temperature_preference"] == "hot"
        # default_location 在 GET 时回填为 dict
        assert isinstance(data["default_location"], dict)
        assert data["default_location"]["city_adcode"] == "310100"
        assert data["default_location"]["community"] == "静安嘉里中心"
        # Pydantic serializes Decimal → JSON string.
        assert data["budget_lunch_min"] == "20.00"
        assert data["budget_lunch_max"] == "60.00"

        # Follow-up GET sees the persisted row.
        get_resp = client.get(
            "/api/v1/preferences", headers={USER_ID_HEADER: random_user_id}
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["spice_tolerance"] == 2
        assert get_resp.json()["data"]["cuisine_weights"]["sichuan"] == 0.9
        assert get_resp.json()["data"]["default_location"]["city_adcode"] == "310100"

    def test_put_minimal_payload_uses_defaults_for_missing_fields(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # Act
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={},
        )

        # Assert: defaults
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["cuisine_weights"] == {}  # PUT is full overwrite; empty stays empty
        assert data["temperature_preference"] == "room"
        assert data["default_location"] is None

    def test_put_replaces_previous_values(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # First write
        client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"allergies": ["peanut"], "spice_tolerance": 2},
        )
        # Second write — empty allergies
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"spice_tolerance": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["allergies"] == []
        assert resp.json()["data"]["spice_tolerance"] == 0


class TestErrorEnvelope:
    def test_invalid_cuisine_id_returns_400_with_envelope(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"cuisine_weights": {"not_a_cuisine": 0.5}},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_CUISINE_ID"

    def test_invalid_allergy_returns_400_with_envelope(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"allergies": ["unicorn_meat"]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_ALLERGY"

    def test_invalid_spice_returns_400_with_envelope(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"spice_tolerance": 99},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_SPICE"

    def test_invalid_temperature_returns_400_with_envelope(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"temperature_preference": "lukewarm"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_TEMPERATURE"

    def test_invalid_budget_returns_400_with_envelope(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={
                "budget_lunch_min": "100.00",
                "budget_lunch_max": "50.00",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_BUDGET"

    def test_invalid_structured_address_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={
                "default_location": {
                    "province": "上海市",
                    "province_adcode": "31000",  # 5 位, 非法
                    "city": "上海市",
                    "city_adcode": "310100",
                }
            },
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "INVALID_STRUCTURED_ADDRESS"

    def test_district_without_district_adcode_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # F051 §3.1: district 与 district_adcode 必须成对出现
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={
                "default_location": {
                    "province": "上海市",
                    "province_adcode": "310000",
                    "city": "上海市",
                    "city_adcode": "310100",
                    "district": "静安区",
                    # district_adcode 缺省 → 触发 cross-field 校验
                }
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_STRUCTURED_ADDRESS"

    def test_unknown_field_returns_400_validation_envelope(
        self, client: TestClient, random_user_id: str
    ) -> None:
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"unknown_field": "x"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_get_with_uuid_cookie_round_trips(
        self, client: TestClient
    ) -> None:
        first = client.get("/api/v1/preferences")
        cookie_value = first.cookies.get(USER_ID_COOKIE)
        assert cookie_value

        second = client.get("/api/v1/preferences", cookies={USER_ID_COOKIE: cookie_value})
        assert second.json()["data"]["user_id"] == cookie_value


class TestLegacyStringCompat:
    """F051 §6.5 — DB 老字符串 default_location 自动回填 None (GET 兼容).

    模拟场景: F051 升级期间/之前的用户, DB 中 default_location 列存的是
    字符串 (例如 `"国贸三期"`). 新代码 PUT 必须拒收字符串 (走 INVALID_STRUCTURED_ADDRESS),
    GET 必须回填 None 而非透传字符串.
    """

    def test_put_with_string_default_location_returns_400(
        self, client: TestClient, random_user_id: str
    ) -> None:
        # F051 升级后, PUT 只接受结构化对象; 字符串走 INVALID_STRUCTURED_ADDRESS
        resp = client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={"default_location": "国贸三期"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_STRUCTURED_ADDRESS"

    def test_get_returns_null_for_legacy_string_default_location(
        self, client: TestClient, db_session: Session, random_user_id: str
    ) -> None:
        # Arrange: 写入结构化对象 → 直接 UPDATE 把列改成字符串 → GET 应回填 None
        client.put(
            "/api/v1/preferences",
            headers={USER_ID_HEADER: random_user_id},
            json={
                "default_location": {
                    "province": "上海市",
                    "province_adcode": "310000",
                    "city": "上海市",
                    "city_adcode": "310100",
                }
            },
        )
        # 复用 TestClient 依赖注入所用的同一个 session (per-test SAVEPOINT);
        # 不另开连接, 否则读不到 PUT 写入的行.
        from app.models.user_preference import UserPreference
        from app.services.preferences import _row_id_for_user

        row_id = _row_id_for_user(db_session, random_user_id)
        assert row_id is not None
        row = db_session.get(UserPreference, row_id)
        assert row is not None
        row.default_location = "国贸三期"  # 老数据格式
        db_session.flush()

        # Act: GET
        resp = client.get(
            "/api/v1/preferences", headers={USER_ID_HEADER: random_user_id}
        )

        # Assert: GET 不抛错, default_location 回填 None (前端兜底到 IP 城市)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["default_location"] is None
        # PUT 是 full overwrite; 本次 PUT 只送了 default_location, 其它字段被覆盖为空
        assert data["cuisine_weights"] == {}