# F030 — 高德 MCP 周边搜索（餐厅）

> **状态**：[x] 已完成（M1 Agent MVP — GREEN）
> **所属里程碑**：M1 Agent MVP
> **依赖**：无（基础服务封装）
> **被依赖**：F003（菜系专家调用）、F040（总结 Agent 二次过滤）

## 1. 用户故事

作为菜系专家 Node，我希望通过统一接口调用高德 MCP 搜索附近餐厅，传入关键词 + 锚点 + 半径，返回结构化餐厅列表（含 POI ID、名称、距离、评分、价格段），由我挑选前 3 家推荐。

## 2. 验收清单

- [ ] 提供 LangChain Tool 风格的封装 `amap_search_restaurants`
- [ ] 每次调用 1.5 秒内返回（高德 SLA 1 秒 + 解析 0.5 秒）
- [ ] 返回 ≥3 家餐厅；不足 3 家时返回所有可用 + 标记 `partial=true`
- [ ] 自动按"距离 + 评分"排序，距离超 3km 的剔除
- [ ] 错误码透传：`AMAP_QUOTA_EXCEEDED` / `AMAP_INVALID_KEY` / `AMAP_NETWORK_ERROR`
- [ ] 单测覆盖：mock 高德返回 → 解析正确；mock 空结果 → 抛 `partial` 标记

## 3. 输入 / 输出

### 3.1 输入

```python
class RestaurantSearchInput(TypedDict):
    keywords: list[str]                 # 1-5 个关键词（来自 F003 菜系专家）
    location: str                        # 锚点（地标 / 写字楼 / 经纬度字符串）
    radius_meters: int = 1500           # 默认 1.5km
    min_rating: float = 3.5              # 最低评分
    max_results: int = 10                # 上限
```

### 3.2 输出

```python
class Restaurant(TypedDict):
    poi_id: str                          # 高德 POI ID
    name: str
    address: str
    distance_meters: int
    rating: float                        # 高德评分（若无则 None）
    avg_price: Decimal | None            # 人均价格（元）
    cuisine_tags: list[str]              # 高德返回的 tags
    location: tuple[float, float]        # 经纬度

class RestaurantSearchResult(TypedDict):
    restaurants: list[Restaurant]        # 长度 0-10，按 distance+rating 排序
    partial: bool                        # 不足 3 家时为 True
    raw_count: int                       # 高德返回的原始条数
```

## 4. 工具调用约定

```python
@tool
async def amap_search_restaurants(
    keywords: list[str],
    location: str,
    radius_meters: int = 1500,
    min_rating: float = 3.5,
    max_results: int = 10,
) -> RestaurantSearchResult:
    """调用高德 MCP /v3/place/around 或 equivalent。
    返回结果按 (距离 / max_distance) + (rating / 5) 加权排序。
    """
```

### 高德 MCP 工具映射

| 菜系专家关键词 | 高德 `types` | 备注 |
|---|---|---|
| 川菜 / 麻辣 / 火锅 | `050000` (餐饮) + keyword | 高德 POI 分类 |
| 粤菜 / 早茶 / 茶餐厅 | `050000` + keyword | |
| 西餐 / 牛排 | `050000` + keyword | |
| 日料 / 寿司 | `050000` + keyword | |
| 小吃 / 快餐 | `050000` + keyword | |
| 甜品 / 咖啡 / 奶茶 | `050000`（甜点子类） | |

> 关键字越具体，高德匹配越好；F003 要求菜系专家输出 3-5 个细粒度关键词（含菜名）。

## 5. 错误码

| code | 含义 | HTTP 等价 | 处理 |
|---|---|---|---|
| `AMAP_INVALID_KEY` | API key 无效 | 401 | 启动时 fail-fast（不应走到这里） |
| `AMAP_QUOTA_EXCEEDED` | 配额耗尽 | 429 | 返回错误事件给前端，提示"稍后再试" |
| `AMAP_NETWORK_ERROR` | 网络/超时 | 5xx | 工具层重试 1 次，仍失败抛错 |
| `AMAP_NO_RESULT` | 关键词无匹配 | 200 | 返回 `restaurants=[]`，标记 `partial=true` |

## 6. 配置

`.env` 新增字段：

```bash
AMAP_API_KEY=your_key_here
AMAP_DEFAULT_RADIUS_METERS=1500
AMAP_TIMEOUT_SECONDS=2.0
```

`.env.example` 同步更新（参考 ADR 0002 文档末尾）。

## 7. 数据 / 接口变更

- 不新增数据库表
- 不新增 REST 接口（仅 LangChain Tool，Agent 内部调用）
- 新增模块：`backend/app/mcp/amap/restaurant.py`
- 新增 mock fixture：`backend/tests/fixtures/amap_restaurant_responses.json`（用于单测）

## 8. 测试计划

### 单元测试（`backend/tests/unit/test_amap_restaurant.py`）

- [ ] mock 高德返回 10 条 → 解析正确，距离 / 评分保留
- [ ] mock 返回 0 条 → `partial=true`，不抛错
- [ ] mock 关键词过滤：含忌口的餐厅被剔除（在 tool 层不做；交由菜系专家）
- [ ] mock 网络超时 → 重试 1 次后抛 `AMAP_NETWORK_ERROR`
- [ ] mock 401 → 抛 `AMAP_INVALID_KEY`

### 集成测试

- [ ] 真实调用高德测试环境（沙箱 key）：返回 ≥3 条 POI
- [ ] 错误响应降级：模拟 429 → summary agent 收到 `partial=true`，推荐措辞调整

### 端到端（Playwright）

- [ ] 不直接测；由 F004 覆盖

## 9. 待澄清问题

- 高德 MCP 工具是否已经接入？若未接入，先用 `httpx` 直连 `https://restapi.amap.com/v3/place/around` 兜底
- 是否需要在结果中携带菜单 / 推荐菜？高德 API 不直接给菜单，由 F003 菜系专家基于餐厅名 + tags 推断
- 评分字段缺失时（很多店没有）如何处理？默认降权，不剔除