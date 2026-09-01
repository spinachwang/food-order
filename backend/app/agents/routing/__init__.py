"""F002 routing subpackage.

Layer 1 (rule engine) and Layer 2 (LLM fallback) pieces of the
main-agent router. Kept separate from `app.agents.main_router` so each
helper is independently testable.
"""

from app.agents.routing.allergies import (
    HARD_ALLERGY_CONFLICTS,
    filter_conflicts,
    zero_out_conflicts,
)
from app.agents.routing.prompt import (
    build_router_prompt,
    parse_router_response,
)
from app.agents.routing.rules import (
    AMBIENT_KEYWORDS,
    CONTRADICTORY_TAGS,
    EXPLICIT_RULES,
    MAX_REASON_CODEPOINTS,
    MODIFIER_RULES,
    Rule,
    is_ambient_message,
    match_rules,
    sample_by_weights,
)

__all__ = [
    "AMBIENT_KEYWORDS",
    "CONTRADICTORY_TAGS",
    "EXPLICIT_RULES",
    "HARD_ALLERGY_CONFLICTS",
    "MAX_REASON_CODEPOINTS",
    "MODIFIER_RULES",
    "Rule",
    "build_router_prompt",
    "filter_conflicts",
    "is_ambient_message",
    "match_rules",
    "parse_router_response",
    "sample_by_weights",
    "zero_out_conflicts",
]
