# F016 — 湘菜专家

> **状态**：[x] 已完成（M1 Phase 1 — GREEN；stub prompt 片段补齐 §4 湘"香辣 + 腊味" vs 川"麻辣 + 花椒"边界澄清 + 腊味 / 经典 / 小吃三类菜品候选 + 过敏原注意；新增 `backend/tests/unit/test_hunan_expert.py` 覆盖 §2 / §6 验收点）
> **所属里程碑**：M1 Agent MVP
> **依赖**：[F003](F003-cuisine-expert-contract.md)、[F030](F030-amap-restaurant-search.md)

## 1. 用户故事

作为湘菜专家 Node，推荐以"香辣、腊味"著称的湖南菜系，与川菜的"麻辣"做明确区分。

## 2. 验收清单

- [x] `cuisine_id="hunan"`
- [x] 关键词覆盖：湘菜 / 湖南 / 剁椒 / 腊味
- [x] 与川菜的辣度区分：川偏"麻"，湘偏"香辣"
- [x] 单测覆盖（`tests/unit/test_hunan_expert.py`）

## 3. 代表性菜品

| 类别 | 菜品 |
|---|---|
| 经典 | 剁椒鱼头、毛氏红烧肉、湘西外婆菜、农家小炒肉 |
| 腊味 | 腊肉、腊鱼、腊鸡 |
| 小吃 | 臭豆腐、糖油粑粑 |

## 4. Prompt 关键提示

```text
你是湘菜推荐专家。

【该菜系要点】
- 湘菜特点：香辣为主，擅用腊味、剁椒，乡土气息浓
- 与川菜区别：湘偏"香辣 + 腊味"，川偏"麻辣 + 花椒"；用户说"想吃辣的"两者都可，但说"香辣"则优先湘
- 关键词生成：包含"湘菜 / 湖南"中的 1 个 + 1 个代表菜（"剁椒鱼头"、"腊味"）+ 1 个风味词（"香辣"）
```

## 5. 数据 / 接口变更

- 新增实现：`backend/app/agents/cuisines/stubs/hunan.py`（继承 F003 `BaseCuisineExpert`，与其它 13 个菜系 stub 同目录）
- 无新增数据库表 / REST 接口

## 6. 测试计划

- [x] `test_hunan_expert.py`：用户输入"想吃辣的" → prompt 同时含"湘菜" + "川菜"区分 + "香辣"风味词（通过 build_prompt 上下文验证，不接 LLM）—— 让 F016 与 F010 都能命中"辣"字场景
- [x] `test_hunan_expert.py`：用户输入"香辣" → prompt 显式标注"麻辣"对照——让 F016 优先于 F010
- [x] `test_hunan_expert.py`：用户输入"湘菜" / "湖南" → prompt 把对应菜系词作为候选 + 至少 1 道 §3 经典代表菜
- [x] `test_hunan_expert.py`：用户输入"剁椒" / "腊味" → prompt 把"剁椒鱼头" / 腊味代表菜作为候选
- [x] `test_hunan_expert.py`：prompt 片段含全部 4 个菜系词（湘菜 / 湖南 / 剁椒 / 腊味）+ 剁椒鱼头 + ≥3 道 §3 经典菜 + ≥1 道腊味菜 + 与川菜的辣度区分（湘"香辣" vs 川"麻辣"）+ 至少 1 个过敏原提示词
- [x] `test_hunan_expert.py`：parse_output 透传 happy path 与非法 JSON fallback