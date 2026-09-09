"""user_preferences.default_location: VARCHAR(128) → JSON (F051 升级)

Revision ID: 8b3c2f1a4d5e
Revises: c0a28cb4bfa6
Create Date: 2026-09-08 12:00:00.000000

F051 §3.1 + spec/data-model.md 修订 (2026-09-08):
`default_location` 由 `VARCHAR(128)` 升级为 `JSON`, 承载 `StructuredAddress`
对象 (Pydantic v2 校验过的 5 级地址结构).

数据迁移策略 (F051 §3.5.2 + spec/api.md § M1):
- **不写**独立数据迁移脚本; 但 `upgrade()` 必须先把所有现有非 JSON 行清成
  `NULL`, 再 ALTER 列类型为 JSON —— MySQL ALTER 会逐行校验 JSON 合法性,
  老字符串 (`"国贸"` / `"国贸三期"` 等) 不是合法 JSON, 会
  直接抛 `Invalid JSON text` (错误码 3140). 只能先 UPDATE 清空再 ALTER.
- 老字符串值 (例如 `"国贸三期"`) 在 `GET /api/v1/preferences` 读取时由
  `app/services/preferences.py` 的 `_coerce_default_location` 兼容回填为
  `None` (前端兜底到 IP 城市, 引导用户重新选择结构化地址).
- **不写**历史数据备份脚本; 字段值永久丢失无副作用 (用户重新选择即覆盖).
- DB 列类型变更后 NULL 值不受影响; service 层兜底识别并回填 None.

降级策略 (`downgrade()`):
- DB 列类型改回 `VARCHAR(128)`; 现有 JSON 数据会被 MySQL 序列化为字符串存储,
  GET 时由 service 层兼容路径回填 None. **降级后老 JSON 数据不可访问** —
  仅供紧急回滚使用.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b3c2f1a4d5e"
down_revision: str | Sequence[str] | None = "c0a28cb4bfa6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """`default_location`: VARCHAR(128) → JSON.

    两步走: 先把现有非 NULL 行清成 NULL (MySQL ALTER TO JSON 会逐行校验 JSON
    合法性, 老字符串直接抛 `Invalid JSON text` 错误码 3140), 再 ALTER 列类型.
    """
    bind = op.get_bind()
    # 1) 清空所有非 NULL 老字符串 — service 层会在 GET 时回填为 None
    bind.execute(
        sa.text("UPDATE user_preferences SET default_location = NULL")
    )
    # 2) ALTER 列类型为 JSON
    op.alter_column(
        "user_preferences",
        "default_location",
        existing_type=sa.String(length=128),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="default_location::json",
    )


def downgrade() -> None:
    """`default_location`: JSON → VARCHAR(128) (紧急回滚).

    注: 降级会丢失已结构化的地址数据 — 仅供紧急回滚.
    """
    op.alter_column(
        "user_preferences",
        "default_location",
        existing_type=sa.JSON(),
        type_=sa.String(length=128),
        existing_nullable=True,
    )