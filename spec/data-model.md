# data-model.md — 数据模型

> M0 阶段无业务表。M1 Agent MVP **仅需一张核心表**：`user_preferences`。
> 原计划的 `user_feedback` 表与 `users` / `shops` / `orders` 等表标记 `[DEPRECATED-M0]`，**不再建表**；`user_feedback` 延后到 M2 再说。

## 通用约定

- 引擎：MySQL 8，字符集 `utf8mb4`，排序 `utf8mb4_0900_ai_ci`
- ORM：SQLModel（SQLAlchemy 2.0 + Pydantic v2）
- 主键：所有表 `id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY`
- 审计字段：所有表 `created_at / updated_at`（`updated_at` 由 ORM 自动维护）
- 软删：业务表统一 `deleted_at DATETIME NULL`（按需启用）
- 时间：所有时间字段 `DATETIME(3)`（毫秒精度）
- JSON 字段：用 `JSON` 类型 + Pydantic 校验；**禁止**字符串化 JSON 存业务数据
- 索引：所有外键列加索引；高频查询条件列加复合索引

## 安全基线

- 用户标识：`user_id` 用前端生成的 UUID 字符串（M1 **不做登录**，无密码 / token / JWT）；登录态推到 M2
- 偏好数据：仅本人读写；其他用户**不可见**
- M1 不引入任何鉴权 token；用户身份完全靠 `X-User-Id` 请求头 + cookie 维持

---

## M1 Agent MVP 表清单

| 表 | 用途 | Spec |
|---|---|---|
| `user_preferences` | 用户口味偏好（菜系权重 / 忌口 / 预算 / 默认位置） | F001 |

> M1 不建 `user_feedback` 表；feedback 整体延后到 M2。

---

## `user_preferences`（F001）

每用户一条，1:1 关系。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGINT UNSIGNED | PK | |
| `user_id` | VARCHAR(36) | UNIQUE NOT NULL | UUID，前端生成 |
| `cuisine_weights` | JSON | NOT NULL DEFAULT '{}' | `{"sichuan": 0.8, "cantonese": 0.5, ...}`，值范围 [0, 1] |
| `allergies` | JSON | NOT NULL DEFAULT '[]' | `["peanut", "shellfish", ...]`，枚举值见 F001 §3 |
| `spice_tolerance` | TINYINT UNSIGNED | NOT NULL DEFAULT 0 | 0=不吃辣 / 1=微辣 / 2=中辣 / 3=重辣 |
| `temperature_preference` | VARCHAR(8) | NOT NULL DEFAULT 'room' | 温度偏好：`"cold"` 冰镇 / 凉拌 / `"room"` 常温 / `"hot"` 热乎；详见 F001 §3.4 |
| `default_location` | VARCHAR(128) | NULL | 默认搜索锚点（6 位 adcode 或主流城市名；详见 F001 §3.5），由用户设置 |
| `budget_lunch_min` | DECIMAL(8,2) | NULL | 午餐预算下限（元），可空 |
| `budget_lunch_max` | DECIMAL(8,2) | NULL | 午餐预算上限（元），可空；**包含配送费**（即"用户实际愿意为一份外卖付出的总价"上限，含餐品 + 打包费 + 平台配送费） |
| `created_at` | DATETIME(3) | NOT NULL | |
| `updated_at` | DATETIME(3) | NOT NULL | ORM 自动维护 |

索引：

- UNIQUE：`user_id`

---

## [M2 规划中] `user_feedback`

> **M1 不建此表**。M2 引入时再补全字段。当前仅占位。

---

## [DEPRECATED-M0] 历史表（不再实现）

- [DEPRECATED-M0] `users`：由 `user_preferences.user_id`（UUID 字符串）替代
- [DEPRECATED-M0] `shops`：本系统不维护商家数据，餐厅信息来自高德 MCP 实时查询
- [DEPRECATED-M0] `categories` / `dishes`：菜系分类由 prompt 模板静态编码，不入库
- [DEPRECATED-M0] `orders` / `order_items` / `payments`：本系统不实际下单
- [M2-PENDING] `user_feedback`：M1 不建表；M2 引入反馈学习时再建