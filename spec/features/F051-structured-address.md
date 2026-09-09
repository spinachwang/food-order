# F051 — 结构化地址选择器（替代 window.prompt）

> **状态**：[ ] 未开始
> **所属里程碑**：M1 Agent MVP（M1 落地）
> **依赖**：[F001 §3.5 默认位置](F001-user-preferences.md)、[F030 高德周边搜索](F030-amap-restaurant-search.md)、[F031 高德天气](F031-amap-weather.md)、[F050 §2.4 addr-edit 按钮](F050-chat-shell.md)
> **被依赖**：F050（addr-edit 弹层改用本 spec 的选择器）；F001 §3.5（`default_location` 字段类型变更）

> **背景**：[F050 §8 #5](F050-chat-shell.md) 原决议是 M1 用 `window.prompt` 凑合、M2 再接高德选址组件。本次升级把选址组件**前移到 M1**：原因（2026-09-08 决议）——
> 1. 当前 `default_location = "上海 · 静安嘉里中心 B2"` 这样的**完整地址字符串**传进 Amap `/v3/weather/weatherInfo` 必然 `AMAP_LOCATION_INVALID`，触发"天气暂不可用"降级（[F031 §2 验收](F031-amap-weather.md) Phase 2 已落地）。要修这条链路，**前端必须能稳定产出 adcode**，而 `window.prompt` 拿不到 adcode。
> 2. F001 §3.5 已规定 `default_location` 合法格式只有 6 位 adcode 或主流城市名；用户手敲完整地址既不安全也不可达。
> 3. M1 的核心 demo 场景（"打开应用 → 看天气 → 推荐"）需要天气能拿得到，否则 [F031](#) 的价值无法体现。

---

## 1. 用户故事

作为办公室打工人，我希望设置默认位置时**按层级挑选**（省 / 城市 / 区 / 街道 / 小区 / 门牌号），而不是手敲一长串地址：

1. 第一次打开应用，agent 给我一个**默认锚点**（基于 IP 城市）；
2. 点 ContextStrip 卡片上的"编辑"按钮 → 弹出一个**分级选择器**：
   - 选城市（顶层下拉，含"使用当前位置"快捷入口） →
   - 选区（下拉，城市变了就重置） →
   - 选街道 / 商圈（搜索框，可跳过） →
   - 选小区 / 楼宇（搜索框，可跳过） →
   - 填门牌号（可选，文字输入） →
   - 点"保存"；
3. 选择后 ContextStrip 显示"城市 · 区 · 小区"摘要；agent 立即能用新位置拿天气；
4. 选择结果**跨刷新保留**，下次打开应用还是这个位置。

---

## 2. 验收清单

### 2.1 UI / 交互

- [ ] ContextStrip 右侧"编辑"按钮 (`data-od-id="addr-edit"`) 调起 `AddressPickerDialog`（**取代** `window.prompt` 与 `editAddress`）
- [ ] 弹窗采用**层叠下拉 / 搜索框**而非级联菜单；每级独立可选（用户可只选城市不选小区）
- [ ] **必选层级**：省 / 城市 / 区（至少这三层才能给 adcode）
- [ ] **可选层级**：街道 / 商圈（POI 关键字搜索，可空）→ 小区 / 楼宇（POI search，可空）→ 门牌号（自由文本，可空）
- [ ] 顶部提供 **"📍 使用当前位置"** 按钮：调 `navigator.geolocation` → 反查 adcode（经纬度 → 区级 adcode），省掉手选；定位失败时降级为 IP 城市兜底
- [ ] 城市列表**首屏渲染** ≤500ms（命中前端缓存 `/config/district` 的国内 **34 个省级单位**：4 直辖市 + 23 省 + 5 自治区 + 2 特别行政区，避开首次选省/直辖市的 API 往返）
- [ ] 区 / 商圈 / 小区**按需懒加载**（用户聚焦输入框时再调高德）
- [ ] 弹窗遵守 F050 §2.6 可访问性：`role="dialog"` + `aria-modal="true"` + `aria-labelledby`；Esc 关闭；点击遮罩关闭；焦点陷阱在第一项
- [ ] 移动端 (≤720px) 弹层改为底部 drawer，键盘推起时滚动容器自适应（沿用 F050 §2.5 响应式原则）

### 2.2 数据契约

- [ ] 后端 Pydantic 新增 `StructuredAddress` 模型（见 §3）；F001 §3.5 `default_location` 字段类型由 `str | None` 升级为 `StructuredAddress | None`
- [ ] GET / PUT /api/v1/preferences 的 JSON 示例同步更新（见 [api.md § M1](../../api.md)）
- [ ] data-model.md `user_preferences.default_location` 列由 `VARCHAR(128)` 升级为 `JSON`（沿用 §通用约定 JSON 字段规则）
- [ ] PUT 校验：必填字段非空、长度合规；POI id 与 adcode 通过 §3.3 白名单正则校验
- [ ] **向后兼容**：老数据 `default_location` 是字符串（如 `"国贸三期"`）时，GET 时**统一回填**为 `null`（前端会兜底到 IP 城市），不返 400
- [ ] 不破坏 `location_override`（POST /api/v1/agent/chat 仍接受字符串 adcode / 城市名）

### 2.3 行为契约

- [ ] 用户首次打开应用（无偏好）→ 后端 IP 城市兜底（"北京" / "上海" 等）→ 前端从 IP 城市反查 adcode → 写入 `default_location` 草稿
- [ ] 用户保存结构化地址 → 立即 PUT /api/v1/preferences（不再走 `addr-edit → location_override` 这条单次覆盖路径）
- [ ] 用户点 `ask-agent` → POST /api/v1/agent/chat **不传 `location_override`** → 后端从 `default_location` 取 adcode
- [ ] F030 `search_restaurants` / F031 `fetch_weather` 直接读 `default_location.city_adcode`（避免字符串解析回退）
- [ ] ContextStrip 摘要显示规则：
  - 城市 + 区 → `"上海 · 静安区"`
  - 加小区 → `"上海 · 静安区 · 静安嘉里中心"`
  - 加门牌号 → `"上海 · 静安区 · 静安嘉里中心 · B2"`

### 2.4 可访问性 / 错误降级

- [ ] 加载高德区划失败 → 弹窗内提示"城市数据加载中，请稍候"+ 自动重试 1 次；最终失败时弹窗拒绝打开并 toast
- [ ] `navigator.geolocation` 拒绝 / 失败 → toast"未获取到位置，已使用默认城市"；弹窗仍可手动选
- [ ] 表单提交校验失败 → 红色 toast + 红边字段；不调后端
- [ ] 网络断开时保存 → toast"网络断了，地址未保存"+ 草稿暂存 `localStorage`

---

## 3. 数据模型

### 3.1 后端 Pydantic

```python
class StructuredAddress(BaseModel):
    """用户结构化默认地址；前端选址组件的最终产出。

    字段约束与高德 Amap API 兼容：
    - city_adcode / district_adcode: 6 位字符串
    - street / community: 人类可读中文，限长
    - poi_id: 高德 POI 唯一 id (B0FF... 形式)
    - door_no: 自由文本门牌号（"B2 楼 305" 等）
    """
    province: str                # 省级名称 ("上海市" / "北京市" / "广东省")
    province_adcode: str         # 6 位省级 adcode ("310000")
    city: str                    # 市级名称 ("上海市" / "广州市")
    city_adcode: str             # 6 位市级 adcode ("310100") — Amap weather 用的锚点
    district: str | None = None  # 区级名称 ("静安区")；直辖市可省
    district_adcode: str | None  # 6 位区级 adcode ("310106") — Amap place/around 用的锚点
    street: str | None = None    # 街道 / 商圈名称 (人类可读，不入 Amap 查询)
    community: str | None = None # 小区 / 楼宇名称
    poi_id: str | None = None    # 高德 POI id (B0FF... 形式)，用于精确锚点
    door_no: str | None = None   # 门牌号 / 楼层 / 房间号 (自由文本)
```

### 3.2 字段约束（白名单正则）

| 字段 | 约束 |
|---|---|
| `province_adcode` / `city_adcode` / `district_adcode` | `^[0-9]{6}$` |
| `poi_id` | `^[A-Z0-9]{8,32}$`（高德 POI id 形如 `B0I6KCBRAM` / `B0FFGKABCD1234567890`，实际长度 8-12 为主，长 id 是早期风格的遗留） |
| `province` / `city` / `district` / `street` / `community` | 中文 / 字母 / 数字 / 空格 / `·`，长度 ≤ 32 |
| `door_no` | 任意字符，长度 ≤ 64 |

### 3.3 Adcode 来源

- 省级 / 市级 / 区级 adcode 来自高德 `/v3/config/district`（`subdistrict=3`）
  - **首屏缓存**：前端内置硬编码 34 个省级单位（4 直辖市 + 23 省 + 5 自治区 + 2 特别行政区），作为 `useDistrictList()` 首屏命中；用户切到第二级时再请求 `/v3/config/district?keywords=省份&subdistrict=1` 拿省下的市列表，再请求 `keywords=市&subdistrict=1` 拿区列表
- POI id / 名称来自 F030 已实现的 `place/text` 关键字搜索

### 3.4 F001 `default_location` 字段升级

`UserPreferences.default_location` 由 `str | None` 升级为 `StructuredAddress | None`。详见 F001 §3.5 修订。

---

## 4. UI / 交互

### 4.1 弹窗布局（桌面端）

```
┌─────────────────────────────────────────────────────────┐
│ 📍 选择你的默认位置                                  ✕  │
├─────────────────────────────────────────────────────────┤
│ [📍 使用当前位置]   ← geolocation 按钮                  │
│                                                         │
│ 省   ┌──────────────┐                                   │
│      │ 上海市    ▾  │                                   │
│      └──────────────┘                                   │
│ 市   ┌──────────────┐                                   │
│      │ 上海市    ▾  │                                   │
│      └──────────────┘                                   │
│ 区   ┌──────────────┐                                   │
│      │ 静安区    ▾  │                                   │
│      └──────────────┘                                   │
│ 商圈 ┌──────────────────────────────┐                  │
│      │ 搜索街道 / 商圈 (可选)       │                  │
│      └──────────────────────────────┘                  │
│ 小区 ┌──────────────────────────────┐                  │
│      │ 搜索小区 / 楼宇 (可选)       │                  │
│      └──────────────────────────────┘                  │
│ 门牌 ┌──────────────────────────────┐                  │
│      │ 楼栋 / 楼层 / 房间号 (可选)  │                  │
│      └──────────────────────────────┘                  │
│                                                         │
│ 摘要: 上海 · 静安区 · 静安嘉里中心 · B2                  │
│                                                         │
│                              [取消]   [保存]            │
└─────────────────────────────────────────────────────────┘
```

### 4.2 关键交互

| 触发 | 行为 |
|---|---|
| 打开弹窗 | 拉取省/市/区三级 adcode（先查 cache）→ 表单渲染 |
| 改省 → 市自动重置；改市 → 区/商圈/小区全部清空 | 字段级联失效 |
| 商圈搜索框聚焦 / 输入 | 调高德 `place/text?types=商圈&city=adcode`（300ms debounce） |
| 小区搜索框聚焦 / 输入 | 调高德 `place/text?types=商务住宅&city=adcode` |
| POI 选中 | 写入 `community` + `poi_id` |
| 点"使用当前位置" | `navigator.geolocation` → 经纬度 → 高德 `regeo` 拿 adcode → 自动填城市+区 |
| 点"保存" | 前端 zod 校验 → PUT /api/v1/preferences（`default_location` 是结构化对象）→ 关弹窗 + toast"已保存"+ ContextStrip 摘要立即更新 |
| Esc / 点遮罩 / 点"取消" | 关弹窗，不调后端 |

### 4.3 组件拆分（前端）

```
features/chat/components/
├── AddressPickerDialog.tsx        # 顶层 Dialog (role=dialog)
├── AddressPickerDialog.module.css
├── AddressPickerFields.tsx        # 5 级表单字段
├── AddressPickerSummary.tsx       # 实时摘要预览
├── AddressPickerGeolocation.tsx   # "使用当前位置" 按钮 + 错误降级
└── hooks/
    ├── useDistrictList.ts         # 高德 /config/district 缓存 + 懒加载
    ├── usePlaceSearch.ts          # 高德 place/text 搜索 (debounced)
    └── useGeolocation.ts          # navigator.geolocation + regeo
```

### 4.4 替换 `AddressEditPopover`

[F050 §2.4](F050-chat-shell.md) 当前 `AddressEditPopover.tsx`（仅 `window.prompt`）被本 spec 的 `AddressPickerDialog.tsx` 完全替换。`chatStore.address: string`（当前是拼好的摘要字符串）字段**保留但来源改为**"由 `default_location` 反向格式化"（`formatAddressSummary(structured)`）。

### 4.5 前端 hydrate 契约（页面二次打开恢复地址）

> **变更**（2026-09-09）：补全 §4.2 行为表"点保存 → ContextStrip 摘要立即更新"之外的另一条路径——**GET 后前端如何把 `default_location` 落到 `chatStore.address`**，避免 M1 落地后用户每次重新打开页面都要重选地址。

**契约**（与 [F001 §3.5.3](F001-user-preferences.md) 同源，此处给 F051 视角）：

- `PreferencesPanel` mount 时调 `usePreferencesQuery()` 拿到 `remotePrefs`，与同步 `uiPrefs` 共用同一个 `hydrated` flag，一次性 `setAddress(remotePrefs.default_location)`
- 老数据兼容回填（DB 里仍是字符串 → GET 返回 `null`） → `setAddress(null)` 是 no-op，`ContextStrip` 显示兜底字符串
- 同次会话 `AddressPickerDialog.onSave` 里**额外**调 `setAddress(parsed.data)`（§4.2 行为表第 4 行），PUT 失败的 catch 分支**不**调 setAddress，保证 UI 与服务端一致

**测试**（`frontend/src/features/chat/components/PreferencesPanel.test.tsx`）：

- `GET` 返回 `default_location: null` → mount 后 `chatStore.address === null`
- `GET` 返回完整结构化对象 → mount 后 `chatStore.address` 等于该对象（验证 `city_adcode` / `poi_id` / `longitude` 等关键字段都已传递）
- 同一 `hydrated` flag 控制：`setAddress` 与 `setUiPrefs` 在同一帧执行，避免出现"uiPrefs 已恢复但 address 还没"的不一致中间态

**不实现**（划界）：

- ❌ `chatStore` `zustand/middleware/persist` —— chatStore 设计为不持久化（[chatStore.ts](../../frontend/src/stores/chatStore.ts)），靠每次 mount GET + 本契约恢复
- ❌ WebSocket / SSE push 后端地址变更 —— M1 单 tab 场景够用；保存侧已即时 `setAddress`
- ❌ `App.tsx` 顶层 `prefetchQuery(['preferences'])` —— 优化项，挪到 M1 验收后再决定（chatStore 默认 null 的兜底已可用）

---

## 5. 高德 MCP 新增 / 复用接口

### 5.1 新增：`backend/app/mcp/amap/district.py`

封装 `/v3/config/district`：

```python
@tool
async def amap_get_district(
    keywords: str | None = None,
    subdistrict: Literal[0, 1, 2, 3] = 1,
) -> list[DistrictInfo]:
    """拉取行政区划树。

    keywords 不传 → 返回省级列表（4 直辖市 + 23 省 + 5 自治区 + 2 特别行政区 = 34 项）
    keywords = "上海市" → 返回上海市下辖区
    subdistrict 控制返回层级深度（0=国 / 1=省 → 市 / 2=省 → 市 → 区 / 3=再下钻 1 级）
    """
```

错误码沿用 F031 §5：复用 `AMAP_INVALID_KEY` / `AMAP_QUOTA_EXCEEDED` / `AMAP_NETWORK_ERROR`；新增 `AMAP_DISTRICT_NOT_FOUND`。

### 5.2 新增：`backend/app/mcp/amap/regeo.py`

封装 `/v3/geocode/regeo`：

```python
@tool
async def amap_regeo(
    location: str,  # "lng,lat"
) -> RegeoInfo:
    """经纬度 → adcode + 行政区划文本。
    用于"使用当前位置"按钮把浏览器坐标转成结构化地址。
    """
```

### 5.3 复用：F030 `place/text`

街道 / 商圈 / 小区 / 楼宇搜索复用 [F030 §3.3](F030-amap-restaurant-search.md) 已实现的 POI 关键字搜索，无需新增 tool，但需要新增 `types` 参数支持：
- `types="商圈"` → 街道 / 商圈候选
- `types="商务住宅|地名地址信息"` → 小区 / 楼宇候选

> 注：[F030 §3.3](F030-amap-restaurant-search.md) 当前 `types` 写死为 `"餐饮服务"`；本 spec 升级 `amap_search_places` 为接受 `types` 参数（向后兼容：缺省 `"餐饮服务"`）。

### 5.4 缓存策略

- 省 / 市列表：前端硬编码首屏缓存 + 后端 Redis 缓存 24h（key: `amap:districts:cn`）
- 区列表：Redis 缓存 24h（key: `amap:districts:{adcode}`）
- POI 搜索结果：不缓存（实时）

---

## 6. 与现有 spec 的集成

### 6.1 F001 §3.5 — `default_location` 字段升级

详见 [F001 §3.5](F001-user-preferences.md) 同步修订：
- 字段类型：`str | None` → `StructuredAddress | None`
- 合法格式表：由"6 位 adcode / 主流城市名"扩展为"结构化对象（含 city_adcode 等必填字段）"
- 校验策略：PUT 严格校验（字段齐全、§3.2 正则放行）— 这是 §3.5 原计划的"M2 升级为严格模式"的**前移**到 M1
- 错误码：新增 `INVALID_STRUCTURED_ADDRESS`（取代 §6 中 `INVALID_LOCATION_FORMAT` 的部分语义）

### 6.2 F030 §3.3 — `amap_search_places` 支持自定义 `types`

接受可选 `types: str | None = None`，缺省 `"餐饮服务"` 保持向后兼容。

### 6.3 F031 §3.1 — `WeatherQueryInput.location`

字段含义从"6 位 adcode 或主流城市名"扩展为"6 位 adcode"（取自 `default_location.city_adcode`）；主流城市名兼容保留。

### 6.4 F040 §3 决策矩阵

`recommendation.location` 字段由 `string`（如 `"国贸三期"`）升级为 `StructuredAddress | null`，供 UI 完整呈现。

### 6.5 F050 §2.4 addr-edit 按钮契约

[F050 §8 #5 决议](F050-chat-shell.md) 由 "M2 接高德选址组件" **前移到 M1**；按钮契约更新为：

| `data-od-id` | M1 行为（修订后） | 备注 |
|---|---|---|
| `addr-edit` | 弹出 `AddressPickerDialog`（F051 §4）；保存 → PUT /api/v1/preferences | 取代原 `window.prompt` |

### 6.6 features.md — 注册 F051

见 features.md 修订。

---

## 7. 错误码

| code | HTTP / 触发 | UI 行为 |
|---|---|---|
| `INVALID_STRUCTURED_ADDRESS` | 400，PUT 时 `default_location` 缺字段或正则不匹配 | 红色 toast + 高亮出错字段 |
| `AMAP_DISTRICT_NOT_FOUND` | 5xx / 高德 `/config/district` 返回空 | 弹窗提示"暂时拿不到城市数据"+ 重试按钮 |
| `AMAP_REGEO_FAILED` | "使用当前位置"按钮 regeo 失败 | toast"未识别你的位置，请手动选城市"+ 弹窗保留打开 |
| `GEOLOCATION_DENIED` | `navigator.geolocation` 拒权 / 失败 | toast"未获取到位置"+ 弹窗保留打开（不弹窗拒绝） |
| `AMAP_QUOTA_EXCEEDED` | 高德配额耗尽 | 弹窗提示"服务繁忙"+ 隐藏搜索框（仍允许用内置城市/区清单保存） |

---

## 8. 测试计划

### 8.1 单元测试

后端：
- [ ] `StructuredAddress` Pydantic 模型：字段缺失 / 正则不匹配 → 抛 `INVALID_STRUCTURED_ADDRESS`
- [ ] `amap_get_district(keywords=None)` mock → 返回 34 项省级
- [ ] `amap_get_district(keywords="上海市", subdistrict=1)` mock → 返回 16 区
- [ ] `amap_regeo("121.43,31.23")` mock → 返回 `{adcode: "310106", district: "静安区"}`
- [ ] `amap_search_places` 带 `types="商圈"` mock → 返回候选列表
- [ ] PUT /api/v1/preferences：合法 `StructuredAddress` → 200；缺 `city_adcode` → 400 `INVALID_STRUCTURED_ADDRESS`

前端：
- [ ] `useDistrictList`：内置 34 项省级首屏命中；切换省级触发市懒加载
- [ ] `usePlaceSearch`：300ms debounce；空查询不调高德
- [ ] `useGeolocation`：成功 / 拒权 / 超时 三种路径
- [ ] `AddressPickerDialog`：级联失效（改市 → 清空下游）+ Esc 关闭 + 焦点陷阱
- [ ] zod schema：合法 / 缺字段 / 字段过长 → 三种结果

### 8.2 集成测试

后端：
- [ ] PUT 合法结构化地址 → GET 返回相同结构化对象
- [ ] PUT 老数据（`default_location = "国贸三期"`） → GET 时 `default_location` 返回 `null`（兼容兜底），不抛 400
- [ ] POST /api/v1/agent/chat 不传 `location_override` → 后端从 `default_location.city_adcode` 查天气（命中 F031 真链路）

前端：
- [ ] `chat_flow.test.tsx` 新增断言：点 `addr-edit` → 弹窗打开 → 选城市 → 保存 → ContextStrip 摘要更新 → 下一次 `ask-agent` 携带新 adcode

### 8.3 端到端（Playwright，`frontend/e2e/`）

- [ ] **`address_picker.spec.ts`**：
  1. `goto('/')` → 点 `addr-edit` → 弹窗打开，断言 34 项省级下拉首屏可见
  2. 选"上海市" → 市自动填"上海市" → 区下拉出现 16 项
  3. 输入"静安"到小区搜索 → 防抖后出现候选 → 选"静安嘉里中心" → 摘要更新
  4. 点"保存" → 弹窗关闭 → ContextStrip 显示新摘要
  5. 点 `ask-agent` → SSE `weather` 事件不再是 `null`（断言 `weather.location` 包含 `"上海"`，且 `temperature_celsius` 是 number 而非 fallback）
- [ ] **`address_geolocation.spec.ts`**：
  1. mock `navigator.geolocation` 返回 `{lat: 31.23, lng: 121.43}` → 点"使用当前位置" → 自动填上海静安 → 不打开搜索
- [ ] **`address_compat.spec.ts`**：
  1. 旧用户（cookie 中已有 `default_location = "国贸三期"`）打开应用 → ContextStrip 显示 IP 城市（"北京"），不报错
- [ ] **`address_persistence.spec.ts`**（2026-09-09 新增，§4.5 契约）：
  1. 走完 `address_picker.spec.ts` 步骤 1-4 → 关闭浏览器 → `goto('/')`（cookie 自动带 x_user_id）→ `ContextStrip` 摘要与上次一致（`city_adcode === "310100"` / `community === "静安嘉里中心"`），不再显示兜底字符串"上海 · 静安嘉里中心 B2"
  2. 旧数据兼容：seed 老字符串 `default_location` 行 → `goto('/')` → `ContextStrip` 显示兜底字符串，无 console error

---

## 9. 待澄清问题

1. **POI 类型过滤范围**：小区搜索的 `types` 字段到底用 `"商务住宅"` 还是 `"地名地址信息"`，或二者合并？两种 API 返回结果差异需实测确认。
2. **首次访问 IP 城市反查**：后端要不要新增 `GET /api/v1/location/ip` 端点？还是前端用免费的 `https://api.ipify.org` + 高德 `regeo`？前者可控，后者少一个端点。
3. **直辖市特殊处理**："上海市"既是省又是市，省级 / 市级 adcode 都是 `310000`。前端表单要不要把省 / 市合并为一个下拉？语义上别扭。
4. **历史地址迁移**：数据库里已有 `default_location = "国贸三期"` 这种字符串记录，要不要写一次迁移脚本批量清空？还是按 §2.2 的"GET 时回填 null"策略走（用户首次访问会看到 IP 城市兜底，下一次保存才会持久化结构化对象）？
5. **港澳台**：当前省列表包含港澳（"香港特别行政区" / "澳门特别行政区"），但 adcode 在高德返回里是 81/82 前缀；与大陆 6 位 adcode 字符串一致，但语义上不同。要不要在 UI 提示？
6. **小区级 POI 是否一定存在**：商业园区（如"张江高科"）可能是 POI，但有些办公楼（如"国贸三期"）才是 POI，"国贸"却不是。用户选不到怎么办？fallback 到区级 adcode 是否可接受？

---

## 10. 变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-08 | 0.1 | 初稿：把 F050 §8 #5 "M2 接高德选址组件"前移到 M1；新增 `StructuredAddress` 模型；F001 `default_location` 升级为结构化对象；新增 `amap_get_district` / `amap_regeo` tool；前端 `AddressPickerDialog` 替换 `AddressEditPopover` |
| 2026-09-09 | 0.2 | **§4.5 前端 hydrate 契约**：补全"GET 后 `default_location` 如何落到 `chatStore.address`"的契约；`PreferencesPanel` mount 时一次性 `setAddress(remotePrefs.default_location)`，第二次打开页面恢复用户上次保存的地址；§8.3 新增 `address_persistence.spec.ts` E2E |