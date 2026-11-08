"""Ending a call when the agent, not the caller, is finished with it.

The pipeline returns when a call is handed to a human, abandoned after repeated failures, found to
be in an unsupported language, or ended with "goodbye". Until now nothing hung up after that, so
the caller sat on a silent open line. Handlers race the pipeline against the caller's hang-up, let
the last words play out, then end the call.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

PLAYBACK_LIMIT_S = 20.0
GRACE_S = 0.5


async def wait_for_playback(
    queue: asyncio.Queue, *, grace_s: float = GRACE_S, limit_s: float = PLAYBACK_LIMIT_S
) -> None:
    """Return once everything queued for the caller has been taken for playback (or on timeout)."""
    waited = 0.0
    while not queue.empty() and waited < limit_s:
        await asyncio.sleep(0.05)
        waited += 0.05
    await asyncio.sleep(grace_s)  # the frame that was just taken is still being played


def task_error(task: asyncio.Task) -> BaseException | None:
    """The exception a finished task raised, or None if it was cancelled or ended cleanly.

    ``Task.exception()`` itself raises ``CancelledError`` for a cancelled task, which at hang-up
    escaped the call handler. A cancelled reader is a normal end of a call, not a failure.
    """
    return None if task.cancelled() else task.exception()


def log_pipeline_end(call_sid: str, task: asyncio.Task) -> None:
    """Say why the pipeline stopped; an exception here is a bug, not a normal hang-up."""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error("Pipeline for %s crashed: %r", call_sid, error)
    else:
        logger.info("Pipeline for %s finished; ending the call", call_sid)


async def session_of(pipeline: object, call_sid: str) -> object | None:
    """The finished conversation, for recording how the call ended; None if unavailable."""
    getter = getattr(pipeline, "session_for", None)
    if getter is None:
        return None
    try:
        return await getter(call_sid)
    except Exception:
        logger.exception("Could not read the session of %s", call_sid)
        return None
