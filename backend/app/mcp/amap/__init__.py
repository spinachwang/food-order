"""高德 MCP 工具包 —— 餐厅搜索 (F030) + 天气 (F031) + 行政区划/逆地理/POI (F051) 共用客户端.

本包按 `spec/features/F030-amap-restaurant-search.md` §7 / `F031-amap-weather.md` §7
建立, 后续 F031 / F051 也复用 `AmapClient`. 不暴露 LangChain `@tool` 装饰器
(项目不使用 LangChain Tools, 仅借 LangGraph Node 接口调用), 但函数签名
与 LangChain Tool 兼容: 显式 typed parameters + 单个 typed return.
"""
