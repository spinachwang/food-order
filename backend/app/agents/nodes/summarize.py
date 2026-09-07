"""`summarize` Node — F040 §3.2 row 6 + F004 graph terminal-before-END.

把 `AgentState` (`cuisine_results` / `restaurant_lists` / `weather` /
`user_preferences`) 喂给 `SummaryAgent`, 拿到结构化 `Recommendation` 后写回
state. 整个调用被 try/except 包住, 任何异常都降级为 `_DEGRADED_RECOMMENDATION`
+ 追加 `errors` 条目 — F040 §7 / F004 §3.4 都强调"summary 异常不破坏 graph".

设计要点:
- `SummaryAgent` 是普通 Python 类 (无 langgraph 依赖), 让单测可以绕开 graph 直接调
- 通过 `get_llm_provider()` 工厂注入 LLM — 测试用 `app.dependency_overrides`
  或 monkeypatch 替换
- `SummaryAgent.assemble` 已经是 async (2026-09-07 改造). 之前用 sync + asyncio.run
  在 worker thread 跑会触发 `httpx.AsyncClient is bound to a different event loop`,
  因为 LLM provider cache 的 client 绑定到 LangGraph 主 loop.
"""
from __future__ import annotations

import logging
from typing import Any

from app.agents.llm.factory import get_llm_provider
from app.agents.state import AgentState
from app.agents.summary import DEGRADED_HEADLINE, SummaryAgent

_logger = logging.getLogger(__name__)


async def node_summarize(state: AgentState) -> dict[str, Any]:
    """F040 主 Node — 组装 Recommendation, 失败时降级.

    永远不抛错. 失败时:
    1. `recommendation` 填降级 payload (与 F004 Phase 1 stub 行为一致)
    2. `errors` 列表追加 `{node, code, message}`
    """
    try:
        llm = get_llm_provider()
        agent = SummaryAgent(llm=llm)
        # assemble 已经在 LangGraph 主 event loop 上跑 (await), 复用了同一个
        # httpx.AsyncClient (LLM provider cache 的).
        recommendation = await agent.assemble(state)
        return {"recommendation": recommendation}
    except Exception as exc:
        _logger.exception("F040 summarize crashed; returning degraded")
        existing_errors = list(state.get("errors") or [])
        return {
            "recommendation": _degraded_payload(state),
            "errors": [
                *existing_errors,
                {
                    "node": "summarize",
                    "code": "SUMMARY_NODE_FAILED",
                    "message": f"{type(exc).__name__}: {exc}",
                },
            ],
        }


def _degraded_payload(state: AgentState) -> dict[str, Any]:
    """Node-level emergency fallback — F040 §7 + F004 §3.4 一致."""
    return {
        "headline": DEGRADED_HEADLINE,
        "cuisine_id": "",
        "restaurant_id": "",
        "restaurant_name": "",
        "order_takeout": True,
        "reason": "推荐服务暂时不可用",
        "confidence": 0.0,
        "alternatives": [],
    }


__all__ = ["node_summarize"]