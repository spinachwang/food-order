"""F004 LangGraph workflow — single executable entry point.

Spec §3.2 row list (read top-to-bottom for the data flow):

1. `load_preferences`     — pull F001 preferences from DB or defaults
2. `route_cuisines`       — F002 main router
3. `cuisine_fanout`       — F003 experts, parallel via asyncio.gather
4. `search_restaurants`   — F030 (placeholder Node until F030 ships)
5. `fetch_weather`        — F031 (placeholder Node until F031 ships)
6. `summarize`            — F040 (placeholder Node until F040 ships)
7. `stream_output`        — terminal anchor; SSE mapping lives in API layer

Edge layout (spec §3.3 + parallel branches):

```
START
  → load_preferences
  → route_cuisines
  → cuisine_fanout
  → [search_restaurants, fetch_weather]   # parallel
  → summarize
  → stream_output
  → END
```

Phase 1 constraints:
- Checkpointer = `MemorySaver` (spec §5; M2 swaps in `PostgresSaver`).
- No LLM calls in this graph except the ones inside cuisine experts and
  the F002 router. Both have their own internal providers; this module
  does not instantiate one.
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver  # type: ignore[import-not-found]
from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import-not-found]
from langgraph.graph import END, START, StateGraph  # type: ignore[import-not-found]

from app.agents.nodes.cuisine_fanout import node_cuisine_fanout
from app.agents.nodes.fetch_weather import node_fetch_weather
from app.agents.nodes.load_preferences import node_load_preferences
from app.agents.nodes.route import node_route_cuisines
from app.agents.nodes.search_restaurants import node_search_restaurants
from app.agents.nodes.stream import node_stream_output
from app.agents.nodes.summarize import node_summarize
from app.agents.state import AgentState

# Public names callers (api/v1/agent.py, F050 frontend) may rely on.
__all__ = ["GRAPH_NODE_NAMES", "build_graph"]


# Spec §3.2 — node names in topological order. Used by SSE layer to map
# LangGraph lifecycle events → SSE event names (spec §4).
GRAPH_NODE_NAMES: tuple[str, ...] = (
    "load_preferences",
    "route_cuisines",
    "cuisine_fanout",
    "search_restaurants",
    "fetch_weather",
    "summarize",
    "stream_output",
)


def build_graph(
    *,
    checkpointer: bool = False,
    custom_checkpointer: BaseCheckpointSaver | None = None,
) -> StateGraph[AgentState, None, AgentState, AgentState].compiled:
    """Construct the LangGraph workflow graph.

    Single executable entry point (spec §2 + §3.2). Returns a
    `CompiledStateGraph` whose `astream_events` / `ainvoke` /
    `get_state` are the supported surface.

    Args:
        checkpointer: When True, attach an in-memory `MemorySaver` — the M1
            default per spec §5. Set False for unit tests that don't
            care about state persistence.
        custom_checkpointer: Advanced hook to plug in a different
            `BaseCheckpointSaver` (e.g. PostgresSaver once M2 lands).
            Takes precedence over the `checkpointer` flag.
    """
    graph: StateGraph = StateGraph(AgentState)

    # Nodes — order matches GRAPH_NODE_NAMES.
    graph.add_node("load_preferences", node_load_preferences)
    graph.add_node("route_cuisines", node_route_cuisines)
    graph.add_node("cuisine_fanout", node_cuisine_fanout)
    graph.add_node("search_restaurants", node_search_restaurants)
    graph.add_node("fetch_weather", node_fetch_weather)
    graph.add_node("summarize", node_summarize)
    graph.add_node("stream_output", node_stream_output)

    # Edges (spec §3.3).
    graph.add_edge(START, "load_preferences")
    graph.add_edge("load_preferences", "route_cuisines")
    graph.add_edge("route_cuisines", "cuisine_fanout")
    # Parallel branch — cuisine_fanout fans out, both converge at summarize.
    graph.add_edge(["search_restaurants", "fetch_weather"], "summarize")
    # cuisine_fanout feeds both leaves (sibling edges in 0.2.x).
    graph.add_edge("cuisine_fanout", "search_restaurants")
    graph.add_edge("cuisine_fanout", "fetch_weather")
    graph.add_edge("summarize", "stream_output")
    graph.add_edge("stream_output", END)

    # Compile.
    saver: BaseCheckpointSaver | None = None
    if custom_checkpointer is not None:
        saver = custom_checkpointer
    elif checkpointer:
        saver = MemorySaver()

    return graph.compile(checkpointer=saver)
