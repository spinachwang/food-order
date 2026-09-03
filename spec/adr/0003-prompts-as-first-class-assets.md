# ADR 0003 — LLM 提示词作为 first-class 资产

- **状态**：Accepted
- **日期**：2026-09-03
- **决策者**：项目负责人
- **关联**：F002 §4（router prompt）/ F003 §4（cuisine expert prompt）/ CLAUDE.md

## 背景

随着 F002 / F003 推进，后端 `backend/app/agents/` 下出现了多份 LLM 提示词：

| 文件 | 内容 | 性质 |
|---|---|---|
| `cuisines/prompts/base.py` 的 `_TEMPLATE` | 14 个菜系专家共用的渲染模板 | 公共模板 |
| `cuisines/stubs/*.py` 的 `CUISINE_PROMPT_FRAGMENT` | 每个菜系的"代表菜 / 风味 / 区别"片段 | 菜系专属片段（14 份） |
| `routing/prompt.py` 的 `system_content` / `user_content` | F002 主路由 LLM 兜底层的 prompt | 路由模板 |

这些字符串目前**与 Python 业务逻辑耦合在同一文件里**。文案修改 / 翻译 / 多版本对比都要打开 `.py` 文件、动业务代码、走完整 CI。带来的具体问题：

1. **diff 噪音大**：产品想微调一句"代表菜描述"，git diff 会带着 Python 语法色块，PR review 难聚焦
2. **不可被非工程师改**：硬编码在 `.py` 里意味着文案修改必须经开发；产品 / 运营无法自助
3. **i18n 不友好**：未来若需中英双语版，模板字符串散在多处难以抽取
4. **版本管理缺位**：LLM 调优常需"A/B 版 prompt 对照"，但当前结构只能"覆盖式"修改，没有命名 / 版本概念
5. **职责不清**：同一文件里既改业务编排又改中文文案，违反 CLAUDE.md「单一职责 / 小文件 / 早返回」原则

## 决策

**LLM 提示词在 `food-order` 中是 first-class 资产**，与代码分离、独立维护。

具体规则：

| 项 | 约束 |
|---|---|
| **位置** | 公共目录 `backend/app/agents/prompts/`（未来重构目标） |
| **承载形式** | 单独 `.py` 模板函数 + 模板常量；菜系片段优先用独立模块 / 字典 / 文本文件 |
| **禁止** | 在 `services/` / `routers/` / Node 函数体里内联 `system_content = "..."` 这种字符串 |
| **调用面** | 业务逻辑通过 `from app.agents.prompts.<x> import render_<x>_prompt` 之类的稳定 API 调用；模板内部变更不破坏调用方 |
| **修改门槛** | prompt 文案修改无需动业务逻辑即可完成；CI 上和代码改动走同一条 lint 路径 |

## 理由

- **review 聚焦**：文案改动只动 prompt 文件，PR diff 干净
- **协作扩展**：产品 / 运营可读 / 可提 PR 修改 prompt，无需懂 LangGraph
- **A/B 与版本**：未来引入 prompt 版本（`prompts/router_v2.py` / 同名文件多版本）只需改 import，无需碰业务
- **复用一致性**：14 个菜系 + 未来可能的 summary agent / 反馈 agent 共用同一组基础设施
- **CLAUDE.md 自洽**：与现有「代码 < 800 行 / 函数 < 50 行 / 单一职责」原则一致

## 后果

- **CLAUDE.md**：在「代码风格 / 共用」段落新增一条「LLM 提示词资产」原则，并引用本 ADR
- **现有代码**：14 个 `cuisines/stubs/*.py` 的 `CUISINE_PROMPT_FRAGMENT` 与 `cuisines/prompts/base.py` 暂保持原状；后续 F003 spec 演进时按 F003 §6 / §8 节奏迁移到 `app/agents/prompts/`
- **新功能**：F040 summary agent / 任何后续 LLM 调用必须遵守本 ADR
- **F002 router**：当前 `routing/prompt.py` 暂保持原状，迁移时机为下一个 LLM 调优周期

## 备选方案

- **维持现状**：放弃，文案与代码耦合的痛点随 F003 / F040 推进只会加剧
- **把 prompt 完全放进数据库 / 配置中心**：放弃，M1 阶段过度工程；优先文件级隔离
- **用独立 micro-package `prompts-as-a-package`**：备选；若未来 prompt 数量爆炸（>20）或需跨仓库复用再升级

## 待澄清（执行中跟进）

- 迁移触发条件：F003 spec 若 §6 / §8 触发大幅 prompt 调整 → 顺手迁移到 `app/agents/prompts/`
- 是否引入 prompt 单元测试（断言关键 token 仍存在）：暂不，本 ADR 不强制
- i18n 何时引入：M2+ 再评估，本 ADR 不预先约束

## 参考

- 现状：[`backend/app/agents/cuisines/prompts/base.py`](../../backend/app/agents/cuisines/prompts/base.py)
- 现状：[`backend/app/agents/routing/prompt.py`](../../backend/app/agents/routing/prompt.py)
- 现状（示例）：[`backend/app/agents/cuisines/stubs/sichuan.py`](../../backend/app/agents/cuisines/stubs/sichuan.py)
- F002 spec：[`../features/F002-main-agent-router.md`](../features/F002-main-agent-router.md)
- F003 spec：[`../features/F003-cuisine-expert-contract.md`](../features/F003-cuisine-expert-contract.md)
- CLAUDE.md：[`../../CLAUDE.md`](../../CLAUDE.md)

---

## 修订记录

（暂无）