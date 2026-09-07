"""Unit tests for `app.services.preferences` — uses the MySQL test schema via `db_session`."""
from __future__ import annotations

from decimal import Decimal

from app.core.constants import CUISINE_IDS
from app.schemas.preferences import PreferencesUpdate
from app.services import preferences as svc
from sqlalchemy.orm import Session


class TestLoadPreferences:
    def test_returns_defaults_when_no_row(self, db_session: Session) -> None:
        result = svc.load_preferences(db_session, "ghost-user")

        assert result["user_id"] == "ghost-user"
        assert set(result["cuisine_weights"].keys()) == set(CUISINE_IDS)
        assert all(w == 0.5 for w in result["cuisine_weights"].values())
        assert result["allergies"] == []
        assert result["spice_tolerance"] == 0
        assert result["temperature_preference"] == "room"
        assert result["default_location"] is None
        assert result["budget_lunch_min"] is None
        assert result["budget_lunch_max"] is None

    def test_returns_persisted_after_upsert(self, db_session: Session) -> None:
        payload = PreferencesUpdate(
            cuisine_weights={"sichuan": 0.9, "cantonese": 0.1},
            allergies=["peanut"],
            spice_tolerance=2,
            temperature_preference="hot",
            default_location="国贸三期",
            budget_lunch_min=Decimal("20.00"),
            budget_lunch_max=Decimal("60.00"),
        )
        svc.upsert_preferences(db_session, "user-1", payload)
        # Rollback semantics are handled by the session fixture — flush so the
        # subsequent load sees the same in-flight row.
        db_session.flush()

        loaded = svc.load_preferences(db_session, "user-1")
        assert loaded["cuisine_weights"] == {"sichuan": 0.9, "cantonese": 0.1}
        assert loaded["allergies"] == ["peanut"]
        assert loaded["spice_tolerance"] == 2
        assert loaded["temperature_preference"] == "hot"
        assert loaded["default_location"] == "国贸三期"
        assert loaded["budget_lunch_min"] == Decimal("20.00")
        assert loaded["budget_lunch_max"] == Decimal("60.00")


class TestUpsertPreferences:
    def test_inserts_when_no_row(self, db_session: Session) -> None:
        payload = PreferencesUpdate(spice_tolerance=3)
        result = svc.upsert_preferences(db_session, "new-user", payload)

        assert result["spice_tolerance"] == 3
        # The other fields get overwritten by defaults from the Pydantic model.
        assert result["cuisine_weights"] == {}
        assert result["temperature_preference"] == "room"

    def test_full_overwrite_replaces_existing(self, db_session: Session) -> None:
        first = PreferencesUpdate(spice_tolerance=1, allergies=["peanut"])
        svc.upsert_preferences(db_session, "u", first)
        db_session.flush()

        second = PreferencesUpdate(
            spice_tolerance=3, temperature_preference="cold"
        )
        result = svc.upsert_preferences(db_session, "u", second)
        db_session.flush()

        # Full overwrite: allergies from the first PUT are gone.
        assert result["spice_tolerance"] == 3
        assert result["allergies"] == []
        assert result["temperature_preference"] == "cold"

    def test_upsert_round_trip_preserves_user_id(self, db_session: Session) -> None:
        result = svc.upsert_preferences(
            db_session, "stable-id", PreferencesUpdate()
        )
        assert result["user_id"] == "stable-id"