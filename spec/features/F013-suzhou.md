# F013 — 苏菜专家

> **状态**：[x] 已完成（M1 Phase 1 — GREEN；新增 `backend/tests/unit/test_suzhou_expert.py` 覆盖 F013 §2 / §4 / §6 验收点；stub prompt 片段补齐 §4 苏浙 / 苏粤 边界澄清 + 过敏原注意 + 关键词生成规则）
> **所属里程碑**：M1 Agent MVP
> **依赖**：[F003](F003-cuisine-expert-contract.md)、[F030](F030-amap-restaurant-search.md)

## 1. 用户故事

作为苏菜专家 Node，推荐以精致、偏甜、刀工讲究著称的江苏菜系。

## 2. 验收清单

- [x] `cuisine_id="suzhou"`
- [x] 关键词覆盖：苏菜 / 江苏 / 苏帮 / 淮扬
- [x] 与浙菜的精致区分：苏更"甜"，浙更"鲜"
- [x] 单测覆盖（`tests/unit/test_suzhou_expert.py`）

## 3. 代表性菜品

| 类别 | 菜品 |
|---|---|
| 经典 | 松鼠鳜鱼、蟹粉狮子头、响油鳝糊、盐水鸭 |
| 淮扬 | 蟹黄汤包、文楼干贝、扬州炒饭 |
| 甜点 | 苏式糕点 |

## 4. Prompt 关键提示

```text
你是苏菜推荐专家。

【该菜系要点】
- 苏菜特点：精致、偏甜、刀工讲究，注重原汁原味
- 与浙菜区别：苏菜偏甜鲜，浙菜偏清淡江浙；用户说"清淡偏甜"优先苏
- 与粤菜区别：粤菜更广式 + 海鲜；苏菜更江淮河鲜
- 关键词生成：包含"苏菜 / 江苏 / 苏帮 / 淮扬"中的 1-2 个 + 1 个代表菜
```

## 5. 数据 / 接口变更

- 新增实现：`backend/app/agents/cuisines/suzhou.py`

## 6. 测试计划

- [x] `test_suzhou_expert.py`：用户输入"精致清淡偏甜" → prompt 含菜系词"苏菜 / 江苏 / 苏帮 / 淮扬"任一 + 与浙菜的区分澄清
- [x] `test_suzhou_expert.py`：prompt 片段含 4 个菜系词全部 + ≥3 道代表菜
- [x] `test_suzhou_expert.py`：parse_output 透传苏菜 happy path 与非法 JSON fallback
- [x] `test_suzhou_expert.py`：与粤菜的区分（"粤菜" + "广式 + 海鲜 vs 江淮河鲜 + 刀工"）落在 prompt 片段中