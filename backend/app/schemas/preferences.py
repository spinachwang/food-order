"""User preferences Pydantic v2 schemas — HTTP boundary only.

Internal state uses TypedDict in `app/agents/state.py`. Schemas below are
boundary types that validate input / shape output for the API.

Validation rules (F001 §3 + §6, F051 §3.1/§3.2):
- `cuisine_weights` keys ∈ `CUISINE_IDS`; values ∈ [0, 1]
- `allergies` elements ∈ `ALLERGY_VALUES`
- `spice_tolerance` ∈ [0, 3]
- `temperature_preference` ∈ {cold, room, hot}
- `budget_lunch_min` ≤ `budget_lunch_max`; both ≥ 0
- `default_location` ∈ `StructuredAddress` | None (F051 §3.1 — 升级自 str | None)

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

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.core.constants import (
    ALLERGY_VALUES,
    CUISINE_IDS,
    NEUTRAL_CUISINE_WEIGHT,
    SPICE_TOLERANCE_RANGE,
    TEMPERATURE_VALUES,
)
from app.schemas._validation_error import _validation_error
from app.schemas.structured_address import StructuredAddress

# ----- Shared bounds -----


_MinSpice, _MaxSpice = SPICE_TOLERANCE_RANGE
_CUISINE_SET = frozenset(CUISINE_IDS)


class _PreferencesBase(BaseModel):
    """Shared fields + cross-field validators used by both read & update."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    cuisine_weights: dict[str, float] = {}
    allergies: list[str] = []
    spice_tolerance: int = 0
    temperature_preference: str = "room"
    # F051 §3.1: default_location 从 `str | None` 升级为 `StructuredAddress | None`.
    # StructuredAddress 自身的 field_validator 已校验 adcode / poi_id / 名称 / door_no 正则,
    # 此处只需声明类型, 无需重复校验.
    default_location: StructuredAddress | None = None
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
    """All 14 cuisines at neutral weight — used when no record exists yet.

    The neutral weight lives in `app.core.constants.NEUTRAL_CUISINE_WEIGHT`
    so the F002 router can import the same value without an `agents →
    schemas` reverse import.
    """
    return {cuisine: NEUTRAL_CUISINE_WEIGHT for cuisine in CUISINE_IDS}