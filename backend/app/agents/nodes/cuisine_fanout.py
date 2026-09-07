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
import time
from typing import Any, cast

from app.agents.cuisines import CUISINE_REGISTRY
from app.agents.state import AgentState, CuisineExpertOutput
from app.core.request_id import get_request_id

_logger = logging.getLogger(__name__)


async def node_cuisine_fanout(state: AgentState) -> dict[str, object]:
    """Dispatch to each selected cuisine's expert.run() in parallel."""
    selected: list[str] = list(state.get("selected_cuisines") or [])
    rid = get_request_id() or "-"

    if not selected:
        # Router returned empty (e.g. EMPTY_MESSAGE) — nothing to do.
        # The router's own errors[] explains why; we don't duplicate.
        _logger.info("cuisine_fanout skip rid=%s reason=empty_selected", rid)
        return {"cuisine_results": {}}

    # Drop unknown ids defensively (registry is the source of truth).
    targets: list[str] = [cid for cid in selected if cid in CUISINE_REGISTRY]
    _logger.info(
        "cuisine_fanout start rid=%s selected=%s targets=%s",
        rid,
        selected,
        targets,
    )
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

    started = time.monotonic()
    results = await asyncio.gather(
        *[_run_one(rid, cid, state) for cid in targets],
        return_exceptions=False,
    )

    merged: dict[str, CuisineExpertOutput] = {}
    new_errors: list[dict[str, str]] = []
    for cid, result in zip(targets, results, strict=True):
        if result is None:
            # Per-cuisine run logged its own error already; nothing to merge.
            new_errors.append(
                {
                    "code": "CUISINE_NODE_FAILED",
                    "cuisine_id": cid,
                    "message": f"{cid} expert run failed (see logs)",
                }
            )
            continue
        merged[cid] = _coerce_to_output(cid, result)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    _logger.info(
        "cuisine_fanout done rid=%s elapsed_ms=%d merged=%d errors=%d",
        rid,
        elapsed_ms,
        len(merged),
        len(new_errors),
    )
    out: dict[str, Any] = {"cuisine_results": merged}
    if new_errors:
        out["errors"] = new_errors
    return out


async def _run_one(
    rid: str, cuisine_id: str, state: AgentState
) -> dict[str, object] | None:
    """Run one expert, with timing + exception capture.

    Returns the expert's result dict on success, or None on exception (the
    exception itself is already logged + counted via `_logger.warning`).
    """
    expert = CUISINE_REGISTRY[cuisine_id]
    started = time.monotonic()
    _logger.info("cuisine[%s] start rid=%s", cuisine_id, rid)
    try:
        result = await expert.run(state)
    except BaseException as exc:  # noqa: BLE001 — fanout never propagates
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _logger.warning(
            "cuisine[%s] failed rid=%s elapsed_ms=%d exc=%s",
            cuisine_id,
            rid,
            elapsed_ms,
            type(exc).__name__,
        )
        _logger.debug(
            "cuisine[%s] traceback rid=%s", cuisine_id, rid, exc_info=exc
        )
        return None
    elapsed_ms = int((time.monotonic() - started) * 1000)
    _logger.info(
        "cuisine[%s] ok rid=%s elapsed_ms=%d", cuisine_id, rid, elapsed_ms
    )
    return cast(dict[str, object], result)


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
