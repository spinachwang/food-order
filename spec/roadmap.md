# roadmap.md — 里程碑

| 里程碑 | 范围 | 状态 |
|---|---|---|
| **M0** | 骨架 — FastAPI `/healthz` + Vite 默认页 + spec 目录 + CLAUDE.md 落定 | ◀ 当前 |
| M1 Sprint 1 | 鉴权 + 店铺/菜单/订单 CRUD + MySQL + Alembic | 未开始 |
| M1 Sprint 2 | 顾客端流程串联 + 沙箱支付 | 未开始 |
| M2 | 微信小程序 + 实时订单 + 配送配置 | 未开始 |
| M3 | 优惠券 / 会员 / 看板 / 第三方配送 | 未开始 |

## M0 验收清单

- [x] 仓库根目录有 `CLAUDE.md` / `README.md` / `.env.example` / `.gitignore`
- [x] `spec/` 目录占位文档齐备
- [x] `backend/` FastAPI 骨架可启动并返回 `/healthz`
- [x] `frontend/` Vite + React 默认页可访问
- [x] 至少 1 个后端 smoke 测试（`test_healthz`）

## M1 Sprint 1 验收清单（待细化）

- [ ] F020 注册/登录可用
- [ ] F001 / F002 店铺与菜单可读
- [ ] F004 订单可创建（未支付）
- [ ] 后端测试覆盖率 ≥ 80%
- [ ] 前端至少 1 个 E2E 流程