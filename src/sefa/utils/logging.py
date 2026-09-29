"""Structured logging setup with PHI masking."""

from __future__ import annotations

import logging
import sys
from typing import TextIO

import structlog

from sefa.utils.compliance import mask_phi


def setup_logging(
    level: str = "INFO",
    phi_masking: bool = True,
    stream: TextIO | None = None,
) -> None:
    """Configure structured logging with optional PHI masking.

    `stream` defaults to stderr; tests pass a buffer so the masked output can be
    asserted without fighting whoever else owns stdout/stderr.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if phi_masking:
        shared_processors.append(
            lambda _, __, event_dict: _mask_event_dict(event_dict)
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    output = stream or sys.stderr
    if output.isatty():
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(output)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def _mask_event_dict(event_dict: dict) -> dict:
    if "event" in event_dict and isinstance(event_dict["event"], str):
        event_dict["event"] = mask_phi(event_dict["event"])
    return event_dict
