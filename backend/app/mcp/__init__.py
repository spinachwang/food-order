"""F030 / F031 — 高德 MCP 工具包.

包内子模块:

- `client`: 通用 httpx 客户端 + 错误码映射 + 重试
- `restaurant`: F030 餐厅周边搜索
- `weather`: F031 天气查询

约定:
- 客户端 / Tool 都是 async-first, 同步入口用 `asyncio.run` 桥接
- 错误统一抛 `app.core.exceptions.AmapError` 子类, 由 `app/main.py` 注册
  的全局处理器翻译成 envelope
- LLM 不参与此包 —— MCP 是确定性的 HTTP 工具, 与 LLM 解耦
"""
