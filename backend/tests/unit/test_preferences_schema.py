"""Unit tests for `app.schemas.preferences` — Pydantic v2 validation rules.

Pydantic v2 only wraps `ValueError` / `AssertionError` / `TypeError` raised from
`field_validator`. The validators in `preferences.py` raise `ValueError` whose
message is encoded `<CODE>|<message>|<details-json>`; the envelope handler
decodes this at the HTTP boundary. Tests assert against that encoding.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.constants import CUISINE_IDS
from app.schemas.preferences import PreferencesUpdate, default_cuisine_weights
from pydantic import ValidationError


def _decode(ve: ValidationError) -> tuple[str, str, str]:
    """Extract (code, message, details_json) from the first ValueError inside the ValidationError."""
    for error in ve.errors():
        ctx = error.get("ctx") or {}
        raw = ctx.get("error")
        if isinstance(raw, ValueError):
            parts = str(raw).split("|", maxsplit=2)
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]
    raise AssertionError(f"No encoded ValueError found in {ve.errors()}")


class TestDefaults:
    def test_default_cuisine_weights_is_neutral(self) -> None:
        weights = default_cuisine_weights()
        assert len(weights) == len(CUISINE_IDS)
        assert all(w == 0.5 for w in weights.values())

    def test_update_model_defaults(self) -> None:
        payload = PreferencesUpdate()
        assert payload.cuisine_weights == {}
        assert payload.allergies == []
        assert payload.spice_tolerance == 0
        assert payload.temperature_preference == "room"
        assert payload.budget_lunch_min is None
        assert payload.budget_lunch_max is None


class TestCuisineWeights:
    def test_unknown_cuisine_id_raises_invalid_cuisine(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(cuisine_weights={"unknown_cuisine": 0.5})
        code, _message, details = _decode(exc.value)
        assert code == "INVALID_CUISINE_ID"
        assert "unknown_cuisine" in details

    def test_weight_out_of_range_raises_invalid_cuisine(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(cuisine_weights={"sichuan": 1.5})
        code, _message, _details = _decode(exc.value)
        assert code == "INVALID_CUISINE_ID"

    def test_negative_weight_raises_invalid_cuisine(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(cuisine_weights={"sichuan": -0.1})
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_CUISINE_ID"

    def test_boundary_values_accepted(self) -> None:
        payload = PreferencesUpdate(cuisine_weights={"sichuan": 0.0, "cantonese": 1.0})
        assert payload.cuisine_weights["sichuan"] == 0.0
        assert payload.cuisine_weights["cantonese"] == 1.0


class TestAllergies:
    def test_unknown_allergy_raises_invalid_allergy(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(allergies=["unicorn_meat"])
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_ALLERGY"

    def test_known_allergies_accepted(self) -> None:
        payload = PreferencesUpdate(allergies=["peanut", "shellfish"])
        assert payload.allergies == ["peanut", "shellfish"]


class TestSpiceTolerance:
    def test_above_max_raises_invalid_spice(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(spice_tolerance=4)
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_SPICE"

    def test_below_min_raises_invalid_spice(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(spice_tolerance=-1)
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_SPICE"


class TestTemperature:
    def test_unknown_temperature_raises_invalid_temperature(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(temperature_preference="warm")
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_TEMPERATURE"

    def test_all_three_values_accepted(self) -> None:
        for v in ("cold", "room", "hot"):
            assert PreferencesUpdate(temperature_preference=v).temperature_preference == v


class TestBudget:
    def test_negative_min_raises_invalid_budget(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(budget_lunch_min=Decimal("-1"))
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_BUDGET"

    def test_negative_max_raises_invalid_budget(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(budget_lunch_max=Decimal("-1"))
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_BUDGET"

    def test_min_greater_than_max_raises_invalid_budget(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PreferencesUpdate(
                budget_lunch_min=Decimal("80.00"), budget_lunch_max=Decimal("40.00")
            )
        code, _, _ = _decode(exc.value)
        assert code == "INVALID_BUDGET"

    def test_min_equals_max_accepted(self) -> None:
        payload = PreferencesUpdate(
            budget_lunch_min=Decimal("50.00"), budget_lunch_max=Decimal("50.00")
        )
        assert payload.budget_lunch_min == payload.budget_lunch_max == Decimal("50.00")


class TestExtraFieldsRejected:
    def test_unknown_field_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            PreferencesUpdate(unknown_field="x")  # type: ignore[call-arg]