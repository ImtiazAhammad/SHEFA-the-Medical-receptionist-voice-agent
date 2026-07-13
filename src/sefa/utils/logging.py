"""Structured logging setup with PHI masking."""

from __future__ import annotations

import logging
import sys

import structlog

from sefa.utils.compliance import mask_phi


def setup_logging(level: str = "INFO", phi_masking: bool = True) -> None:
    """Configure structured logging with optional PHI masking."""
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

    if sys.stderr.isatty():
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def _mask_event_dict(event_dict: dict) -> dict:
    if "event" in event_dict and isinstance(event_dict["event"], str):
        event_dict["event"] = mask_phi(event_dict["event"])
    return event_dict
