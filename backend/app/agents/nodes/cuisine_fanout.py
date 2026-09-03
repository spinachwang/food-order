"""`cuisine_fanout` Node — F004 §3.2 row 3.

The 14 registered cuisines (F003 §3.2 / `CUISINE_REGISTRY`) are addressed by
`state["selected_cuisines"]`. This Node:

- Runs each `BaseCuisineExpert.run(state)` concurrently via `asyncio.gather`
  (`return_exceptions=True`), so a single failure never blocks the others.
- Aggregates outcomes into `state["cuisine_results"]: dict[str, output]`
  keyed by `cuisine_id`. The dict shape — vs. the F004 spec §3.1 list —
  is the F003 §6 / F004 §3.2 decision recorded in `app/agents/state.py`'s
  TODO(F004) note: dict-by-id is what the parallel-fanin needs; spec is
  updated by test fixtures.
- Failed experts contribute an entry to `errors` (spec §3.4) instead of
  propagating. The summary agent (F040) skips failed cuisines.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from app.agents.cuisines import CUISINE_REGISTRY
from app.agents.state import AgentState, CuisineExpertOutput

_logger = logging.getLogger(__name__)


async def node_cuisine_fanout(state: AgentState) -> dict[str, object]:
    """Dispatch to each selected cuisine's expert.run() in parallel."""
    selected: list[str] = list(state.get("selected_cuisines") or [])
    if not selected:
        # Router returned empty (e.g. EMPTY_MESSAGE) — nothing to do.
        # The router's own errors[] explains why; we don't duplicate.
        return {"cuisine_results": {}}

    # Drop unknown ids defensively (registry is the source of truth).
    targets: list[str] = [cid for cid in selected if cid in CUISINE_REGISTRY]
    if not targets:
        return {
            "cuisine_results": {},
            "errors": [
                {
                    "code": "NO_VALID_CUISINES",
                    "message": f"selected_cuisines 不在注册表: {selected}",
                }
            ],
        }

    coros = [CUISINE_REGISTRY[cid].run(state) for cid in targets]
    results = await asyncio.gather(*coros, return_exceptions=True)

    merged: dict[str, CuisineExpertOutput] = {}
    new_errors: list[dict[str, str]] = []
    for cid, result in zip(targets, results, strict=True):
        if isinstance(result, Exception):
            # Spec §3.4: 不中断整体工作流. F003 §3.3 says each expert already
            # returns a `_fallback_output` on parse failure; this branch is
            # for *raised* exceptions (NotImplementedError in Phase 1, runtime
            # issues, transport failures, etc.).
            _logger.warning(
                "cuisine %s failed: %s",
                cid,
                result,
                exc_info=result,
            )
            new_errors.append(
                {
                    "code": "CUISINE_NODE_FAILED",
                    "cuisine_id": cid,
                    "message": f"{type(result).__name__}: {result}",
                }
            )
            continue
        # Result is a partial-state dict; pull the cuisine_id-keyed output
        # if present, else treat raw dict as the output.
        merged[cid] = _coerce_to_output(cid, result)

    out: dict[str, Any] = {"cuisine_results": merged}
    if new_errors:
        out["errors"] = new_errors
    return out


def _coerce_to_output(
    cuisine_id: str, raw: object
) -> CuisineExpertOutput:
    """Convert whatever the expert returned into the TypedDict shape.

    Experts return `dict[str, object]` shaped like the cuisine output
    (F003 §3.1). Some Phase 1 stubs may return an empty dict or a stub
    test sentinel; we coerce defensively so downstream summary agent
    sees the right keys.
    """
    if not isinstance(raw, dict):
        _logger.warning("cuisine %s returned non-dict: %r", cuisine_id, raw)
        return {
            "cuisine_id": cuisine_id,
            "conclusion": "暂不可推荐",
            "keywords": [],
            "matched_allergies": [],
        }
    d = cast(dict[str, object], raw)
    keywords = d.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    allergies = d.get("matched_allergies") or []
    if not isinstance(allergies, list):
        allergies = []
    return {
        "cuisine_id": str(d.get("cuisine_id") or cuisine_id),
        "conclusion": str(d.get("conclusion") or ""),
        "keywords": [str(k) for k in keywords],
        "matched_allergies": [str(a) for a in allergies],
    }


__all__ = ["node_cuisine_fanout"]
