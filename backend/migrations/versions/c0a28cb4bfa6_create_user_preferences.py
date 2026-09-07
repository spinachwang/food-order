"""create user_preferences

Revision ID: c0a28cb4bfa6
Revises:
Create Date: 2026-09-02 00:15:00.165049

Hand-patched on top of `alembic revision --autogenerate` to match
`spec/data-model.md` precisely:

- `created_at` / `updated_at` → `DATETIME(3)` (millisecond precision) +
  server defaults (`CURRENT_TIMESTAMP(3)`; `updated_at` also `ON UPDATE`).
- `spice_tolerance` → `DEFAULT 0` (matches Python-side default).
- `temperature_preference` → `DEFAULT 'room'` (matches Python-side default).
- CHECK constraints for `spice_tolerance` (0..3) and `temperature_preference`
  (enum) so DB enforces invariants even if ORM is bypassed.

JSON columns `cuisine_weights` and `allergies` have NO server default —
MySQL JSON default expressions are awkward (`DEFAULT (JSON_OBJECT())` etc.)
and SQLModel always populates them from `default_factory=dict` / `list`, so
the application layer is the only writer in M1.
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "c0a28cb4bfa6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_preferences",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column("cuisine_weights", sa.JSON(), nullable=False),
        sa.Column("allergies", sa.JSON(), nullable=False),
        sa.Column(
            "spice_tolerance",
            mysql.SMALLINT(unsigned=True),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "temperature_preference",
            sqlmodel.sql.sqltypes.AutoString(length=8),
            nullable=False,
            server_default=sa.text("'room'"),
        ),
        sa.Column(
            "default_location",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=True,
        ),
        sa.Column("budget_lunch_min", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("budget_lunch_max", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=3),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
        ),
        sa.CheckConstraint(
            "spice_tolerance BETWEEN 0 AND 3",
            name="ck_user_preferences_spice_tolerance_range",
        ),
        sa.CheckConstraint(
            "temperature_preference IN ('cold', 'room', 'hot')",
            name="ck_user_preferences_temperature_enum",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_preferences_user_id"),
        "user_preferences",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_preferences_user_id"), table_name="user_preferences")
    op.drop_table("user_preferences")