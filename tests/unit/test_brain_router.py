"""The router: one short JSON-only call that says which tool (if any) this turn needs."""

from __future__ import annotations

import asyncio
import json
import logging
import re

import pytest

from shefa.brain import router
from shefa.brain.router import ROUTER_TOOLS, Route, route
from shefa.brain.state import GOALS, MOODS, CallState
from shefa.config.settings import settings


class FakeLLM:
    """Streams the router's answer a few characters at a time; `pause_after` waits after the
    text that far (as a slow server would) and `delay` before anything."""

    def __init__(
        self,
        text: str = "",
        *,
        error: Exception | None = None,
        delay: float = 0,
        pause_after: str = "",
        pause: float = 0,
    ):
        self.text = text
        self.error = error
        self.delay = delay
        self.pause_after = pause_after
        self.pause = pause
        self.calls: list[dict] = []
        self.closed = 0

    async def generate_stream(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error is not None:
                raise self.error
            sent = ""
            for i in range(0, len(self.text), 3):
                piece = self.text[i : i + 3]
                yield piece
                sent += piece
                if self.pause_after and sent.startswith(self.pause_after) and self.pause:
                    await asyncio.sleep(self.pause)
                    self.pause = 0
        finally:
            self.closed += 1


def _route(llm, said="কাল বিকেলে রহমান স্যারের সিরিয়াল দিন", history=None, **kw):
    history = history if history is not None else [{"role": "user", "content": said}]
    return asyncio.run(route(llm, CallState(), said, history, **kw))


def _out(tool="none", mood="calm", goal="information") -> str:
    return json.dumps({"tool": tool, "mood": mood, "goal": goal}, separators=(",", ":"))


def test_a_named_tool_with_mood_and_goal_is_read() -> None:
    got = _route(FakeLLM(_out("book", "rushed", "booking")))
    assert got == Route("book", "rushed", "booking")


def test_none_means_no_tool_but_keeps_mood_and_goal() -> None:
    got = _route(FakeLLM(_out("none", "angry", "information")))
    assert (got.tool, got.mood, got.goal) == (None, "angry", "information")


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"tool": "find_doctors", "mood": "calm", "goal": "booking"}',  # not a router tool
        "[1, 2]",
    ],
)
def test_unreadable_output_falls_back_to_a_plain_reply(text) -> None:
    got = _route(FakeLLM(text))
    assert (got.tool, got.mood, got.goal) == (None, None, None)
    assert got.error


@pytest.mark.parametrize(
    "text",
    [
        '{"tool": "book"}',  # mood and goal missing
        '{"tool": "book", "mood": "furious", "goal": "booking"}',  # not a mood
    ],
)
def test_a_readable_tool_stands_when_only_mood_or_goal_is_wrong(text) -> None:
    # Changed in fix round 1: the tool field comes first and is acted on as soon as it is
    # complete, so a bad mood or goal after it only loses the labels (the word rules keep them).
    got = _route(FakeLLM(text))
    assert (got.tool, got.mood, got.goal) == ("book", None, None)
    assert got.error


def test_an_error_falls_back_and_says_why() -> None:
    got = _route(FakeLLM(error=RuntimeError("server down")))
    assert (got.tool, got.mood, got.goal) == (None, None, None)
    assert "server down" in got.error


def test_a_slow_router_times_out(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "router_timeout_s", 0.05)
    got = _route(FakeLLM(_out("book"), delay=1))
    assert (got.tool, got.mood, got.goal) == (None, None, None)
    assert got.error == "timeout"


def test_router_timeout_setting_defaults_to_one_and_a_half_seconds() -> None:
    assert type(settings.brain).model_fields["router_timeout_s"].default == 1.5


def test_the_request_is_greedy_short_and_shape_enforced_by_the_server() -> None:
    llm = FakeLLM(_out())
    _route(llm)
    call = llm.calls[0]
    assert call["temperature"] == 0
    assert call["max_tokens"] <= 40
    pattern = call["extra_body"]["structured_outputs"]["regex"]
    # every allowed answer matches the enforced shape, anything else does not
    for tool in (*ROUTER_TOOLS, "none"):
        for mood in MOODS:
            for goal in GOALS:
                assert re.fullmatch(pattern, _out(tool, mood, goal))
    assert not re.fullmatch(pattern, _out("find_doctors"))
    assert not re.fullmatch(pattern, '{"tool": "none", "mood": "calm", "goal": "unknown"}')


def test_find_doctors_is_not_a_router_choice() -> None:
    assert "find_doctors" not in ROUTER_TOOLS
    assert set(ROUTER_TOOLS) == {
        "free_times",
        "book",
        "lookup_booking",
        "cancel_booking",
        "reschedule_booking",
        "request_callback",
        "hand_over",
        "end_call",
    }


def test_prompt_is_fixed_first_then_the_last_turns_and_the_callers_line() -> None:
    history = [
        {"role": "assistant", "content": "GREETING"},
        {"role": "user", "content": "OLD-1"},
        {"role": "assistant", "content": "OLD-2"},
        {"role": "user", "content": "OLD-3"},
        {"role": "assistant", "content": "OLD-4"},
        {"role": "user", "content": "OLD-5"},
        {"role": "assistant", "content": "OLD-6"},
        {"role": "user", "content": "CALLER-NOW"},
    ]
    llm = FakeLLM(_out())
    _route(llm, said="CALLER-NOW", history=history)
    messages = llm.calls[0]["messages"]
    assert messages[0] == {"role": "system", "content": router.INSTRUCTIONS}
    turn = messages[-1]["content"]
    assert turn.rstrip().endswith("CALLER-NOW")
    assert turn.count("CALLER-NOW") == 1
    assert "OLD-3" in turn and "OLD-6" in turn
    assert "GREETING" not in turn and "OLD-1" not in turn  # only the last four turns


def test_instructions_name_every_tool_and_say_questions_are_none() -> None:
    for tool in ROUTER_TOOLS:
        assert tool in router.INSTRUCTIONS
    assert "find_doctors" not in router.INSTRUCTIONS
    assert "ফি কত" in router.INSTRUCTIONS  # an information example routed to none


@pytest.fixture
def fresh_warnings(monkeypatch):
    monkeypatch.setattr(router, "_warned", router._Warned())


def test_a_failing_router_is_logged_but_not_on_every_turn(fresh_warnings, caplog, monkeypatch):
    # A server that stops accepting the output shape fails every turn: one warning a minute says
    # so without flooding the log.
    clock = [1000.0]
    monkeypatch.setattr(router.time, "monotonic", lambda: clock[0])
    caplog.set_level(logging.WARNING, logger="shefa.brain.router")
    for _ in range(5):
        _route(FakeLLM(error=RuntimeError("structured_outputs rejected")))
    assert len(caplog.records) == 1
    assert "structured_outputs rejected" in caplog.records[0].getMessage()
    clock[0] += router.WARN_EVERY_S + 1
    _route(FakeLLM("not json"))
    assert len(caplog.records) == 2
    assert "4 more" in caplog.records[1].getMessage()


def test_a_router_that_answers_logs_nothing(fresh_warnings, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="shefa.brain.router")
    _route(FakeLLM(_out("book", "calm", "booking")))
    assert caplog.records == []


# --- streaming: the tool is known before the rest of the answer -------------------------------


def _streamed(llm, **kw):
    seen: list[tuple[str | None, bool]] = []

    async def run():
        task = None

        def on_tool(tool):
            seen.append((tool, task.done() if task else None))

        task = asyncio.ensure_future(
            route(llm, CallState(), "x", [{"role": "user", "content": "x"}], on_tool=on_tool, **kw)
        )
        return await task

    found = asyncio.run(run())
    return found, seen


def test_none_is_told_as_soon_as_the_tool_field_is_complete() -> None:
    text = _out("none", "calm", "information")
    found, seen = _streamed(FakeLLM(text, pause_after='{"tool":"none",', pause=0.2))
    assert seen == [(None, False)]  # told while the rest was still coming
    assert found == Route(None, "calm", "information")


def test_a_tool_is_told_early_too() -> None:
    found, seen = _streamed(
        FakeLLM(_out("book", "rushed", "booking"), pause_after='{"tool":"book"', pause=0.1)
    )
    assert seen == [("book", False)]
    assert found.tool == "book"


def test_a_malformed_stream_tells_nothing_and_is_no_route() -> None:
    found, seen = _streamed(FakeLLM("I think you should book."))
    assert seen == []
    assert (found.tool, found.mood, found.goal) == (None, None, None)
    assert found.error


def test_a_tool_that_is_not_a_choice_is_never_told() -> None:
    found, seen = _streamed(FakeLLM('{"tool":"find_doctors","mood":"calm","goal":"booking"}'))
    assert seen == []
    assert found.tool is None


def test_a_stream_that_stops_after_the_tool_keeps_the_tool() -> None:
    found, seen = _streamed(FakeLLM('{"tool":"book","mo'))
    assert seen == [("book", False)]
    assert (found.tool, found.mood, found.goal) == ("book", None, None)
    assert found.error


def test_the_router_stream_is_closed_on_timeout(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "router_timeout_s", 0.05)
    llm = FakeLLM(_out(), pause_after="{", pause=1)
    found, seen = _streamed(llm)
    assert found.error == "timeout"
    assert seen == []
    assert llm.closed == 1


def test_a_timeout_after_the_tool_was_read_is_not_logged(fresh_warnings, caplog, monkeypatch):
    # The tool decided the turn; only mood and goal were late. That is no router failure.
    monkeypatch.setattr(settings.brain, "router_timeout_s", 0.05)
    caplog.set_level(logging.WARNING, logger="shefa.brain.router")
    for tool in ("none", "book"):
        found, seen = _streamed(FakeLLM(_out(tool), pause_after='{"tool":"' + tool, pause=1))
        assert found.error == "timeout"
        assert seen == [(None if tool == "none" else tool, False)]
    assert caplog.records == []
