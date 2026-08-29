# api.md — REST 接口契约

> ⚠️ M0 阶段仅 `/healthz`。具体接口在 M1 各功能 spec 化后追加。

## 通用约定

- 基址：`{VITE_API_BASE_URL}`，默认 `http://localhost:8000`
- 版本前缀：`/api/v1`
- 鉴权：`Authorization: Bearer <jwt>`（受保护接口）
- 内容类型：`application/json; charset=utf-8`
- 错误响应统一信封（参考全局规则）：

```json
{
  "ok": false,
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "订单不存在",
    "details": null
  }
}
```

成功响应：

```json
{
  "ok": true,
  "data": { /* ... */ }
}
```

---

## M0

### `GET /healthz`

健康检查。

- **响应 200**：`{"status": "ok"}`

---

## M1（占位）

| 方法 | 路径 | 说明 | Spec |
|---|---|---|---|
| POST | /api/v1/auth/register | 用户注册 | F020 |
| POST | /api/v1/auth/login | 用户登录 | F020 |
| GET  | /api/v1/shops | 店铺列表 | F001 |
| GET  | /api/v1/shops/{id}/menu | 店铺菜单 | F002 |
| POST | /api/v1/orders | 创建订单 | F004 |
| POST | /api/v1/orders/{id}/pay | 订单支付 | F005 |
| GET  | /api/v1/orders | 我的订单 | F006 |

> 具体 schema 在对应功能的 spec 中定义（按 F-ID 引用）。