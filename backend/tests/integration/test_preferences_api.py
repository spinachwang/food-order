"""End-to-end integration tests for `/api/v1/preferences` (F001).

Drives a real FastAPI TestClient with:
- The `UserIdMiddleware` running (anonymous UUID generation + cookie).
- Exception handlers producing the standard envelope.
- `get_db` overridden to use the MySQL test schema (per-test SAVEPOINT).
"""
from __future__ import annotations

from app.core.user_id import USER_ID_COOKIE, USER_ID_HEADER
from fastapi.testclient import TestClient


class TestGetPreferences:
    def test_anonymous_request_returns_defaults_with_uuid_cookie(
        self, client: TestClient
    ) -> None:
        # Act
        resp = client.get("/api/v1/preferences")

        # Assert
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"]  # non-empty UUID string
        assert body["cuisine_weights"]  # at least one entry
        assert body["temperature_preference"] == "room"
        assert body["spice_tolerance"] == 0
        assert body["allergies"] == []

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
        assert resp.json()["user_id"] == random_user_id


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
                "default_location": "国贸三期",
                "budget_lunch_min": "20.00",
                "budget_lunch_max": "60.00",
            },
        )

        # Assert: PUT succeeded
        assert put_resp.status_code == 200
        body = put_resp.json()
        assert body["user_id"] == random_user_id
        assert body["cuisine_weights"]["sichuan"] == 0.9
        assert body["allergies"] == ["peanut", "shellfish"]
        assert body["spice_tolerance"] == 2
        assert body["temperature_preference"] == "hot"
        assert body["default_location"] == "国贸三期"
        # Pydantic serializes Decimal → JSON string.
        assert body["budget_lunch_min"] == "20.00"
        assert body["budget_lunch_max"] == "60.00"

        # Follow-up GET sees the persisted row.
        get_resp = client.get(
            "/api/v1/preferences", headers={USER_ID_HEADER: random_user_id}
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["spice_tolerance"] == 2
        assert get_resp.json()["cuisine_weights"]["sichuan"] == 0.9

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
        assert body["cuisine_weights"] == {}  # PUT is full overwrite; empty stays empty
        assert body["temperature_preference"] == "room"

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
        assert resp.json()["allergies"] == []
        assert resp.json()["spice_tolerance"] == 0


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
        assert second.json()["user_id"] == cookie_value