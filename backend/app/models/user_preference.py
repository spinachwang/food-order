"""User preferences table (F001).

Per `spec/data-model.md` §`user_preferences` (patched in Step 0.5 to include
`temperature_preference`):

- `id` → `BIGINT UNSIGNED` (SQLModel/SQLAlchemy: `BigInteger, unsigned=True`)
- `spice_tolerance` → `TINYINT UNSIGNED` (SQLModel: `SmallInteger, unsigned=True`)
- `created_at` / `updated_at` → `DATETIME(3)` (millisecond precision)

JSON columns (`cuisine_weights`, `allergies`) use `sa_column=Column(JSON, ...)`
explicitly because SQLModel's default mapping of `dict[str, float]` /
`list[str]` to MySQL JSON is unreliable across SQLAlchemy versions.

`default=dict` (NOT `default={}`) avoids the shared-mutable-default trap.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, Column, SmallInteger
from sqlalchemy.dialects.mysql import BIGINT, SMALLINT
from sqlmodel import Field, SQLModel


class UserPreference(SQLModel, table=True):
    """SQLModel row for the `user_preferences` table."""

    __tablename__ = "user_preferences"

    id: int | None = Field(
        default=None,
        sa_column=Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True),
    )
    user_id: str = Field(max_length=36, unique=True, index=True, nullable=False)

    cuisine_weights: dict[str, float] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    allergies: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )

    spice_tolerance: int = Field(
        default=0,
        ge=0,
        le=3,
        sa_column=Column(SMALLINT(unsigned=True), nullable=False),
    )
    temperature_preference: str = Field(default="room", max_length=8, nullable=False)

    default_location: str | None = Field(default=None, max_length=128, nullable=True)

    budget_lunch_min: Decimal | None = Field(
        default=None, max_digits=8, decimal_places=2, nullable=True
    )
    budget_lunch_max: Decimal | None = Field(
        default=None, max_digits=8, decimal_places=2, nullable=True
    )

    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


# Silence unused-import lint; BigInteger/SmallInteger are kept for migration
# cross-dialect fallbacks (e.g. SQLite tests).
_ = (BigInteger, SmallInteger)