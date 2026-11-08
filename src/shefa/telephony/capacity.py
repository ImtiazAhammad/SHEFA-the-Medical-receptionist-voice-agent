"""How many calls the box answers at once, and what the next caller hears.

Speech recognition, the model and the voice share one GPU. Past the number of calls it can serve
well, every caller's audio degrades, not just the last one's. So the Nth+1 caller is told plainly
that the lines are busy, a call-back is queued with their number, and the line is released.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CallGate:
    """Counts live calls against ``telephony.max_concurrent_calls`` (0 means no limit)."""

    def __init__(self) -> None:
        self._active: set[str] = set()

    @staticmethod
    def limit() -> int:
        from shefa.config.settings import settings

        return settings.telephony.max_concurrent_calls

    def admit(self, call_sid: str) -> bool:
        if call_sid in self._active:
            return True
        limit = self.limit()
        if limit and len(self._active) >= limit:
            logger.warning("Turning away %s: %d calls already live", call_sid, len(self._active))
            return False
        self._active.add(call_sid)
        return True

    def release(self, call_sid: str) -> None:
        self._active.discard(call_sid)

    @property
    def active(self) -> int:
        return len(self._active)


gate = CallGate()
