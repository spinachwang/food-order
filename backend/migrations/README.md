# food-order — 后端数据库迁移

> 本目录是 [`food-order`](../../) 后端的 **Alembic** 迁移脚本。
> 项目背景 / 架构设计 / 技术栈 / 启动方式见仓库根 [README.md](../../README.md) 与 [CLAUDE.md](../../CLAUDE.md)。

## 目录内容

| 文件 / 目录 | 作用 |
|---|---|
| [`env.py`](./env.py) | Alembic 入口；从仓库根加载 `.env`，从 `app.core.config` 读取数据库 URL；自动导入所有 `app.models.*` 以填充 `SQLModel.metadata` |
| [`script.py.mako`](./script.py.mako) | 迁移文件模板（`alembic revision` 自动套用） |
| [`versions/`](./versions/) | 已生成的迁移脚本（按 revision id 升序） |

## 数据模型（SSOT）

迁移脚本必须与 [`spec/data-model.md`](../../spec/data-model.md) 保持一致。

**M1 Agent MVP 当前只一张核心表**：`user_preferences`（详见 [F001](../../spec/features/F001-user-preferences.md)）。
`user_feedback` / `users` / `shops` 等历史表已标记 `[DEPRECATED-M0]`，**不再建表**。

| revision id | 内容 | 关联 spec |
|---|---|---|
| `c0a28cb4bfa6` | 建表 `user_preferences`（含 `cuisine_weights` / `allergies` / `spice_tolerance` / `temperature_preference` / `default_location` / 预算范围） | [F001 §3](../../spec/features/F001-user-preferences.md) |
| `8b3c2f1a4d5e` | `default_location` 字段类型迁移：`VARCHAR(128)` → `JSON`；GET 时回填 `null`（无数据清洗脚本） | [F051 §3.1](../../spec/features/F051-structured-address.md) |

## 常用命令

> 所有命令从**仓库根目录**运行；Python 走 conda 全局规则。

```bash
# 升级到最新迁移
conda run -n food-order alembic upgrade head

# 回退一步
conda run -n food-order alembic downgrade -1

# 自动生成迁移（autogenerate）—— 仅作为初稿，DDL 必须人工 review
conda run -n food-order alembic revision --autogenerate -m "<F-ID> <描述>"

# 空模板
conda run -n food-order alembic revision -m "<F-ID> <描述>"

# 查看当前版本
conda run -n food-order alembic current

# 查看历史
conda run -n food-order alembic history --verbose
```

## 新增迁移的流程

1. **先更新 spec**：在 [`spec/data-model.md`](../../spec/data-model.md) 写清字段类型 / 索引 / 约束；`feat/*` 分支名带 `F-ID`
2. **改 model**：在 `backend/app/models/<x>.py` 用 SQLModel 定义；新 model 必须在 [`env.py`](./env.py) 显式 `import`
3. **生成迁移**：`alembic revision --autogenerate -m "<F-ID> ..."`，人工 review DDL（autogenerate 可能漏索引 / `JSON` 默认值）
4. **正反两边都测**：`alembic upgrade head && alembic downgrade -1 && alembic upgrade head` 必须无报错
5. **同 PR 提交**：迁移文件 + model 改动 + spec 改动 + 对应测试

## 数据库约定（继承自 spec）

- 引擎：MySQL 8，字符集 `utf8mb4`，排序 `utf8mb4_0900_ai_ci`
- 主键：`id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY`
- 审计字段：所有表 `created_at / updated_at`（`updated_at` ORM 自动维护）
- 时间：`DATETIME(3)`（毫秒精度）
- JSON 字段：MySQL `JSON` 类型 + Pydantic 校验；**禁止**字符串化 JSON 存业务数据
- 索引：所有外键列加索引；高频查询条件列加复合索引
- 不做软删（默认无 `deleted_at`，按表需要再补）

详见 [`spec/data-model.md §通用约定`](../../spec/data-model.md)。