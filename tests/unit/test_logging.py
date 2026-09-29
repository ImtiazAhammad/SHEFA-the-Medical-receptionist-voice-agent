"""T8: the configured structlog logger is the ONLY server logger.

`logging.basicConfig` in `main.py` used to install a parallel rendering path
that structlog's PHI masking never ran on. These tests pin two things:

1. `setup_logging(phi_masking=...)` is the real masking gate, on and off.
2. `main.py` wires that gate from config — `monitoring.logging.phi_masking` —
   and no longer begs off with its own `basicConfig`.
"""

from __future__ import annotations

import importlib
import io
import logging
import sys
from pathlib import Path

import pytest
import structlog

from sefa.config.settings import settings
from sefa.utils.logging import setup_logging


@pytest.fixture
def log_capture(monkeypatch):
    """Point stderr at a buffer and restore its handler stream afterwards.

    `setup_logging` clears and re-creates root handlers, so the teardown has to
    re-attach a live stream too — otherwise every later log in the suite dies
    into a discarded StringIO. The stream is passed explicitly rather than
    swapped in via monkeypatched `sys.stderr`, so the test is immune to
    pytest's own stderr capture.
    """
    buffer = io.StringIO()

    yield buffer

    for handler in logging.getLogger().handlers:
        if handler.stream is buffer:
            handler.stream = sys.stderr


class TestSetupLoggingHonoursThePhiMaskingFlag:
    def test_masks_phi_when_enabled(self, log_capture):
        setup_logging("INFO", phi_masking=True, stream=log_capture)
        structlog.get_logger("t8").info("client called +8801712345678")

        rendered = log_capture.getvalue()
        assert "8801712345" not in rendered
        assert "5678" in rendered

    def test_leaves_phi_alone_when_disabled(self, log_capture):
        setup_logging("INFO", phi_masking=False, stream=log_capture)
        structlog.get_logger("t8").info("client called +8801712345678")

        assert "+8801712345678" in log_capture.getvalue()

    def test_installs_exactly_one_root_handler(self, log_capture):
        """The server must have one configured pipeline, not a long tail of
        competing renderers."""
        setup_logging("INFO", phi_masking=True, stream=log_capture)

        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(
            root.handlers[0].formatter, structlog.stdlib.ProcessorFormatter
        )
        assert root.handlers[0].stream is log_capture


class _TtyLike(io.StringIO):
    def isatty(self) -> bool:
        return True


class TestSetupLoggingChoosesTheRendererByStream:
    def test_tty_stream_gets_the_console_renderer(self, log_capture):
        setup_logging("INFO", phi_masking=False, stream=_TtyLike())
        formatter = logging.getLogger().handlers[0].formatter
        assert isinstance(
            formatter.processors[-1], structlog.dev.ConsoleRenderer
        )

    def test_non_tty_stream_gets_json(self, log_capture):
        setup_logging("INFO", phi_masking=False, stream=log_capture)
        formatter = logging.getLogger().handlers[0].formatter
        assert isinstance(
            formatter.processors[-1], structlog.processors.JSONRenderer
        )


class TestMainWiresTheConfiguredLogger:
    def test_main_registers_no_parallel_logger(self):
        source = Path(importlib.import_module("sefa.main").__file__).read_text(
            encoding="utf-8"
        )
        assert "basicConfig" not in source
        assert "setup_logging" in source
        assert "phi_masking" in source

    def test_main_logger_is_a_structlog_bound_logger(self):
        import sefa.main

        assert sefa.main.logger.__class__.__module__.startswith("structlog")

    def test_main_passes_the_config_flag_to_setup(self, monkeypatch):
        """main's module body must call setup with the *config* flag, so an
        operator flipping `monitoring.logging.phi_masking` actually moves the
        masking. The stub records the call; the reload is what replays it."""
        calls: list[tuple[str, bool]] = []

        def fake_setup_logging(level: str, phi_masking: bool) -> None:
            calls.append((level, phi_masking))

        monkeypatch.setattr(
            "sefa.utils.logging.setup_logging", fake_setup_logging
        )
        importlib.reload(importlib.import_module("sefa.main"))

        assert calls == [(settings.monitoring.logging.level, True)]

    def test_the_config_flag_is_readable_and_defaults_on(self):
        assert settings.monitoring.logging.phi_masking is True