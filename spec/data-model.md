# data-model.md — 数据模型

> ⚠️ M0 阶段无数据表。M1 各功能 spec 化后追加表结构。

## 通用约定

- 引擎：MySQL 8，字符集 `utf8mb4`，排序 `utf8mb4_0900_ai_ci`
- ORM：SQLModel（SQLAlchemy 2.0 + Pydantic v2）
- 主键：所有表 `id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY`
- 审计字段：所有表 `created_at / updated_at`（`updated_at` 由 ORM 自动维护）
- 软删：业务表统一 `deleted_at DATETIME NULL`（按需启用）
- 金额：所有货币字段 `DECIMAL(10,2)`，单位"元"
- 时间：所有时间字段 `DATETIME(3)`（毫秒精度）
- 索引：所有外键列加索引；高频查询条件列加复合索引

## 安全基线

- 密码：`argon2id` 哈希存储，**绝不**明文
- 手机号：哈希或脱敏存储，原始值仅用于发送通知
- Token：JWT 仅保留必要声明；不存敏感数据

---

## M1 表清单（占位）

| 表 | 用途 | Spec |
|---|---|---|
| `users` | 用户（顾客 + 商家） | F020 |
| `shops` | 店铺 | F001 |
| `categories` | 菜品分类 | F002 |
| `dishes` | 菜品 | F002 |
| `orders` | 订单 | F004 |
| `order_items` | 订单明细 | F004 |
| `payments` | 支付记录 | F005 |

> 详细字段、外键、索引在对应功能的 spec 中定义（按 F-ID 引用）。