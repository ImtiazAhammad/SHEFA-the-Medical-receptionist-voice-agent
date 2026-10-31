"""What an outbound call is about, handed from whoever dials to the pipeline that answers.

The dialler registers a context under the call's UUID; when the patient picks up and the
pipeline starts, it takes the context once: the opening line to speak, who the caller is,
and a callback to tell the dialler the call was answered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_pending: dict[str, OutboundContext] = {}


@dataclass
class OutboundContext:
    greeting: str
    language: str = "bn"
    patient_id: str = ""
    patient_name: str = ""
    on_answered: Callable[[], None] | None = field(default=None, repr=False)


def set_context(call_sid: str, context: OutboundContext) -> None:
    _pending[call_sid] = context


def pop_context(call_sid: str) -> OutboundContext | None:
    return _pending.pop(call_sid, None)


def discard_context(call_sid: str) -> None:
    _pending.pop(call_sid, None)


def has_context(call_sid: str) -> bool:
    return call_sid in _pending
