"""Integration test: F002 router can consume a real `UserPreferencesDict`
loaded via `load_preferences` and produce a `selected_cuisines` list that
every downstream cuisine expert can resolve from `CUISINE_REGISTRY`.

This is the F002 §7 "integration" coverage — proves the chain holds end-to-end
on a real DB session. Requires MySQL test schema up.
"""
from __future__ import annotations

import asyncio
import random
from decimal import Decimal
from typing import Any

import pytest
from app.agents.cuisines import CUISINE_REGISTRY
from app.agents.llm.testing import FakeLLMProvider
from app.agents.main_router import route_cuisines
from app.agents.state import AgentState
from app.core.constants import CUISINE_IDS, NEUTRAL_CUISINE_WEIGHT
from app.services.preferences import load_preferences, upsert_preferences
from app.schemas.preferences import PreferencesUpdate
from fastapi.testclient import TestClient


def _state_with_prefs(message: str, prefs: Any) -> AgentState:
    return {
        "user_id": "u-test",
        "user_message": message,
        "user_preferences": prefs,
    }


class TestRoutingEndToEnd:
    def test_rule_layer_with_real_preferences(
        self, client: TestClient, random_user_id: str, db_session: Any
    ) -> None:
        # Arrange — write a real preferences row with peanut allergy + sichuan high weight.
        upsert_preferences(
            db_session,
            random_user_id,
            PreferencesUpdate(
                cuisine_weights={"sichuan": 1.0, "cantonese": 0.5, "hunan": 0.5},
                allergies=["peanut"],
                spice_tolerance=2,
                temperature_preference="room",
                default_location="国贸",
                budget_lunch_min=Decimal("30.00"),
                budget_lunch_max=Decimal("80.00"),
            ),
        )
        prefs = load_preferences(db_session, random_user_id)

        # Act — rule layer must NOT trigger LLM, must drop sichuan (peanut).
        provider = FakeLLMProvider()
        out = asyncio.run(
            route_cuisines(
                _state_with_prefs("想吃辣的", prefs),
                provider=provider,
                rng=random.Random(0),
            )
        )

        # Assert
        assert provider.calls == []
        assert "sichuan" not in out["selected_cuisines"]
        assert "hunan" in out["selected_cuisines"]
        # Every selected id resolves to a real expert downstream can run.
        for cuisine_id in out["selected_cuisines"]:
            assert cuisine_id in CUISINE_REGISTRY, (
                f"{cuisine_id} is not in CUISINE_REGISTRY — downstream will crash"
            )

    def test_llm_fallback_with_real_preferences(
        self, client: TestClient, random_user_id: str, db_session: Any
    ) -> None:
        # Arrange — neutral preferences; LLM will be hit because no rule fires.
        prefs = load_preferences(db_session, random_user_id)

        provider = FakeLLMProvider()
        # Program the LLM to return two cuisines that ARE in the registry.
        provider.set_response(  # type: ignore[arg-type]
            {
                "content": (
                    '{"selected_cuisines": ["suzhou", "japanese"], '
                    '"routing_reason": "清淡口 → 苏 + 日"}'
                ),
                "model": "fake-model",
                "usage": None,
            }
        )

        # Act
        out = asyncio.run(
            route_cuisines(
                _state_with_prefs("想吃点清淡的", prefs),
                provider=provider,
                rng=random.Random(0),
            )
        )

        # Assert
        assert provider.calls, "gray-zone phrase must hit the LLM"
        assert set(out["selected_cuisines"]) == {"suzhou", "japanese"}
        for cuisine_id in out["selected_cuisines"]:
            assert cuisine_id in CUISINE_REGISTRY

    def test_neutral_weights_when_no_row_exists(
        self, client: TestClient, random_user_id: str, db_session: Any
    ) -> None:
        # Arrange — no row → defaults (all 14 cuisines at NEUTRAL_CUISINE_WEIGHT).
        prefs = load_preferences(db_session, random_user_id)
        assert all(
            w == NEUTRAL_CUISINE_WEIGHT for w in prefs["cuisine_weights"].values()
        )
        # Sample 1 cuisine to keep the test deterministic.
        sample = next(iter(prefs["cuisine_weights"]))
        assert sample in CUISINE_IDS
