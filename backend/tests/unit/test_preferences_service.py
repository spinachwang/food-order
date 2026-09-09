"""Unit tests for `app.services.preferences` — uses the MySQL test schema via `db_session`.

F051 升级 (2026-09-08): `default_location` 字段为 `StructuredAddress | None`
(DB 列 `JSON`). 老字符串数据由 `_coerce_default_location` 兼容回填 None
(见 `TestLegacyStringCompat`).
"""
from __future__ import annotations

from decimal import Decimal

from app.core.constants import CUISINE_IDS
from app.schemas.preferences import PreferencesUpdate
from app.schemas.structured_address import StructuredAddress
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
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
            district="静安区",
            district_adcode="310106",
            community="静安嘉里中心",
            poi_id="B0FFFAB6J2ABCDEFGHIJ",
        )
        payload = PreferencesUpdate(
            cuisine_weights={"sichuan": 0.9, "cantonese": 0.1},
            allergies=["peanut"],
            spice_tolerance=2,
            temperature_preference="hot",
            default_location=addr,
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
        assert loaded["default_location"] is not None
        assert loaded["default_location"]["city_adcode"] == "310100"
        assert loaded["default_location"]["community"] == "静安嘉里中心"
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
        assert result["default_location"] is None

    def test_full_overwrite_replaces_existing(self, db_session: Session) -> None:
        first_addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
        )
        first = PreferencesUpdate(
            spice_tolerance=1,
            allergies=["peanut"],
            default_location=first_addr,
        )
        svc.upsert_preferences(db_session, "u", first)
        db_session.flush()

        second = PreferencesUpdate(
            spice_tolerance=3, temperature_preference="cold"
        )
        result = svc.upsert_preferences(db_session, "u", second)
        db_session.flush()

        # Full overwrite: allergies from the first PUT are gone; default_location 已被清空
        assert result["spice_tolerance"] == 3
        assert result["allergies"] == []
        assert result["temperature_preference"] == "cold"
        assert result["default_location"] is None

    def test_upsert_round_trip_preserves_user_id(self, db_session: Session) -> None:
        result = svc.upsert_preferences(
            db_session, "stable-id", PreferencesUpdate()
        )
        assert result["user_id"] == "stable-id"


class TestLegacyStringCompat:
    """F051 §6.5 — 老字符串 default_location 在 GET 时回填 None (前端兜底到 IP 城市).

    模拟场景: 数据库里 default_location 是字符串 (F051 升级前的数据).
    """

    def test_legacy_string_default_location_coerced_to_none(
        self, db_session: Session
    ) -> None:
        # Arrange: 先用新 schema 写入一行, 然后手动把 default_location 列
        # 改写成老字符串格式 (模拟 F051 升级前/迁移期间的数据)
        addr = StructuredAddress(
            province="上海市",
            province_adcode="310000",
            city="上海市",
            city_adcode="310100",
        )
        payload = PreferencesUpdate(default_location=addr)
        svc.upsert_preferences(db_session, "legacy-user", payload)
        db_session.flush()

        # 模拟老数据: 直接 UPDATE 把 JSON 列写成字符串
        from app.models.user_preference import UserPreference

        row = db_session.get(UserPreference, svc._row_id_for_user(db_session, "legacy-user"))
        assert row is not None
        # MySQL JSON 列写入字符串 → 实际存储为 JSON 字符串 (quoted string)
        # 我们通过 Python 端设置 str 模拟 ORM 读到的"字符串老数据"场景
        row.default_location = "国贸三期"
        db_session.flush()

        # Act: load_preferences 应回填 None, 不抛错
        loaded = svc.load_preferences(db_session, "legacy-user")

        # Assert
        assert loaded["default_location"] is None

    def test_none_default_location_returns_none(self, db_session: Session) -> None:
        payload = PreferencesUpdate(default_location=None)
        svc.upsert_preferences(db_session, "null-user", payload)
        db_session.flush()

        loaded = svc.load_preferences(db_session, "null-user")
        assert loaded["default_location"] is None