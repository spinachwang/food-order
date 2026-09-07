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

Agent 搜索锚点。由前端 `addr-edit`（F050 §2.4）写入，覆盖到
`location_override`（`POST /api/v1/agent/chat`）。

合法格式（与 `location_override` 共用同一约束）：

| 格式 | 示例 | 备注 |
|---|---|---|
| 6 位数字 adcode | `"110000"` | **推荐**；最稳，Amap 所有相关 API 都收 |
| 主流城市名 | `"北京"` / `"上海"` / `"广州"` | 限省级或直辖市；Amap 可识别 |

非法格式（**不收**，Node 层会兜底到默认城市）：

- 经纬度坐标 `"116.43,39.91"` —— Amap `/v3/weather/weatherInfo` **不收坐标**，会返回空 `lives` → `AMAP_LOCATION_INVALID`
- 区级 / 楼宇级地标 `"国贸"` / `"国贸三期"` —— weather API 同样不识别；F030 `place/around` 虽收但搜索质量差
- 完整地址 `"北京市朝阳区建国门外大街1号"` —— 任何 Amap API 都不直接收

> **设计动机**（2026-09-07 决议）：Amap 两个核心 API 对 location 字段
> 的接受能力不一致 —— `place/around` 收坐标 / adcode / 地标名；
> `weather/weatherInfo` 只收 adcode / 城市名。统一收 adcode + 城市名
> 让 F030 / F031 共用同一锚点解析逻辑，避免 `fetch_weather` Node 默认
> `lng,lat` 触发的 `AMAP_LOCATION_INVALID` bug 重演。

校验 / 兜底策略：

- **PUT /api/v1/preferences** —— 宽松校验：非空、长度 ≤ 128、不匹配坐标正则即放行（避免打断旧用户的 `"国贸"` 偏好；非法格式由 Node 层兜底）
- **POST /api/v1/agent/chat**（`location_override`）—— 同样宽松校验
- **Node 层兜底** —— `fetch_weather.py` / `search_restaurants.py` 发现 `default_location` / `location_override` 是坐标或非城市名时，落回 `_DEFAULT_LOCATION = "110000"`（北京 adcode），并在日志里 `WARNING` 记录触发兜底的 `user_id` 与原始值
- **M2 计划** —— 接入高德选址组件后，由前端保证提交的就是 adcode / 城市名；届时 PUT 校验升级为严格模式，新增 `INVALID_LOCATION_FORMAT` 错误码

## 4. 输入 / 输出（Agent 视角）

```python
class UserPreferences(TypedDict):
    user_id: str
    cuisine_weights: dict[str, float]   # 14 keys, value in [0,1]
    allergies: list[str]                # 0-N elements
    spice_tolerance: int                # 0-3
    temperature_preference: Literal["cold", "room", "hot"]  # F050 §3.4
    default_location: str | None
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
| `INVALID_LOCATION_FORMAT` | default_location / location_override 是坐标或非城市名 | 400 | **M1 暂不触发**（PUT 宽松校验，见 §3.5）；M2 引入严格校验时启用 |

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