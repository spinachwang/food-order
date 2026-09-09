# F001 — 用户偏好管理

> **状态**：[ ] 未开始
> **所属里程碑**：M1 Agent MVP
> **依赖**：无（基础功能）
> **被依赖**：F002（主 Agent 读取）、F003（菜系专家读取）、F040（总结 Agent 参考）

## 1. 用户故事

作为办公室打工人，我希望保存我的口味偏好（菜系倾向、忌口、辣度、预算、默认位置），下次打开应用时系统能"记住我"，给出更精准的午餐推荐。

## 2. 验收清单

- [ ] `GET /api/v1/preferences`：未设置时返回默认值而非 404
- [ ] `PUT /api/v1/preferences`：完整覆盖式更新，校验菜系 ID 在 F003 枚举内
- [ ] 数据校验：`spice_tolerance ∈ [0,3]`、`cuisine_weights` 各值 ∈ [0,1]、`allergies` 限定枚举
- [ ] 主 Agent / 菜系专家 / 总结 Agent 都能通过内部接口读取偏好
- [ ] M1 **不做登录**：用户标识来自前端生成的匿名 UUID（写入 `X-User-Id` 请求头 + cookie），后端不维护登录态；登录态推到 M2
- [ ] M1 **不做 feedback**：`POST /api/v1/feedback` / `user_feedback` 表延后到 M2；本 spec 不实现该端点
- [ ] `budget_lunch_max` **包含配送费**（即"用户实际支出上限"，含商家打包费 + 平台配送费）
- [ ] 单元 / 集成测试覆盖率 ≥ 80%

## 3. 偏好字段定义

### 3.1 过敏原枚举（`allergies`）

```python
ALLERGY_VALUES = {
    "peanut",        # 花生
    "tree_nut",      # 坚果（杏仁 / 腰果等）
    "shellfish",     # 虾蟹贝
    "fish",
    "egg",
    "soy",
    "wheat",         # 含麸质
    "dairy",
    "sesame",
    "alcohol",
    "fried_food",    # 油炸（F050 §8 待澄清 #7 决议 2026-08-30；前端"不吃油炸"chip 映射）
}
```

### 3.2 辣度（`spice_tolerance`）

| 值 | 含义 |
|---|---|
| 0 | 不吃辣 |
| 1 | 微辣 |
| 2 | 中辣 |
| 3 | 重辣 |

### 3.3 菜系权重（`cuisine_weights`）

键为 F003 §3.2 中的 `cuisine_id`；值为 [0, 1] 的浮点数。

- 0 = 完全不感兴趣
- 0.5 = 中性
- 1.0 = 强烈偏好

权重会被 F002 主 Agent router 用作"模糊意图"路由的先验概率。

### 3.4 温度偏好（`temperature_preference`）

| 值 | 含义 |
|---|---|
| `"cold"` | 冰镇 / 凉拌 |
| `"room"` | 常温 |
| `"hot"`  | 热乎乎的 |

> **来源**：F050 §8 待澄清 #6 决议 2026-08-30。原 prototype 温度 toggle 误用 `spice_tolerance` 字段；改为独立 `temperature_preference` 字段，`spice_tolerance` 恢复"辣度 0–3"原意。前端控件不变，提交时映射为字符串。

### 3.5 默认位置（`default_location`）

Agent 搜索锚点。**M1 字段类型升级（2026-09-08，[F051](F051-structured-address.md) 决议）**：

- **新格式**：`StructuredAddress | None`（结构化对象，见 §3.5.1）
- **生产路径**：用户在 [F050 §2.4 addr-edit 弹层](F050-chat-shell.md) 通过 5 级选择器（省 / 市 / 区 / 商圈 / 小区 / 门牌号）产生；底层 adcode 由前端从高德 `/config/district` + `place/text` 实时获取，避免字符串解析回退
- **消费路径**：[F030 §3.3](F030-amap-restaurant-search.md) `search_restaurants` / [F031 §3.1](F031-amap-weather.md) `fetch_weather` 直接读 `city_adcode` / `district_adcode`，不再回退到全局默认

#### 3.5.1 `StructuredAddress`（[F051 §3.1](F051-structured-address.md)）

```python
class StructuredAddress(BaseModel):
    province: str                # "上海市" / "北京市"
    province_adcode: str         # 6 位省级 adcode ("310000")
    city: str                    # "上海市"
    city_adcode: str             # 6 位市级 adcode ("310100") — Amap weather 锚点
    district: str | None = None  # "静安区"（直辖市可省）
    district_adcode: str | None  # 6 位区级 adcode ("310106") — Amap place/around 锚点
    street: str | None = None    # 街道 / 商圈
    community: str | None = None # 小区 / 楼宇
    poi_id: str | None = None    # 高德 POI id
    door_no: str | None = None   # 门牌号 / 楼层 / 房间号
```

字段正则约束（[F051 §3.2](F051-structured-address.md)）：

| 字段 | 约束 |
|---|---|
| `province_adcode` / `city_adcode` / `district_adcode` | `^[0-9]{6}$` |
| `poi_id` | `^[A-Z0-9]{20,32}$` |
| `province` / `city` / `district` / `street` / `community` | 中文 / 字母 / 数字 / 空格 / `·`，长度 ≤ 32 |
| `door_no` | 任意字符，长度 ≤ 64 |

#### 3.5.2 向后兼容

> **设计动机**（2026-09-08 决议）：原 §3.5 的字符串方案（adcode / 城市名）无法让前端保证 adcode 来源稳定，导致 M1 落地后 F031 `fetch_weather` 持续触发 `AMAP_LOCATION_INVALID` 降级（"天气暂不可用"）。升级为结构化对象后，前端选址组件天然产出 adcode，F030 / F031 直接消费，零字符串解析。

**迁移策略**：

- **GET 兼容**：数据库老数据 `default_location` 是字符串（如 `"国贸三期"`）时，GET 返回 `default_location: null`（前端兜底到 IP 城市），**不抛 400**
- **PUT 严格**：M1 升级后 PUT 只接受 `StructuredAddress`；字符串 payload 直接 `400 INVALID_STRUCTURED_ADDRESS`
- **`location_override` 不变**：POST /api/v1/agent/chat 的 `location_override` 字段**仍是字符串**（adcode / 主流城市名），由调用方保证；详见 [api.md § M1](../../api.md)

校验策略：

- **PUT /api/v1/preferences** —— 严格校验：§3.5.1 必填字段非空、§3.5.2 正则全部放行
- **Node 层兜底** —— `fetch_weather.py` / `search_restaurants.py` 仍保留回退到 `_DEFAULT_LOCATION = "110000"`（北京 adcode）的兜底逻辑，作为结构化字段缺失时的最后防线
- **M2 计划** —— `location_override` 字段类型可选择性升级为结构化对象（视 M2 是否仍保留单次覆盖语义）

#### 3.5.3 前端 hydrate 契约

> **变更**（2026-09-09）：补全 PUT 之外的"读取即恢复"路径。原 §3.5 / §4.2 描述了"如何保存"，但没规定"GET 后前端如何把 `default_location` 落到本地 store"；M1 落地后表现为"用户每次重新打开页面都要重新选地址"。

**契约**：

- **首次打开**（GET 返回 `default_location: null`，含老数据兼容回填）→ `chatStore.address` 保持 `null`，`ContextStrip` 显示兜底字符串（[F050 §2.4](F050-chat-shell.md)）
- **第二次及之后打开**（GET 返回非 null 结构化对象）→ 前端 mount `PreferencesPanel` 时，hydrate 一次性 `setAddress(remotePrefs.default_location)`，让 `ContextStrip` 立即显示用户上次保存的地址，无需再次打开地址选择器
- **同次会话 `AddressPickerDialog` 点保存** → `setAddress(parsed.data)` 立即生效（[F051 §4.2](F051-structured-address.md) 行为表第 4 行），并 PUT 远端
- **后端是 source of truth**：即使本地 `chatStore.address` 是 `null`，hydrate 也用服务端值回填（覆盖用户在另一浏览器设置过的地址）

**实现位置**：`frontend/src/features/chat/components/PreferencesPanel.tsx` 的 hydrate `useEffect`，与 `uiPrefs` 同步共用同一个 `hydrated` flag，避免多次写入。

**不实现**（明确划界）：

- ❌ `chatStore` 走 `zustand/middleware/persist` —— chatStore 设计为"不持久化"（[chatStore.ts](../../frontend/src/stores/chatStore.ts) §设计要点）；SSR / 多窗口同步由本契约的 GET hydrate 保证
- ❌ 后端主动 push `default_location` 变更给前端 —— M1 单 tab 场景，dialog 保存后本地已立即 `setAddress`，无需 push

## 4. 输入 / 输出（Agent 视角）

```python
class UserPreferences(TypedDict):
    user_id: str
    cuisine_weights: dict[str, float]   # 14 keys, value in [0,1]
    allergies: list[str]                # 0-N elements
    spice_tolerance: int                # 0-3
    temperature_preference: Literal["cold", "room", "hot"]  # F050 §3.4
    default_location: StructuredAddress | None  # F051 §3.1：升级为结构化对象
    budget_lunch_min: Decimal | None
    budget_lunch_max: Decimal | None  # 包含配送费（餐品 + 打包费 + 平台配送费的合计上限）
```

### Agent 读取接口（内部）

```python
async def load_preferences(user_id: str) -> UserPreferences:
    """GET /api/v1/preferences 的 service 层封装；不存在返回默认值。"""
```

> **M1 不做 feedback**：`record_feedback` 函数与 `POST /api/v1/feedback` 端点延后到 M2。本 spec 不再包含其签名。

## 5. 数据 / 接口变更

### 新增表

详见 [../data-model.md](../data-model.md)：

- `user_preferences`

### 新增 API

- `GET /api/v1/preferences` — 返回当前用户偏好
- `PUT /api/v1/preferences` — 完整覆盖更新

API 契约详见 [../api.md § M1](../api.md#m1-agent-mvp)。

> **M1 不做 feedback**：原计划的 `user_feedback` 表 + `POST /api/v1/feedback` 端点延后到 M2 再做。

## 6. 错误码

| code | 含义 | HTTP | 备注 |
|---|---|---|---|
| `INVALID_CUISINE_ID` | cuisine_weights 含未在 F003 §3.2 注册的 ID | 400 | |
| `INVALID_ALLERGY` | allergies 含未在 §3.1 注册的值 | 400 | |
| `INVALID_SPICE` | spice_tolerance ∉ [0,3] | 400 | |
| `INVALID_TEMPERATURE` | temperature_preference ∉ {"cold","room","hot"}（§3.4） | 400 | |
| `INVALID_BUDGET` | min > max 或负值 | 400 | |
| `INVALID_LOCATION_FORMAT` | `location_override` 是坐标或非城市名 | 400 | M1 暂不触发（仅针对 `location_override` 字符串字段）；`default_location` 升级结构化对象后由 `INVALID_STRUCTURED_ADDRESS` 接管 |
| `INVALID_STRUCTURED_ADDRESS` | `default_location` 缺字段、字段值不匹配 §3.5.2 正则 | 400 | F051 §7；M1 升级后启用（取代原 `INVALID_LOCATION_FORMAT` 对 `default_location` 的覆盖） |

## 7. 测试计划

### 单元测试（`backend/tests/unit/test_preferences.py`）

- [ ] 默认值生成：新建用户返回全 0.5 权重 + 空 allergies + `spice_tolerance=0`
- [ ] 校验：非枚举菜系 ID → 抛 `INVALID_CUISINE_ID`
- [ ] 校验：菜系权重越界 → 400
- [ ] 校验：辣度越界 → 400
- [ ] 校验：预算 min > max → 400

### 集成测试（`backend/tests/integration/test_preferences_api.py`）

- [ ] `GET /api/v1/preferences` 不带 `X-User-Id` → 自动生成匿名 UUID 并返回默认
- [ ] `PUT /api/v1/preferences` 覆盖更新后 `GET` 返回新值
- [ ] `budget_lunch_max` 包含配送费的语义在 F040 决策矩阵中被正确使用

### 端到端（Playwright）

- [ ] 不直接测；由 F050（Web 聊天壳）的"打开应用 → 修改偏好 → 推荐结果变化"覆盖
- [ ] 结构化地址的端到端由 [F051 §8.3](F051-structured-address.md) 覆盖

### 前端 hydrate 测试（`frontend/src/features/chat/components/PreferencesPanel.test.tsx`）—— §3.5.3

- [ ] GET 返回 `default_location: null` → mount 后 `chatStore.address` 仍为 `null`（首次打开场景）
- [ ] GET 返回结构化 `default_location` → mount 后 `chatStore.address` 等于该对象（第二次打开恢复场景）—— 提交 SHA: `frontend/src/features/chat/components/PreferencesPanel.tsx` 的 hydrate effect 新增 `setAddress(remotePrefs.default_location)` 一行

## 8. 变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-30 | 0.1 | 初稿：偏好数据模型 + CRUD API + M1 不做登录 / feedback |
| 2026-08-30 | 0.2 | §3.1 新增 `fried_food`；§3.4 新增 `temperature_preference`；§4 TypedDict 同步；§6 新增 `INVALID_TEMPERATURE` |
| 2026-09-07 | 0.3 | §3.5 收窄 `default_location` 合法格式为 6 位 adcode / 主流城市名；§6 标注 `INVALID_LOCATION_FORMAT` M1 暂不触发；§3.5 增加 Node 层兜底到 `110000`（北京）adcode 的策略 |
| 2026-09-08 | 0.4 | **§3.5 字段类型升级**：`default_location` 由 `str \| None` 升级为 `StructuredAddress \| None`（见 [F051](F051-structured-address.md)）；§3.5.1 / §3.5.2 新增结构化对象与正则约束；§4 TypedDict 同步；§6 错误码新增 `INVALID_STRUCTURED_ADDRESS`，原 `INVALID_LOCATION_FORMAT` 范围收窄到仅 `location_override` 字符串字段 |
| 2026-09-09 | 0.5 | **§3.5.3 前端 hydrate 契约**：GET 返回的 `default_location` 在前端 mount `PreferencesPanel` 时一次性 `setAddress` 到 `chatStore.address`，第二次打开页面恢复用户上次保存的地址（修复 M1 落地后用户每次都要重新输入地址的 bug） |