"""User preferences Pydantic v2 schemas — HTTP boundary only.

Internal state uses TypedDict in `app/agents/state.py`. Schemas below are
boundary types that validate input / shape output for the API.

Validation rules (F001 §3 + §6):
- `cuisine_weights` keys ∈ `CUISINE_IDS`; values ∈ [0, 1]
- `allergies` elements ∈ `ALLERGY_VALUES`
- `spice_tolerance` ∈ [0, 3]
- `temperature_preference` ∈ {cold, room, hot}
- `budget_lunch_min` ≤ `budget_lunch_max`; both ≥ 0

Validator → envelope mapping
----------------------------
Pydantic v2 only wraps `ValueError` / `AssertionError` / `TypeError` thrown from
`field_validator`. To surface F001's error codes (`INVALID_CUISINE_ID` etc.) in
the response envelope, validators raise `ValueError` whose message is encoded:

    <CODE>|<human message>|<json-encoded details>

`app.core.exceptions._validation_error_handler` parses this back into the
standard envelope. This avoids relying on `__cause__` chaining (which Pydantic
does not preserve) and keeps the DomainError class hierarchy clean.

Note: `Decimal` serializes to JSON as string by default in Pydantic v2 — matches
`spec/api.md` example (`"20.00"`).
"""
from __future__ import annotations

import json
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.core.constants import (
    ALLERGY_VALUES,
    CUISINE_IDS,
    SPICE_TOLERANCE_RANGE,
    TEMPERATURE_VALUES,
)

# ----- Shared bounds -----


_MinSpice, _MaxSpice = SPICE_TOLERANCE_RANGE
_CUISINE_SET = frozenset(CUISINE_IDS)


def _validation_error(code: str, message: str, details: object | None = None) -> ValueError:
    """Build a ValueError whose message encodes the DomainError envelope fields."""
    details_json = "null" if details is None else json.dumps(details, ensure_ascii=False)
    return ValueError(f"{code}|{message}|{details_json}")


class _PreferencesBase(BaseModel):
    """Shared fields + cross-field validators used by both read & update."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cuisine_weights: dict[str, float] = {}
    allergies: list[str] = []
    spice_tolerance: int = 0
    temperature_preference: str = "room"
    default_location: str | None = None
    budget_lunch_min: Decimal | None = None
    budget_lunch_max: Decimal | None = None

    # ----- field validators -----

    @field_validator("cuisine_weights")
    @classmethod
    def _check_cuisine_keys_and_values(cls, v: dict[str, float]) -> dict[str, float]:
        unknown = set(v) - _CUISINE_SET
        if unknown:
            raise _validation_error(
                "INVALID_CUISINE_ID",
                "cuisine_weights 包含未注册的菜系 ID",
                {"unknown": sorted(unknown)},
            )
        for cuisine_id, weight in v.items():
            if not (0.0 <= weight <= 1.0):
                raise _validation_error(
                    "INVALID_CUISINE_ID",
                    f"菜系权重越界: {cuisine_id}={weight}",
                    {"cuisine_id": cuisine_id, "weight": weight},
                )
        return v

    @field_validator("allergies")
    @classmethod
    def _check_allergies(cls, v: list[str]) -> list[str]:
        invalid = [a for a in v if a not in ALLERGY_VALUES]
        if invalid:
            raise _validation_error(
                "INVALID_ALLERGY",
                "allergies 包含未注册的过敏原",
                {"invalid": sorted(invalid)},
            )
        return v

    @field_validator("spice_tolerance")
    @classmethod
    def _check_spice(cls, v: int) -> int:
        if not (_MinSpice <= v <= _MaxSpice):
            raise _validation_error(
                "INVALID_SPICE",
                f"spice_tolerance 越界: {v}",
                {"min": _MinSpice, "max": _MaxSpice},
            )
        return v

    @field_validator("temperature_preference")
    @classmethod
    def _check_temperature(cls, v: str) -> str:
        if v not in TEMPERATURE_VALUES:
            raise _validation_error(
                "INVALID_TEMPERATURE",
                f"temperature_preference 不在枚举内: {v}",
                {"allowed": sorted(TEMPERATURE_VALUES)},
            )
        return v

    @field_validator("budget_lunch_min", "budget_lunch_max")
    @classmethod
    def _check_budget_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise _validation_error(
                "INVALID_BUDGET",
                "预算不能为负数",
                {"value": str(v)},
            )
        return v

    # ----- cross-field -----

    @model_validator(mode="after")
    def _check_budget_range(self) -> _PreferencesBase:
        lo = self.budget_lunch_min
        hi = self.budget_lunch_max
        if lo is not None and hi is not None and lo > hi:
            raise _validation_error(
                "INVALID_BUDGET",
                "budget_lunch_min 不能大于 budget_lunch_max",
                {"min": str(lo), "max": str(hi)},
            )
        return self


class PreferencesUpdate(_PreferencesBase):
    """PUT /api/v1/preferences request body (no user_id — comes from header)."""


class PreferencesRead(_PreferencesBase):
    """GET /api/v1/preferences response payload — includes the resolved user_id."""

    user_id: str


def default_cuisine_weights() -> dict[str, float]:
    """All 14 cuisines at neutral weight 0.5 — used when no record exists yet."""
    return {cuisine: 0.5 for cuisine in CUISINE_IDS}