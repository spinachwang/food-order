"""LLM prompt templates — first-class assets (CLAUDE.md rule).

`backend/app/agents/prompts/` is the canonical home for non-cuisine LLM
prompts. Cuisine experts live under `app/agents/cuisines/prompts/` because
they are *per-cuisine* modules loaded by the registry; the summary prompt is
a single Node's render, so it lives here.

Public surface (re-exported below):
- `summary.render_summary_prompt(...)` — render the summary agent's prompt.
"""
from app.agents.prompts.summary import (
    DECISION_MATRIX_TABLE,
    build_decision_matrix_table,
    render_summary_prompt,
)

__all__ = [
    "DECISION_MATRIX_TABLE",
    "build_decision_matrix_table",
    "render_summary_prompt",
]