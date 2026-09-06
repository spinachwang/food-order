"""Central application logging configuration.

`setup_logging()` wires the stdlib `logging` dictConfig so that every log
line emitted anywhere in the backend (including library code) carries the
`request_id` of the inbound HTTP request that triggered it.

Call once from `app/main.py:create_app()`. The function is **idempotent** —
re-invocations clear existing handlers and re-apply the config so test
fixtures can re-call it with different settings without leaking handlers
across tests.

Why not `logging.basicConfig`? dictConfig gives us per-logger levels
(`app.agents.llm` always DEBUG when root is INFO), a structured JSON
formatter option for log shippers, and clean module separation.

Why not `loguru` / `structlog`? Project standard (per logging audit) is
stdlib `logging`. We don't introduce dependencies for cross-cutting concerns
that stdlib already covers.
"""
from __future__ import annotations

import logging
import logging.config
from typing import Any

from app.core.config import get_settings
from app.core.request_id import RequestIdFilter

# Default formatter — human-readable, single-line, includes `request_id`.
# The `%(msecs)03d` gives millisecond precision without sub-second noise.
_HUMAN_FORMAT = (
    "%(asctime)s.%(msecs)03d %(levelname)-5s [%(name)s] [rid=%(request_id)s] %(message)s"
)
# JSON formatter — single-line JSON, useful for log shippers (Loki/ELK).
# Fields: ts (ISO-8601 with ms), level, logger, rid, message.
_JSON_FORMAT = (
    '{"ts":"%(asctime)s.%(msecs)03d","level":"%(levelname)s",'
    '"logger":"%(name)s","rid":"%(request_id)s","msg":"%(message)s"}'
)


def _build_config(level: str, fmt: str) -> dict[str, Any]:
    """Construct a dictConfig payload.

    Layout:
      - root: INFO (or override), no handlers at root — propagation only
      - app.*: inherits from root (configured below)
      - app.agents.llm: DEBUG so prompts are visible when root is INFO
      - app.agents.prompts: DEBUG for prompt-render trace
      - app.agents.nodes: INFO for per-node enter/exit
      - uvicorn / sqlalchemy.engine: WARNING (quiet default)
    """
    format_string = _JSON_FORMAT if fmt == "json" else _HUMAN_FORMAT

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": RequestIdFilter,
            },
        },
        "formatters": {
            "human": {
                "format": format_string,
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "human",
                "filters": ["request_id"],
            },
        },
        "loggers": {
            # `app` inherits from root so user-set LOG_LEVEL=DEBUG cascades to
            # every `app.*` logger. Per-module overrides live ONLY on
            # `app.agents.llm` / `app.agents.prompts` (always DEBUG — prompts
            # are useless below DEBUG and we want them inspectable whenever
            # the operator flips LOG_LEVEL above WARNING).
            "app.agents.llm": {"level": "DEBUG", "handlers": [], "propagate": True},
            "app.agents.prompts": {"level": "DEBUG", "handlers": [], "propagate": True},
            # Third-party — silence the noisy ones unless user opts in via
            # LOG_LEVEL override (root level).
            "uvicorn": {"level": "WARNING", "handlers": [], "propagate": True},
            "uvicorn.access": {"level": "INFO", "handlers": [], "propagate": True},
            "sqlalchemy.engine": {"level": "WARNING", "handlers": [], "propagate": True},
        },
        "root": {"level": level, "handlers": ["console"]},
    }


def setup_logging(*, level: str | None = None, fmt: str | None = None) -> None:
    """Apply the dictConfig.

    Args:
        level: Override root / `app` logger level. Falls back to
            `Settings.log_level` (default "INFO").
        fmt: Override formatter name (`"human"` or `"json"`). Falls back to
            `Settings.log_format` (default `"human"`).

    Idempotent: clears existing handlers on `app.*` loggers and the root
    logger before applying new config so repeated calls (e.g. in tests) do
    not stack handlers or duplicate output.
    """
    settings = get_settings()
    chosen_level = (level or settings.log_level).upper()
    chosen_fmt = (fmt or settings.log_format).lower()

    if chosen_fmt not in {"human", "json"}:
        raise ValueError(
            f"Unsupported LOG_FORMAT={chosen_fmt!r}; expected 'human' or 'json'"
        )

    # Idempotency: detach all handlers on every logger we manage so the
    # `disable_existing_loggers=False` flag in dictConfig doesn't stack them.
    _reset_handlers()

    config = _build_config(level=chosen_level, fmt=chosen_fmt)
    logging.config.dictConfig(config)


def _reset_handlers() -> None:
    """Remove handlers from loggers we manage, plus the root logger.

    Walks `logging.Logger.manager.loggerDict` so we catch loggers that exist
    by name but haven't been instantiated yet. Idempotent.
    """
    targets: set[str] = {
        "",
        "app",
        "app.agents",
        "app.agents.llm",
        "app.agents.llm.minimax",
        "app.agents.llm.testing",
        "app.agents.prompts",
        "app.agents.nodes",
        "app.agents.observability",
        "uvicorn",
        "uvicorn.access",
        "sqlalchemy.engine",
    }
    for name in targets:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)


__all__ = ["setup_logging"]
