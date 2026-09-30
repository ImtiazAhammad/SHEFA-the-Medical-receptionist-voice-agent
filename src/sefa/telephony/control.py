"""Provider-neutral call control.

`transfer_to_human` used to set a session state and return `True`, so the
agent announced a transfer that never happened. A patient saying "chest pain"
was told a receptionist was being connected while the line stayed open and
dead. This module gives the escalation path a real endpoint: a `CallLeg` per
live call, registered in a `CallControl`, so a transfer is a provider call with
a success or failure rather than a boolean.

SIP lands behind this same interface (T7 keeps one provider enum), so a
transfer implementation change is not a pipeline change.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class CallLeg(ABC):
    """One live call leg a provider can act on.

    Implementations set `call_sid` as an instance attribute; a provider leg is
    identified by the call it belongs to, not by a property override.
    """

    call_sid: str

    @abstractmethod
    async def transfer(self, to: str) -> dict[str, Any]:
        """Bridge this leg to `to` (E.164)."""

    @abstractmethod
    async def play_file(self, url: str, loop: int = 1) -> dict[str, Any]:
        """Play an audio file to the caller while waiting."""

    @abstractmethod
    async def hangup(self) -> dict[str, Any]:
        """End the call."""

    @abstractmethod
    async def dial(self, number: str) -> dict[str, Any]:
        """Place a new outbound leg."""


class CallControl:
    """Registry of live call legs, keyed by call_sid."""

    def __init__(self) -> None:
        self._legs: dict[str, CallLeg] = {}

    def register(self, leg: CallLeg) -> None:
        self._legs[leg.call_sid] = leg

    def get(self, call_sid: str) -> CallLeg | None:
        return self._legs.get(call_sid)

    def release(self, call_sid: str) -> None:
        self._legs.pop(call_sid, None)

    def active_count(self) -> int:
        return len(self._legs)

    def active_call_sids(self) -> list[str]:
        return list(self._legs)

    async def transfer(self, call_sid: str, to: str) -> dict[str, Any]:
        leg = self._legs.get(call_sid)
        if leg is None:
            return {"error": f"No active call leg for {call_sid}", "transferred": False}
        try:
            return await leg.transfer(to)
        except Exception as exc:
            logger.exception("Transfer failed for %s", call_sid)
            return {"error": str(exc), "transferred": False}

    async def play_file(self, call_sid: str, url: str, loop: int = 1) -> dict[str, Any]:
        leg = self._legs.get(call_sid)
        if leg is None:
            return {"error": f"No active call leg for {call_sid}"}
        return await leg.play_file(url, loop)

    async def hangup(self, call_sid: str) -> dict[str, Any]:
        leg = self._legs.get(call_sid)
        if leg is None:
            return {"error": f"No active call leg for {call_sid}"}
        return await leg.hangup()

    async def dial(self, call_sid: str, number: str) -> dict[str, Any]:
        leg = self._legs.get(call_sid)
        if leg is None:
            return {"error": f"No active call leg for {call_sid}"}
        return await leg.dial(number)


control = CallControl()


def on_call_target() -> str | None:
    """First configured on-call number, or None when the list is empty.

    An empty list is a real state, not a default: the staffed on-call
    allow-list for the unmanned window is still an open blocker, so this
    returns None rather than inventing a number to dial.
    """
    from sefa.config.settings import settings

    numbers = settings.escalation.on_call_numbers
    return numbers[0] if numbers else None
