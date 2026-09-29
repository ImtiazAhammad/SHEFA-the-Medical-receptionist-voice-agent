"""Turn-failure taxonomy and retry policy for the conversation loop (D-ENG12).

The pre-fix loop swallowed transcribe-stage exceptions with a bare
``except Exception`` and continued, so a stuck STT or TTS adapter drove an
error hot loop and ``escalation.max_transfer_attempts`` was declared but never
read. This module names the failures the pipeline can actually classify, the
sentinel it raises for an unusable LLM result, and the exponential backoff it
applies between retries so a transient fault cannot spin the CPU.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class FailureKind(StrEnum):
    """The named rescue paths of the turn loop, in the plan's taxonomy."""

    STT_TIMEOUT = "stt_timeout"
    STT_ERROR = "stt_error"
    EMPTY_TRANSCRIPTION = "empty_transcription"
    MALFORMED_LLM_OUTPUT = "malformed_llm_output"
    TTS_FAILURE = "tts_failure"


class MalformedLLMOutputError(ValueError):
    """The LLM returned nothing the pipeline can speak or act on.

    Raised by :func:`require_llm_result` so the call site can classify the
    failure instead of crashing or swallowing it.
    """


def backoff_delay(
    consecutive_failures: int, *, base: float = 0.25, cap: float = 2.0
) -> float:
    """Exponential backoff in seconds: ``base * 2 ** (n - 1)``, capped.

    The cap matters twice: a stuck adapter must not sleep the conversation
    into dead air, and ``max_transfer_attempts`` still ends the call, so the
    longest a patient waits between failed retries is ``cap`` seconds.
    """
    if consecutive_failures < 1:
        return 0.0
    return min(base * (2 ** (consecutive_failures - 1)), cap)


def require_llm_result(result: Any) -> Any:
    """Validate an LLM output; raise :class:`MalformedLLMOutput` if unusable.

    A ``None`` result or a missing/non-string ``text`` is malformed; an empty
    ``text`` with real tool calls is a legitimate tool-only turn.
    """
    if result is None or not isinstance(getattr(result, "text", None), str):
        raise MalformedLLMOutputError(f"LLM output unusable: {result!r}")
    return result