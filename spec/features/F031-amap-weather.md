# F031 — 高德 MCP 天气查询

> **状态**：[ ] 未开始
> **所属里程碑**：M1 Agent MVP
> **依赖**：无（基础服务封装）
> **被依赖**：F040（总结 Agent 用天气决定"是否点外卖"）

## 1. 用户故事

作为总结 Agent，我希望在生成推荐前快速拿到用户当前位置的天气信息（温度、天气状况、降水概率、风力），用于决策"今天适合出门吃饭还是点外卖"。

## 2. 验收清单

- [ ] 提供 `amap_get_weather(location)` 工具封装
- [ ] 调用 1 秒内返回
- [ ] 返回字段：当前温度 / 天气状况（晴雨雪雾霾）/ 未来 3 小时预报 / 降水概率 / 风力
- [ ] 错误码透传：`AMAP_INVALID_KEY` / `AMAP_QUOTA_EXCEEDED` / `AMAP_NETWORK_ERROR`
- [ ] 单测覆盖：mock 高德返回 → 字段解析正确

## 3. 输入 / 输出

### 3.1 输入

```python
class WeatherQueryInput(TypedDict):
    location: str                        # 地标 / 经纬度
```

### 3.2 输出

```python
class WeatherInfo(TypedDict):
    location: str
    temperature_celsius: float           # 当前温度
    condition: Literal["sunny", "cloudy", "rainy", "snowy", "foggy", "dust"]
    humidity_percent: int                # 0-100
    wind_level: int                      # 0-12（蒲福风级）
    precipitation_probability: float     # 0.0-1.0（未来 3 小时）
    forecast_3h: list[dict]              # 未来 3 小时逐小时：[{hour, temp, condition, pop}]
    fetched_at: datetime
```

## 4. 工具调用约定

```python
@tool
async def amap_get_weather(location: str) -> WeatherInfo:
    """调用高德 MCP /v3/weather/weatherInfo。
    location 优先使用经纬度字符串 "lng,lat"，其次是高德可解析的地标名。
    """
```

## 5. 错误码

| code | 含义 | 处理 |
|---|---|---|
| `AMAP_INVALID_KEY` | API key 无效 | 启动时 fail-fast |
| `AMAP_QUOTA_EXCEEDED` | 配额耗尽 | 返回错误事件 |
| `AMAP_NETWORK_ERROR` | 网络超时 | 工具层重试 1 次 |
| `AMAP_LOCATION_INVALID` | 地标无法解析 | 用 IP 城市兜底 |

## 6. 配置

复用 F030 的 `AMAP_API_KEY`；不新增字段。

## 7. 数据 / 接口变更

- 不新增数据库表
- 不新增 REST 接口
- 新增模块：`backend/app/mcp/amap/weather.py`

## 8. 测试计划

### 单元测试

- [ ] mock 晴天返回 → `condition="sunny"`、`pop=0.05`
- [ ] mock 雨天返回 → `condition="rainy"`、`pop=0.85`
- [ ] mock 无效 location → 抛 `AMAP_LOCATION_INVALID`
- [ ] mock 429 → 重试后抛 `AMAP_QUOTA_EXCEEDED`

### 集成测试

- [ ] 真实调用高德天气 API：返回字段齐全
- [ ] 错误降级：天气 API 失败时 summary agent 用默认"未知天气 → 中性推荐"

### 端到端（Playwright）

- [ ] 不直接测；由 F021 覆盖

## 9. 待澄清问题

- 高德天气 API 是否覆盖用户所在地？默认国内城市
- 风力 / 湿度是否真的影响"是否外卖"决策？F040 会定义阈值
- 是否需要预报未来 24 小时？M1 仅 3 小时预报够用