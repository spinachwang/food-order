# F040 — 总结与推荐 Agent

> **状态**：[ ] 未开始
> **所属里程碑**：M1 Agent MVP
> **依赖**：[F001 偏好](F001-user-preferences.md)、[F003 菜系专家契约](F003-cuisine-expert-contract.md)、[F031 天气](F031-amap-weather.md)
> **被依赖**：[F021 整体工作流](F021-langgraph-workflow.md)

## 1. 用户故事

作为 LangGraph 工作流的总结 Agent，我希望聚合所有上游节点输出（菜系专家结论、餐厅列表、天气、用户偏好），给出一个**结构化、可执行、有理由**的最终推荐：今天吃哪家 / 要不要点外卖 / 为什么 / 还有啥备选。

## 2. 验收清单

- [ ] 输入：菜系专家输出（≥0 个）+ 天气 + 偏好
- [ ] 输出：`Recommendation` 对象（headline / restaurant_id / order_takeout / reason / alternatives）
- [ ] 决策规则（基于天气 + 距离）决定是否外卖：
  - 天气恶劣（雨 / 雪 / 沙尘 / 风 ≥6 级）或温度 ≥35℃ / ≤-5℃ → 倾向 `order_takeout=true`
  - 餐厅距离 ≤500m 且天气良好 → 倾向 `order_takeout=false`
  - 其他情况 → 默认 `order_takeout=true`（中庸之选）
- [ ] 备选 ≥2 个（fallback 方案）
- [ ] 输出 `reason` 含可解释依据（天气 / 距离 / 偏好 / 评分）
- [ ] 全部菜系专家失败时降级输出："今天没合适推荐，换个口味吧"
- [ ] 单测覆盖所有决策分支

## 3. 输入 / 输出

### 3.1 输入

```python
class SummaryAgentInput(TypedDict):
    user_message: str
    user_preferences: UserPreferences         # F001
    cuisine_results: list[CuisineExpertOutput]  # F003，可能为空
    restaurant_lists: dict[str, list[Restaurant]]  # cuisine_id → 餐厅列表
    weather: WeatherInfo | None              # F031
```

### 3.2 输出

```python
class Recommendation(TypedDict):
    headline: str                            # "今天推荐：蜀香苑（川菜）"
    cuisine_id: str
    restaurant_id: str                       # 高德 POI ID
    restaurant_name: str
    order_takeout: bool                      # 是否建议点外卖
    reason: str                              # "天气晴朗，距您 380m，步行 5 分钟可达"
    confidence: float                        # 0.0-1.0
    alternatives: list[AltRecommendation]    # ≥2 个备选

class AltRecommendation(TypedDict):
    cuisine_id: str
    restaurant_id: str
    restaurant_name: str
    short_reason: str                        # 备选的一句话理由
```

### 3.3 决策矩阵（`order_takeout`）

| 天气 | 距离 ≤500m | 距离 500-1500m | 距离 >1500m |
|---|---|---|---|
| 晴 / 多云 / 阴 / 风力 ≤5 | false | false | true |
| 小雨 / 风 6 级 | true | true | true |
| 中大雨 / 雪 / 沙尘 / 雾霾 | true | true | true |
| 温度 ≥35℃ / ≤-5℃ | true | true | true |

> 默认距离未知时按 "500-1500m" 处理。

## 4. 评分口径

```python
def score_restaurant(
    restaurant: Restaurant,
    cuisine_output: CuisineExpertOutput,
    preferences: UserPreferences,
) -> float:
    score = 0.0
    # 距离越近越好（≤500m: +0.4, 500-1500: +0.2, >1500: +0.0）
    if restaurant.distance_meters <= 500:
        score += 0.4
    elif restaurant.distance_meters <= 1500:
        score += 0.2
    # 评分（>4.5: +0.3, 4.0-4.5: +0.2, 3.5-4.0: +0.1, 缺失: 0）
    if restaurant.rating is not None:
        if restaurant.rating >= 4.5: score += 0.3
        elif restaurant.rating >= 4.0: score += 0.2
        elif restaurant.rating >= 3.5: score += 0.1
    # 菜系偏好加成（cuisine_weights × 0.3）
    score += preferences.cuisine_weights[cuisine_output.cuisine_id] * 0.3
    return score
```

`recommendation` 取 score 最高的；`alternatives` 取 score 2/3 名（按 cuisine_id 多样性优先）。

## 5. Prompt 模板

```text
你是"午餐决策助手"的总结 Agent。基于上游所有信息给出最终推荐。

【用户偏好】
{preferences_summary}

【天气】
{weather_summary}

【菜系专家结论】
{cuisine_results_summary}      # 每条: conclusion + 餐厅列表前 3

【决策矩阵】
{decision_matrix_table}       # 见 §3.3

【任务】
1. 选出 score 最高的 1 家作为主推荐
2. 给出 ≥2 个备选（不同菜系优先）
3. 输出 `reason`：≤50 字，引用天气 / 距离 / 偏好 / 评分
4. 决定 `order_takeout`：基于决策矩阵

【输出格式】严格 JSON：
{
  "headline": "...",
  "cuisine_id": "...",
  "restaurant_id": "...",
  "restaurant_name": "...",
  "order_takeout": true|false,
  "reason": "...",
  "confidence": 0.85,
  "alternatives": [
    {"cuisine_id": "...", "restaurant_id": "...", "restaurant_name": "...", "short_reason": "..."},
    ...
  ]
}
```

## 6. 数据 / 接口变更

- 不新增表 / 接口
- 新增实现：`backend/app/agents/summary.py`
- 新增打分函数：`backend/app/agents/scoring.py`

## 7. 错误码

| code | 含义 | 处理 |
|---|---|---|
| `NO_RESTAURANTS` | 所有菜系专家返回餐厅为空 | 输出降级："今天没合适推荐，换个口味吧" |
| `ALL_ALLERGIES_CONFLICT` | 推荐餐厅与忌口 100% 冲突 | 切到备选 + reason 标注 |
| `WEATHER_UNAVAILABLE` | 天气 API 失败 | 用默认"未知天气"走决策矩阵中庸档 |

## 8. 测试计划

### 单元测试（`backend/tests/unit/test_summary_agent.py`）

- [ ] 决策矩阵：晴天 + 距离 300m → `order_takeout=false`
- [ ] 决策矩阵：雨天 + 距离 300m → `order_takeout=true`
- [ ] 决策矩阵：温度 38℃ → `order_takeout=true`
- [ ] 评分：评分 4.8 + 距离 200m + 偏好 0.9 → score ≥ 0.95
- [ ] 备选：≥2 个，且 cuisine_id 与主推荐不同（若可能）
- [ ] 全部菜系失败 → 降级 message

### 集成测试

- [ ] 完整 State 流转：mock 2 个菜系专家 + mock 天气 → 输出 recommendation
- [ ] 天气 API 失败 → 默认决策可用

### 端到端（Playwright）

- [ ] 不直接测；由 F021 覆盖

## 9. 待澄清问题

- 决策矩阵的边界值（如温度 34.9℃ vs 35.1℃）是否要做平滑？M1 用硬阈值
- 备选是否要求不同菜系？默认是（增强多样性）
- `confidence` 字段是否暴露给前端？默认**暴露**，用于排序展示