"""LangGraph node implementations for F004 §3.2.

Each module exposes a single `node_<name>(state: AgentState) -> dict`
returning the partial-State delta to merge into the running graph (mirrors
the F002 `RouterOutput` / `BaseCuisineExpert.run` convention).

Failure handling — spec §3.4:
- 单个菜系 Node 异常 → 不中断，标记 cuisine_results 中该条为 error
- search_restaurants 异常 → 该 cuisine_id 餐厅列表为空
- fetch_weather 异常 → weather=None
- summarize 异常 → 不写 recommendation
- 全局 errors 列表是最终消费字段

Multiple Nodes (F030 / F031 / F040) are still unimplemented at the time
F004 lands — they raise `NotImplementedError` if called for real, and the
Node layer catches it and degrades. Once each upstream spec ships its own
implementation, the patch hooks in this module are swapped for imports.
"""
