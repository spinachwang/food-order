# features.md — 功能列表

> 每条功能必须含：用户故事、验收清单、所属里程碑（M1 / M2 / M3）。**未列入本表的功能不得实现**。
> 当前 M1 方向：**AI Agent 午餐决策系统**（详见 [adr/0002-ai-agent-pivot.md](adr/0002-ai-agent-pivot.md)）。原 M0 的传统 Web 应用功能标记 `[ARCHIVED-M0]`，仅供历史参考。

## 状态约定

- [ ] 未开始
- [~] 进行中
- [x] 完成
- [!] 阻塞 / 待评审
- [ARCHIVED-M0] 已废弃（M0 阶段的方向，被 ADR 0002 取代）

---

## M1 — Agent MVP（当前）

### 基础设施

- [ ] **F001**：[用户偏好管理](features/F001-user-preferences.md) — 偏好数据模型 + CRUD API + Agent 读取接口（M1 不做登录、不做 feedback）
- [ ] **F002**：[主 Agent 编排（router）](features/F002-main-agent-router.md) — 解析意图、决定调哪些菜系专家
- [x] **F003**：[菜系专家通用契约](features/F003-cuisine-expert-contract.md) — LangGraph Node 接口 / 输入输出 schema / prompt 模板结构
- [ ] **F004**：[LangGraph 整体工作流](features/F004-langgraph-workflow.md) — State 类型 / 所有 Node / Edge 条件 / checkpoint 策略

### 14 个菜系专家（每个独立 spec）

- [ ] **F010**：[川菜专家](features/F010-sichuan.md)
- [ ] **F011**：[粤菜专家](features/F011-cantonese.md)
- [ ] **F012**：[鲁菜专家](features/F012-shandong.md)
- [ ] **F013**：[苏菜专家](features/F013-suzhou.md)
- [ ] **F014**：[浙菜专家](features/F014-zhejiang.md)
- [ ] **F015**：[闽菜专家](features/F015-fujian.md)
- [ ] **F016**：[湘菜专家](features/F016-hunan.md)
- [ ] **F017**：[徽菜专家](features/F017-anhui.md)
- [ ] **F018**：[日料专家](features/F018-japanese.md)
- [ ] **F019**：[西餐专家](features/F019-western.md)
- [ ] **F020**：[西式快餐专家](features/F020-western-fastfood.md)
- [ ] **F022**：[中式快餐专家](features/F022-chinese-fastfood.md)
- [ ] **F023**：[小吃专家](features/F023-snacks.md)
- [ ] **F024**：[甜品饮品专家](features/F024-dessert-drinks.md)

### 高德 MCP 集成

- [ ] **F030**：[高德 MCP 周边搜索（餐厅）](features/F030-amap-restaurant-search.md)
- [ ] **F031**：[高德 MCP 天气查询](features/F031-amap-weather.md)

### 总结 Agent

- [ ] **F040**：[总结与推荐 Agent](features/F040-summary-agent.md) — 综合菜系专家输出 + 天气 + 偏好，给出最终建议

### Web 聊天壳（前端）

- [ ] **F050**：[Web 聊天窗口（Vite + React）](features/F050-chat-shell.md)
- [ ] **F051**：[结构化地址选择器](features/F051-structured-address.md) — 替代 `window.prompt`，用 5 级选址组件（省/市/区/商圈/小区/门牌号）产出结构化 `default_location`；依赖高德 `/config/district` + `regeo` + F030 `place/text`（M1 落地，取代 F050 §8 #5 原"M2 接高德选址组件"计划）

---

## M2 — 体验增强（暂缓）

> 待 M1 Agent MVP 验收后再展开

- 登录态与多设备同步
- 历史对话记录
- 收藏夹 / 黑名单
- 用户反馈回写（`POST /api/v1/feedback` + `user_feedback` 表）
- 团队 / 群组推荐
- 国际化

## M3 — 商业化（暂缓）

- 推荐准确率看板
- 城市 / 区域配置
- 多 LLM 兜底
- 第三方外卖平台深链接（不实际下单，仅跳转）

---

## [ARCHIVED-M0] 原 Web 应用功能（已被 ADR 0002 取代）

> 以下功能在 M0 阶段被规划过，但因产品方向转向 AI Agent 系统，**不再实现**。保留在此供检索 / 历史追溯。

### 顾客端

- [ARCHIVED-M0] **F001**：浏览店铺列表
- [ARCHIVED-M0] **F002**：查看店铺菜单
- [ARCHIVED-M0] **F003**：加入购物车
- [ARCHIVED-M0] **F004**：提交订单（未支付）
- [ARCHIVED-M0] **F005**：订单支付（沙箱）
- [ARCHIVED-M0] **F006**：查看我的订单

### 商家端

- [ARCHIVED-M0] **F010**：商家登录
- [ARCHIVED-M0] **F011**：查看新订单
- [ARCHIVED-M0] **F012**：接单 / 拒单

### 通用

- [ARCHIVED-M0] **F020**：用户注册 / 登录（JWT）