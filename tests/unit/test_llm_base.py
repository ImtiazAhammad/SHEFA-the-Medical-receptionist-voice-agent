"""Tests for the default ``BaseLLM.generate_events`` bridge.

`OpenAICompatibleLLM` streams natively, but an adapter that only implements the
abstract ``generate`` still has to work: the pipeline consumes
``generate_events`` unconditionally. The base default wraps one ``generate``
result in a single event so a non-streaming adapter keeps working (tools and
all) instead of raising ``AttributeError``. A ``None`` result is bridged to an
empty event so the pipeline classifies it as malformed rather than crashing.
"""

from __future__ import annotations

from typing import Any

from sefa.models.base import BaseLLM, Language, LLMResult, StreamEvent

_CALL = {"id": "c1", "name": "book_appointment", "arguments": "{}"}


class _GenerateOnlyLLM(BaseLLM):
    """Implements only the abstract surface; inherits the default bridge."""

    def __init__(self, result: Any) -> None:
        self.result = result

    async def generate(
        self, messages: list[dict[str, str]], tools: Any = None, **kwargs: Any
    ) -> Any:
        return self.result

    async def generate_stream(
        self, messages: list[dict[str, str]], tools: Any = None, **kwargs: Any
    ):
        yield ""  # pragma: no cover - not exercised; present for the ABC

    async def close(self) -> None:
        return None


async def _events(result: Any) -> list[StreamEvent]:
    llm = _GenerateOnlyLLM(result)
    return [event async for event in llm.generate_events([])]


async def test_the_default_bridges_a_result_to_one_event() -> None:
    result = LLMResult(
        text="Tuesday at ten.",
        tool_calls=[_CALL],
        finish_reason="tool_calls",
        language=Language.ENGLISH,
    )

    events = await _events(result)

    assert events == [
        StreamEvent(text="Tuesday at ten.", tool_calls=[_CALL], finish_reason="tool_calls")
    ]


async def test_the_default_is_null_safe_for_a_malformed_result() -> None:
    events = await _events(None)

    assert events == [StreamEvent(text="", tool_calls=[], finish_reason=None)]
