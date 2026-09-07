# F018 — 日料专家

> **状态**：[x] 已完成（M1 Phase 1 — GREEN；stub prompt 片段补齐 §4 三大代表（寿司 / 刺身 / 拉面）+ 与 F020 西式快餐的边界澄清（便利店日式便当归 F020）+ 面食 / 炸物 / 套餐三类代表菜 + 过敏原注意（刺身含 shellfish / fish，拉面含小麦 / 蛋 / 麸质）+ 关键词生成规则；新增 `backend/tests/unit/test_japanese_expert.py` 覆盖 §2 / §6 验收点；新增 `scripts/japanese.py` 冒烟脚本验证契约）
> **所属里程碑**：M1 Agent MVP
> **依赖**：[F003](F003-cuisine-expert-contract.md)、[F030](F030-amap-restaurant-search.md)

## 1. 用户故事

作为日料专家 Node，推荐寿司、刺身、拉面、天妇罗、鳗鱼饭等正餐日料（不含便利店便当，归西式快餐）。

## 2. 验收清单

- [x] `cuisine_id="japanese"`
- [x] 关键词覆盖：日料 / 日本料理 / 寿司 / 刺身 / 拉面
- [x] 与西式快餐的边界：本 Node 推正餐日料；便利店便当归 F020
- [x] 单测覆盖

## 3. 代表性菜品

| 类别 | 菜品 |
|---|---|
| 寿司 / 刺身 | 寿司、刺身、鳗鱼饭、亲子丼 |
| 面 | 拉面、乌冬、荞麦面 |
| 炸物 | 天妇罗、可乐饼 |
| 套餐 | 鳗鱼饭、牛丼 |

## 4. Prompt 关键提示

```text
你是日料推荐专家。

【该菜系要点】
- 日料特点：生鲜、刀工、季节感；寿司 / 刺身 / 拉面是三大代表
- 与西式快餐的边界：本 Node 推荐正餐日料店；便利店日式便当归 F020 西式快餐
- 过敏原注意：刺身 / 海鲜类含贝类、鱼过敏原；部分拉面含小麦 + 蛋
- 关键词生成：包含"日料 / 日本料理"中的 1 个 + 1 个代表菜（"寿司"、"拉面"、"刺身"）+ 1 个风味词（"和风"、"生鲜"）
```

## 5. 数据 / 接口变更

- 增强实现：`backend/app/agents/cuisines/stubs/japanese.py`（继承 F003 `BaseCuisineExpert`）
- 无新增数据库表 / REST 接口

## 6. 测试计划

- [x] `test_japanese_expert.py`：用户输入"想吃寿司" → prompt 同时含"日料" / "日本料理" / "寿司" / "刺身" / "拉面"五关键词 + 与西式快餐的边界澄清（含"便利店"或"便当"）+ 风味词"和风"
- [x] `test_japanese_expert.py`：用户输入"想吃拉面" → prompt 把"拉面"作为代表菜候选 + 含过敏原提示（小麦 / 蛋 / 麸质）
- [x] `test_japanese_expert.py`：用户输入"想吃便利店便当" → prompt 把便利店场景显式推给 F020 西式快餐
- [x] `test_japanese_expert.py`：用户输入"想吃日本料理" → prompt 把"日本料理"作为菜系词候选
- [x] `test_japanese_expert.py`：prompt 片段含全部 5 个菜系词（日料 / 日本料理 / 寿司 / 刺身 / 拉面）+ 面食 ≥2 + 炸物 ≥1 + 套餐 ≥1 + 三大代表显式标注 + 与西式快餐边界（含"便利店"或"便当"）+ 至少 1 个过敏原提示词（贝类 / 鱼 / 海鲜 / 小麦 / 蛋 / 麸质）
- [x] `test_japanese_expert.py`：parse_output 透传 happy path 与非法 JSON fallback；日料专属字段（寿司 / 刺身 / 拉面 / 和风）正确归位
- [x] 集成：与西式快餐（F020）并行时不冲突（注册表共存 + prompt 隔离；`test_japanese_expert.py::TestJapaneseParallelSafety`）