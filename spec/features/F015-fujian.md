# F015 — 闽菜专家

> **状态**：[x] 已完成（M1 Phase 1 — GREEN；stub prompt 片段补齐 §4 闽南 / 沙茶关键词生成规则 + 与粤菜的海鲜区分澄清 + 过敏原注意；新增 `backend/tests/unit/test_fujian_expert.py` 覆盖 §2 / §6 验收点）
> **所属里程碑**：M1 Agent MVP
> **依赖**：[F003](F003-cuisine-expert-contract.md)、[F030](F030-amap-restaurant-search.md)

## 1. 用户故事

作为闽菜专家 Node，推荐以海鲜、清汤、细巧著称的福建菜系，重点佛跳墙、海蛎煎、沙茶面。

## 2. 验收清单

- [x] `cuisine_id="fujian"`
- [x] 关键词覆盖：闽菜 / 福建 / 闽南 / 沙茶 / 佛跳墙
- [x] 与粤菜的海鲜区分：闽更"汤鲜 + 山珍"，粤更"生猛海鲜"
- [x] 单测覆盖（`tests/unit/test_fujian_expert.py`）

## 3. 代表性菜品

| 类别 | 菜品 |
|---|---|
| 经典 | 佛跳墙、海蛎煎、沙茶面、闽南春卷、荔枝肉 |
| 汤 | 鸡汤汆海蚌 |
| 小吃 | 沙茶面、福州鱼丸 |

## 4. Prompt 关键提示

```text
你是闽菜推荐专家。

【该菜系要点】
- 闽菜特点：以海鲜山珍为主，汤品出色，刀工巧妙
- 与粤菜区别：闽菜更"汤鲜 + 山珍"，粤菜更"生猛海鲜"
- 过敏原注意：海蛎煎 / 海蚌含贝类过敏原
- 关键词生成：包含"闽菜 / 福建 / 闽南"中的 1-2 个 + 1 个代表菜
```

## 5. 数据 / 接口变更

- 新增实现：`backend/app/agents/cuisines/stubs/fujian.py`（继承 F003 `BaseCuisineExpert`，与其它 13 个菜系 stub 同目录）
- 无新增数据库表 / REST 接口

## 6. 测试计划

- [x] `test_fujian_expert.py`：用户输入"闽南 / 沙茶" → 关键词含"闽菜"（通过 build_prompt 上下文验证，不接 LLM）
- [x] `test_fujian_expert.py`：用户输入"福建菜" → prompt 含"福建"菜系词 + 代表菜
- [x] `test_fujian_expert.py`：用户输入"沙茶" → prompt 优先用"沙茶面"作代表菜
- [x] `test_fujian_expert.py`：prompt 片段含全部 5 个菜系词（闽菜 / 福建 / 闽南 / 沙茶）+ 佛跳墙 + ≥3 道 F015 §3 代表菜 + 与粤菜的海鲜区分（闽"汤鲜 + 山珍" vs 粤"生猛海鲜"）+ 至少 1 个过敏原提示词
- [x] `test_fujian_expert.py`：parse_output 透传 happy path 与非法 JSON fallback