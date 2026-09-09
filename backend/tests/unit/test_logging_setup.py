"""Tests for `app.core.logging` — dictConfig-based setup."""
from __future__ import annotations

import logging
import logging.handlers

import pytest
from app.core.config import _REPO_ROOT, get_settings
from app.core.logging import _reset_handlers, setup_logging


@pytest.fixture(autouse=True)
def _restore_root_logger() -> None:
    """Snapshot + restore the root logger handlers around each test.

    Several pytest fixtures (notably `caplog`) attach a handler to the root
    logger. Our setup_logging() builds its own handler set; we must leave
    the test process with the same handler count we started with.

    `RotatingFileHandler` instances own OS file handles that are NOT
    released by garbage collection — on Windows the next test that tries
    to open the same path raises `PermissionError`. We close them
    explicitly before restoring the handler list.
    """
    root = logging.getLogger()
    original = list(root.handlers)
    try:
        yield
    finally:
        for h in list(root.handlers):
            if isinstance(h, logging.handlers.RotatingFileHandler):
                h.close()
        root.handlers = original


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Drop the `lru_cache` on `get_settings` so monkeypatched env vars take effect."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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

    def test_observability_logger_is_debug_at_info_root(self) -> None:
        """Regression: `app.agents.observability` must stay at DEBUG even when
        root is INFO, otherwise `instrument_llm_call` and `logged_node` never
        emit prompt/response bodies (their content lines are DEBUG-gated).
        """
        setup_logging(level="INFO")
        assert (
            logging.getLogger("app.agents.observability").getEffectiveLevel()
            == logging.DEBUG
        )
        # Sanity: root is INFO as configured.
        assert logging.getLogger().level == logging.INFO

    def test_prompts_and_llm_loggers_stay_debug_at_info_root(self) -> None:
        """Same regression guard for the sibling sub-loggers."""
        setup_logging(level="INFO")
        assert logging.getLogger("app.agents.llm").getEffectiveLevel() == logging.DEBUG
        assert logging.getLogger("app.agents.prompts").getEffectiveLevel() == logging.DEBUG

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


# ---------------------------------------------------------------------------
# File sink — opt-in RotatingFileHandler wired by `LOG_FILE_PATH`.
# ---------------------------------------------------------------------------


class TestFileLoggingSink:
    """Coverage for the optional rotating-file sink added on top of stderr.

    Each test sets `LOG_FILE_PATH` (and rotation params where relevant) via
    `monkeypatch.setenv`, then asserts the resulting file-system + handler
    state. The autouse fixtures in this module ensure both the settings
    cache is invalidated and any open `RotatingFileHandler` is closed
    before the test process moves on.
    """

    def _file_handlers(self) -> list[logging.handlers.RotatingFileHandler]:
        return [
            h
            for h in logging.getLogger().handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]

    def test_empty_log_file_path_creates_no_file_handler(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_FILE_PATH", "")
        setup_logging()
        assert self._file_handlers() == []

    def test_whitespace_only_disables_sink(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_FILE_PATH", "   ")
        setup_logging()
        assert self._file_handlers() == []

    def test_configured_path_writes_records(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "app.log"
        monkeypatch.setenv("LOG_FILE_PATH", str(target))
        setup_logging()

        logging.getLogger().info("MARKER-RECORD")

        # Flush is implicit on close, but pytest runs handlers under caplog
        # too — force a flush so the test does not race the FS buffer.
        for h in self._file_handlers():
            h.flush()

        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "MARKER-RECORD" in content

    def test_relative_path_resolves_against_repo_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`LOG_FILE_PATH=logs/x.log` lands at `_REPO_ROOT/logs/x.log`,
        regardless of pytest's cwd. Cleanup is best-effort — we delete only
        the file we created, not the (possibly shared) `logs/` directory.

        The handler must be closed BEFORE we `unlink` — Windows refuses
        to delete a file that is still mmap'd by a RotatingFileHandler.
        The autouse fixture closes handlers too, but only at the end of
        the *next* test's setup; here we need it earlier.
        """
        rel = "logs/_pytest_relative_resolve.log"
        expected = _REPO_ROOT / rel
        if expected.exists():
            expected.unlink()

        monkeypatch.setenv("LOG_FILE_PATH", rel)
        try:
            setup_logging()
            logging.getLogger().info("RELATIVE-PATH-PROBE")
            for h in self._file_handlers():
                h.flush()
                h.close()
            assert expected.exists()
            assert "RELATIVE-PATH-PROBE" in expected.read_text(encoding="utf-8")
        finally:
            if expected.exists():
                expected.unlink()

    def test_rotation_parameters_threaded(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_FILE_PATH", str(tmp_path / "rot.log"))
        monkeypatch.setenv("LOG_FILE_MAX_BYTES", "200")
        monkeypatch.setenv("LOG_FILE_BACKUP_COUNT", "2")
        setup_logging()

        handlers = self._file_handlers()
        assert len(handlers) == 1
        h = handlers[0]
        assert h.maxBytes == 200
        assert h.backupCount == 2

    def test_idempotent_under_re_setup(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_FILE_PATH", str(tmp_path / "idempotent.log"))
        setup_logging()
        setup_logging()
        # Exactly one file handler on root — never stacked.
        assert len(self._file_handlers()) == 1

    def test_file_sink_captures_observability_debug_records(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The point of the sink: DEBUG records from `app.agents.observability`
        (prompt / response bodies) propagate to root and land in the file.
        Root level is INFO so the file is not flooded with every DEBUG line
        from libraries, but the observability logger keeps its DEBUG override.
        """
        target = tmp_path / "obs.log"
        monkeypatch.setenv("LOG_FILE_PATH", str(target))
        setup_logging(level="INFO")

        logging.getLogger("app.agents.observability").debug(
            "PROMPT>>> %s", "test-marker-xyz"
        )
        for h in self._file_handlers():
            h.flush()

        assert target.exists()
        assert "PROMPT>>> test-marker-xyz" in target.read_text(encoding="utf-8")
