# F017 — 徽菜专家

> **状态**：[x] 已完成（M1 Phase 1 — GREEN；stub prompt 片段补齐 §4 徽"咸鲜 + 重油 + 山珍腊味" vs 川"麻辣" vs 湘"香辣腊味"边界澄清 + 经典 / 腊味两类菜品候选 + 过敏原注意 + 关键词生成规则；新增 `backend/tests/unit/test_anhui_expert.py` 覆盖 §2 / §6 验收点）
> **所属里程碑**：M1 Agent MVP
> **依赖**：[F003](F003-cuisine-expert-contract.md)、[F030](F030-amap-restaurant-search.md)

## 1. 用户故事

作为徽菜专家 Node，推荐以"重油、腊味、徽州"为特色的安徽菜系，与川菜的"麻辣"、湘菜的"香辣腊味"做明确区分。

## 2. 验收清单

- [x] `cuisine_id="anhui"`
- [x] 关键词覆盖：徽菜 / 安徽 / 徽州 / 臭鳜鱼
- [x] 与川菜 / 湘菜的辣度区分：徽偏"咸鲜 + 重油"，无辣或微辣
- [x] 单测覆盖（`tests/unit/test_anhui_expert.py`）

## 3. 代表性菜品

| 类别 | 菜品 |
|---|---|
| 经典 | 臭鳜鱼、毛豆腐、火腿炖甲鱼、徽州毛豆腐、问政山笋 |
| 腊味 | 徽州腊肉、刀板香 |

## 4. Prompt 关键提示

```text
你是徽菜推荐专家。

【该菜系要点】
- 徽菜特点：重油、重色、擅用火腿与山珍，徽州山区特色
- 与川菜区别：徽偏咸鲜不辣，川偏麻辣
- 与湘菜区别：徽偏山珍腊味，湘偏香辣腊味
- 关键词生成：包含"徽菜 / 安徽 / 徽州"中的 1-2 个 + 1 个代表菜（"臭鳜鱼"）
```

## 5. 数据 / 接口变更

- 新增实现：`backend/app/agents/cuisines/stubs/anhui.py`（继承 F003 `BaseCuisineExpert`，与其它 13 个菜系 stub 同目录；§5 原路径 `cuisines/anhui.py` 为笔误，实际与 F010-F016 一致落在 `stubs/`）
- 无新增数据库表 / REST 接口

## 6. 测试计划

- [x] `test_anhui_expert.py`：用户输入"徽州" → prompt 同时含"徽菜" + "安徽" + "徽州"三菜系词候选 + 与川菜/湘菜的辣度区分澄清 + 至少 1 道 §3 经典代表菜（通过 build_prompt 上下文验证，不接 LLM）—— 让 F017 在徽州/安徽/徽菜场景都能命中
- [x] `test_anhui_expert.py`：用户输入"咸鲜" → prompt 显式标注"麻辣" vs "香辣"对照——让 F017 优先于 F010 / F016
- [x] `test_anhui_expert.py`：用户输入"徽菜" / "安徽菜" → prompt 把对应菜系词作为候选 + 至少 1 道 §3 经典代表菜
- [x] `test_anhui_expert.py`：用户输入"臭鳜鱼" → prompt 把"臭鳜鱼"作为代表菜候选 + 菜系词候选
- [x] `test_anhui_expert.py`：prompt 片段含全部 4 个菜系词（徽菜 / 安徽 / 徽州 / 臭鳜鱼）+ ≥3 道 §3 经典菜 + ≥1 道腊味菜 + 与川菜/湘菜的辣度区分（徽"咸鲜 + 重油" vs 川"麻辣" vs 湘"香辣"）+ 至少 1 个过敏原提示词（pork / 火腿 / 腊肉）
- [x] `test_anhui_expert.py`：parse_output 透传 happy path 与非法 JSON fallback；徽菜专属字段（臭鳜鱼 / 徽州腊肉 / 刀板香 / 咸鲜）正确归位
- [x] 集成：与川菜并行时不冲突（注册表共存 + prompt 隔离；`test_anhui_expert.py::TestAnhuiParallelSafety`）