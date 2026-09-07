# api.md — REST 接口契约

> M0 阶段仅 `/healthz`。M1 Agent MVP 追加：偏好 CRUD + Agent 流式聊天接口。
> 原 M0 顾客端 / 商家端 / 支付接口标记 `[DEPRECATED-M0]`，**不再实现**。

## 通用约定

- 基址：`{VITE_API_BASE_URL}`，默认 `http://localhost:8000`
- 版本前缀：`/api/v1`
- 鉴权：M1 **不做登录**；用户标识来自前端生成的匿名 UUID（`X-User-Id` 请求头 + cookie），后端据此加载 `user_preferences`，不维护登录态。登录态推到 M2（届时再决定 JWT vs session）
- 内容类型：`application/json; charset=utf-8`
- 流式响应：`text/event-stream`（SSE，遵循 OpenAI 兼容事件格式）
- 错误响应统一信封：

```json
{
  "ok": false,
  "error": {
    "code": "PREFERENCE_NOT_FOUND",
    "message": "用户偏好不存在",
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

## M1 Agent MVP

### `GET /api/v1/preferences` — F001

按 `X-User-Id` 获取当前用户偏好；不存在则返回默认值（不创建）。

- **响应 200**：

```json
{
  "ok": true,
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "cuisine_weights": { "sichuan": 0.8, "cantonese": 0.5 },
    "allergies": ["peanut"],
    "spice_tolerance": 2,
    "temperature_preference": "room",
    "default_location": "国贸三期",
    "budget_lunch_min": "20.00",
    "budget_lunch_max": "60.00"
  }
}
```

### `PUT /api/v1/preferences` — F001

完整覆盖当前用户偏好（不存在则创建）。

- **请求体**：

```json
{
  "cuisine_weights": { "sichuan": 0.8, "cantonese": 0.5 },
  "allergies": ["peanut"],
  "spice_tolerance": 2,
  "temperature_preference": "room",
  "default_location": "国贸三期",
  "budget_lunch_min": "20.00",
  "budget_lunch_max": "60.00"
}
```

- **响应 200**：返回更新后的完整偏好（同 GET）

### `POST /api/v1/agent/chat` — F002 + F040

发起一次 Agent 对话；流式 SSE 返回中间事件与最终推荐。

- **请求体**：

```json
{
  "message": "今天想吃辣的",
  "session_id": "可选 UUID，用于多轮上下文",
  "location_override": "可选，覆盖默认位置（格式约束见 F001 §3.5：6 位 adcode 或主流城市名）"
}
```

> `default_location` / `location_override` 格式约束详见 [F001 §3.5](features/F001-user-preferences.md)。

- **响应 200**：`Content-Type: text/event-stream`

事件流（按时间顺序）：

```
event: cuisine_selected
data: {"cuisines": ["sichuan", "hunan"], "routing_reason": "你说想吃辣的 → 川 + 湘"}

event: restaurant_searching
data: {"cuisine": "sichuan"}

event: restaurant_found
data: {"cuisine": "sichuan", "restaurants": [/* >=3 */]}

event: weather
data: {"temperature": 32, "condition": "sunny", "precipitation_probability": 0.05}

event: recommendation
data: {
  "headline": "今天推荐：蜀香苑",
  "cuisine": "sichuan",
  "restaurant_id": "B0FFF...",
  "order_takeout": false,
  "reason": "天气晴朗，距您 380m，步行 5 分钟可达",
  "alternatives": [/* 2-3 个备选 */]
}

event: done
data: {}
```

错误事件：

```
event: error
data: {"code": "AMAP_QUOTA_EXCEEDED", "message": "高德 API 配额耗尽"}
```

> `cuisine_selected.routing_reason` ≤30 字、人话风格，由 [F002](features/F002-main-agent-router.md) §2 产出，
> [F050](features/F050-chat-shell.md) 在回复气泡中直接渲染。
>
> 路由阶段可能出现的 `error.code`（见 F002 §6）：`EMPTY_MESSAGE`（消息为空 / 乱码，不进下游）、
> `NO_CUISINE_MATCHED`（已按偏好 top-1 兜底，流程继续）、`ALL_CUISINES_FILTERED`（忌口把候选全剔除）。

---

## M2 — 体验增强（规划中，不在 M1 范围）

> 以下端点在 M1 阶段**不实现**，仅占位供 spec 引用：

- [M2] `POST /api/v1/feedback` — 记录用户对推荐的采纳 / 否决 / 收藏反馈；用于回写调整 `cuisine_weights` 先验概率
- [M2] `POST /api/v1/auth/login` / `auth/logout` — 登录态（JWT 或 session 待 M2 决策）

## [DEPRECATED-M0] 历史接口（不再实现）

- [DEPRECATED-M0] `POST /api/v1/auth/register` / `auth/login`
- [DEPRECATED-M0] `GET /api/v1/shops` / `shops/{id}/menu`
- [DEPRECATED-M0] `POST /api/v1/orders` / `orders/{id}/pay`
- [DEPRECATED-M0] `GET /api/v1/orders`