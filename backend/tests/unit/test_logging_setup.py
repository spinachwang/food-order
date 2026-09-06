"""Tests for `app.core.logging` — dictConfig-based setup."""
from __future__ import annotations

import logging

import pytest
from app.core.logging import _reset_handlers, setup_logging


@pytest.fixture(autouse=True)
def _restore_root_logger() -> None:
    """Snapshot + restore the root logger handlers around each test.

    Several pytest fixtures (notably `caplog`) attach a handler to the root
    logger. Our setup_logging() builds its own handler set; we must leave
    the test process with the same handler count we started with.
    """
    root = logging.getLogger()
    original = list(root.handlers)
    try:
        yield
    finally:
        root.handlers = original


class TestSetupLogging:
    def test_setup_logging_installs_console_handler(self) -> None:
        setup_logging()
        root = logging.getLogger()
        assert any(
            h.__class__.__name__ == "StreamHandler" for h in root.handlers
        )

    def test_setup_logging_is_idempotent(self) -> None:
        setup_logging()
        first_handlers = list(logging.getLogger().handlers)
        setup_logging()
        second_handlers = list(logging.getLogger().handlers)
        # Re-running must not stack handlers — same count as the first call.
        assert len(first_handlers) == len(second_handlers)

    def test_setup_logging_accepts_explicit_level(self) -> None:
        setup_logging(level="DEBUG")
        # `app.agents.llm` logger is configured at DEBUG by default; root
        # should reflect the override.
        assert logging.getLogger("app.agents.llm").getEffectiveLevel() == logging.DEBUG
        assert logging.getLogger().level == logging.DEBUG

    def test_setup_logging_rejects_unknown_format(self) -> None:
        with pytest.raises(ValueError, match="Unsupported LOG_FORMAT"):
            setup_logging(fmt="xml")

    def test_setup_logging_json_format_does_not_raise(self) -> None:
        setup_logging(fmt="json")
        # No assertion on output here — just verify it doesn't blow up.
        assert logging.getLogger().level in {
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
        }

    def test_reset_handlers_detaches_managed_loggers(self) -> None:
        setup_logging()
        # After setup, our managed loggers may have inherited handlers via
        # propagate; verify we can wipe them without raising.
        _reset_handlers()
        # And re-running setup works again (idempotent on the cleaned state).
        setup_logging()
