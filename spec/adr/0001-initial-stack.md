# ADR 0001 — 初始技术栈选型

- **状态**：Accepted
- **日期**：2026-08-29
- **决策者**：项目负责人

## 背景

`food-order` 是新启动的餐饮点单 Web 应用。需要在前端框架、后端框架、ORM、测试栈、Python 环境管理等关键维度做出初始选型，作为后续所有 spec 与代码的基线。

## 决策

| 维度 | 选择 | 理由 |
|---|---|---|
| 前端框架 | React 18 + TypeScript | 生态成熟、招聘面广、与 Vite 集成好 |
| 前端构建 | Vite 5 | 快、HMR、TS 默认支持 |
| 后端框架 | FastAPI | 异步原生、OpenAPI 自动生成、Pydantic 校验 |
| ORM | SQLModel | SQLAlchemy 2.0 + Pydantic v2 合一，减少样板 |
| 数据库 | MySQL 8 | 团队熟悉、运维简单、字符集支持好 |
| Python 环境 | conda env `food-order` | 继承全局规则 |
| 包管理（前端） | pnpm | 快、磁盘省、monorepo 友好 |
| 鉴权 | 自建 JWT (HS256) | M1 简单可控，后期可换 RS256 |
| 测试（后端） | pytest + httpx + pytest-asyncio | 标准组合 |
| 测试（前端） | Vitest + Testing Library + Playwright | 单测 + E2E 覆盖 |
| Lint（后端） | ruff + mypy | 快、规则全 |
| Lint（前端） | ESLint + Prettier | 生态标准 |

## 后果

- 锁定后端 Python 版本为 3.11+；conda 环境名 `food-order`。
- 锁定前端包管理器为 pnpm；`package.json` 中 `packageManager` 字段约束版本。
- 任何后续替换必须新开一条 ADR 并更新 `spec/architecture.md` 与 `CLAUDE.md` 的技术栈表。

## 备选方案

- 后端：Django + DRF（重，ORM 自带 admin 优势对本项目不重要）；NestJS（TS 栈统一但与 Python 数据科学 / 脚本生态割裂）。
- ORM：纯 SQLAlchemy 2.0（灵活但样板多）；Tortoise ORM（异步但生态小）。
- 数据库：PostgreSQL（功能更强但运维成本略高）；SQLite（M1 不适用并发）。

## 参考

- 全局规则：`~/.claude/rules/common/coding-style.md`、`testing.md`
- CLAUDE.md：[../../CLAUDE.md](../../CLAUDE.md)