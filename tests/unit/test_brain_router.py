"""The router: one short JSON-only call that says which tool (if any) this turn needs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from types import SimpleNamespace

import pytest

from shefa.brain import router
from shefa.brain.router import ROUTER_TOOLS, Route, route
from shefa.brain.state import GOALS, MOODS, CallState
from shefa.config.settings import settings


class FakeLLM:
    def __init__(self, text: str = "", *, error: Exception | None = None, delay: float = 0):
        self.text = text
        self.error = error
        self.delay = delay
        self.calls: list[dict] = []

    async def generate(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.text)


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
        '{"tool": "book"}',  # fields missing
        '{"tool": "find_doctors", "mood": "calm", "goal": "booking"}',  # not a router tool
        '{"tool": "book", "mood": "furious", "goal": "booking"}',  # not a mood
        "[1, 2]",
    ],
)
def test_unreadable_output_falls_back_to_a_plain_reply(text) -> None:
    got = _route(FakeLLM(text))
    assert (got.tool, got.mood, got.goal) == (None, None, None)
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
