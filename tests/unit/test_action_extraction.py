"""Tests for the structured-JSON action router and its pipeline mode."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from sefa.audio import AudioFrame
from sefa.config.settings import settings
from sefa.models.base import Language, StreamEvent, ToolDefinition
from sefa.pipeline.actions import (
    confirmation_text,
    extract_action,
    extractor_system_prompt,
    parse_action,
    resolve_arguments,
    resolve_relative_day,
    tool_result_note,
)
from sefa.pipeline.voice_pipeline import VoicePipeline
from sefa.session.manager import CallSession

_BOOK = ToolDefinition(
    name="book_appointment",
    description="Book an appointment for the patient.",
    parameters={
        "type": "object",
        "properties": {"date": {"type": "string"}},
        "required": ["date"],
    },
)
_SLOTS = ToolDefinition(
    name="check_appointment_slots",
    description="Check available appointment slots.",
    parameters={"type": "object", "properties": {}},
)
_TOOLS = [_BOOK, _SLOTS]
_KNOWN = {t.name for t in _TOOLS}


class _FakeRouterLLM:
    def __init__(self, *, text: str | None = None, error: Exception | None = None):
        self._text = text
        self._error = error
        self.calls: list[dict] = []

    async def generate(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools, "kwargs": kwargs})
        if self._error is not None:
            raise self._error
        return SimpleNamespace(text=self._text)


def _session(*turns: tuple[str, str]) -> CallSession:
    session = CallSession(call_sid="SID-R", language=Language.BANGLA)
    for role, content in turns:
        session.add_turn(role, content, Language.BANGLA)
    return session


class TestParseAction:
    @pytest.mark.parametrize(
        "payload, arguments",
        [
            ({"tool": "book_appointment", "arguments": {"date": "tomorrow"}}, {"date": "tomorrow"}),
            ({"tool": "check_appointment_slots", "arguments": {}}, {}),
        ],
    )
    def test_known_tool_decodes(self, payload, arguments):
        action = parse_action(json.dumps(payload), _KNOWN)
        assert action is not None
        assert action.name == payload["tool"]
        assert action.arguments == arguments

    def test_null_tool_is_no_action(self):
        assert parse_action(json.dumps({"tool": None, "arguments": {}}), _KNOWN) is None

    def test_missing_tool_is_no_action(self):
        assert parse_action(json.dumps({"arguments": {}}), _KNOWN) is None

    def test_unknown_tool_is_rejected(self):
        payload = {"tool": "delete_everything", "arguments": {}}
        assert parse_action(json.dumps(payload), _KNOWN) is None

    def test_non_dict_arguments_are_rejected(self):
        payload = {"tool": "book_appointment", "arguments": ["tomorrow"]}
        assert parse_action(json.dumps(payload), _KNOWN) is None

    def test_non_json_is_no_action(self):
        assert parse_action("I will check that for you", _KNOWN) is None

    def test_json_non_object_is_no_action(self):
        assert parse_action('[{"tool": "book_appointment"}]', _KNOWN) is None

    def test_missing_arguments_are_rejected(self):
        assert parse_action(json.dumps({"tool": "book_appointment"}), _KNOWN) is None


class TestExtractorPrompt:
    def test_lists_every_tool_and_the_json_shape(self):
        prompt = extractor_system_prompt(_TOOLS)
        assert "book_appointment" in prompt
        assert "check_appointment_slots" in prompt
        assert '"tool": <name or null>' in prompt
        assert '"arguments": {}' in prompt
        assert '"date"' in prompt

    def test_injects_todays_date_so_relative_days_resolve(self):
        prompt = extractor_system_prompt(_TOOLS, today=date(2026, 10, 10))
        assert "2026-10-10" in prompt
        assert "today" in prompt.lower()
        assert "আগামীকাল" in prompt


class TestResolveRelativeDay:
    @pytest.mark.parametrize(
        "phrase, expected",
        [
            ("today", "2026-10-10"),
            ("Today", "2026-10-10"),
            ("আজ", "2026-10-10"),
            ("tomorrow", "2026-10-11"),
            ("আগামীকাল", "2026-10-11"),
            ("কাল", "2026-10-11"),
            ("day after tomorrow", "2026-10-12"),
            ("পরশু", "2026-10-12"),
        ],
    )
    def test_recognised_phrases_map_to_absolute_dates(self, phrase, expected):
        assert resolve_relative_day(phrase, date(2026, 10, 10)) == expected

    def test_unrecognised_text_is_not_a_date(self):
        assert resolve_relative_day("next week sometime", date(2026, 10, 10)) is None

    def test_non_string_is_not_a_date(self):
        assert resolve_relative_day(20260110, date(2026, 10, 10)) is None


class TestResolveArguments:
    def test_relative_date_terms_become_absolute(self):
        args = {"date": "আগামীকাল", "doctor_name": "করিম"}
        assert resolve_arguments(args, date(2026, 10, 10)) == {
            "date": "2026-10-11",
            "doctor_name": "করিম",
        }

    def test_all_date_keys_are_resolved(self):
        args = {"date": "tomorrow", "new_date": "today"}
        resolved = resolve_arguments(args, date(2026, 10, 10))
        assert resolved == {"date": "2026-10-11", "new_date": "2026-10-10"}

    def test_already_absolute_dates_pass_through_untouched(self):
        args = {"date": "2026-12-01"}
        assert resolve_arguments(args, date(2026, 10, 10)) == {"date": "2026-12-01"}

    def test_free_text_date_is_left_as_is(self):
        args = {"date": "some time next month"}
        assert resolve_arguments(args, date(2026, 10, 10)) == {
            "date": "some time next month"
        }

    def test_does_not_mutate_the_input(self):
        args = {"date": "tomorrow"}
        resolve_arguments(args, date(2026, 10, 10))
        assert args == {"date": "tomorrow"}


class TestToolResultNote:
    def test_grounds_the_confirmation_on_the_result(self):
        note = tool_result_note(
            "book_appointment", {"success": True, "appointment_id": "APT-1"}
        )
        assert "book_appointment" in note
        assert '"success": true' in note
        assert "APT-1" in note
        assert "ONLY on this result" in note


class TestExtractAction:
    async def test_swaps_the_system_prompt_and_asks_for_json(self):
        llm = _FakeRouterLLM(
            text=json.dumps(
                {"tool": "book_appointment", "arguments": {"date": "tomorrow"}}
            )
        )
        session = _session(("user", "আমি কাল ১০টায় আসতে চাই"))

        action = await extract_action(llm, session, today=date(2026, 10, 10))

        assert action is not None
        assert action.name == "book_appointment"
        assert action.arguments == {"date": "2026-10-11"}
        call = llm.calls[0]
        assert call["messages"][0]["role"] == "system"
        assert "book_appointment" in call["messages"][0]["content"]
        assert "2026-10-10" in call["messages"][0]["content"]
        assert call["messages"][-1]["role"] == "user"
        assert "আমি কাল ১০টায় আসতে চাই" in call["messages"][-1]["content"]
        assert call["kwargs"]["response_format"] == {"type": "json_object"}

    async def test_llm_errors_are_swallowed_as_no_action(self):
        llm = _FakeRouterLLM(error=RuntimeError("ollama is on fire"))

        assert await extract_action(llm, _session(("user", "হ্যালো"))) is None

    async def test_unknown_tool_from_the_router_is_no_action(self):
        llm = _FakeRouterLLM(
            text=json.dumps({"tool": "make_the_coffee", "arguments": {}})
        )

        assert await extract_action(llm, _session(("user", "কফি দাও"))) is None

    async def test_uses_the_supplied_tool_set(self):
        llm = _FakeRouterLLM(
            text=json.dumps(
                {"tool": "book_appointment", "arguments": {"date": "tomorrow"}}
            )
        )

        action = await extract_action(llm, _session(("user", "বুক করুন")), tools=[_BOOK])

        assert action is not None
        assert action.name == "book_appointment"
        assert "check_appointment_slots" not in llm.calls[0]["messages"][0]["content"]

    async def test_relative_dates_are_absolute_before_the_action_returns(self):
        today = date(2026, 10, 10)
        llm = _FakeRouterLLM(
            text=json.dumps(
                {"tool": "book_appointment", "arguments": {"date": "আগামীকাল"}}
            )
        )

        action = await extract_action(
            llm, _session(("user", "আগামীকাল বুক করুন")), today=today
        )

        assert action is not None
        assert action.arguments == {"date": "2026-10-11"}
        assert "2026-10-10" in llm.calls[0]["messages"][0]["content"]


class _FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize_stream(self, text: str, language: str = "en"):
        self.spoken.append(text)
        yield AudioFrame(b"\x00" * 1600, rate=22050)


class _Sink:
    def __init__(self) -> None:
        self.frames: list[AudioFrame] = []

    async def __call__(self, frame: AudioFrame) -> None:
        self.frames.append(frame)


class _ScriptedLLM:
    """Streams a scripted reply per call, and answers the router call."""

    def __init__(self, *, routed_action: dict | None, replies: list[list[StreamEvent]]):
        self.routed_action = routed_action
        self.replies = replies
        self.generate_calls: list[dict] = []
        self.stream_calls: list[dict] = []

    async def generate(self, messages, tools=None, **kwargs):
        self.generate_calls.append({"messages": messages, "kwargs": kwargs})
        text = json.dumps(self.routed_action) if self.routed_action else "{}"
        return SimpleNamespace(text=text)

    async def generate_events(self, messages, tools=None, **kwargs):
        self.stream_calls.append({"messages": messages, "tools": tools})
        events = self.replies[min(len(self.stream_calls) - 1, len(self.replies) - 1)]
        for event in events:
            yield event


class TestConfirmationText:
    def test_booking_renders_the_facts_verbatim_in_bangla(self):
        text = confirmation_text(
            "book_appointment",
            {
                "success": True,
                "appointment_id": "APT-9",
                "date": "2026-12-01",
                "time": "10:00",
                "doctor": "ডাক্তার করিম",
            },
            "bn",
        )
        assert text is not None
        assert "2026-12-01" in text
        assert "10:00" in text
        assert "ডাক্তার করিম" in text
        assert "APT-9" in text

    def test_booking_english(self):
        text = confirmation_text(
            "book_appointment",
            {
                "success": True,
                "appointment_id": "APT-9",
                "date": "2026-12-01",
                "time": "10:00",
                "doctor": "Dr. Karim",
            },
            "en",
        )
        assert text == (
            "Your appointment is booked for 2026-12-01 at 10:00 with "
            "Dr. Karim. Your reference is APT-9."
        )

    def test_slots_lists_every_available_time(self):
        text = confirmation_text(
            "check_appointment_slots",
            {
                "date": "2026-12-01",
                "available_slots": [{"time": "09:00"}, {"time": "10:30"}],
            },
            "bn",
        )
        assert text is not None
        assert "09:00" in text
        assert "10:30" in text

    def test_cancel_confirms_the_reference(self):
        text = confirmation_text(
            "cancel_appointment",
            {"success": True, "appointment_id": "APT-1", "cancelled": True},
            "en",
        )
        assert text == "Your appointment APT-1 has been cancelled."

    def test_reschedule_names_the_new_slot(self):
        text = confirmation_text(
            "reschedule_appointment",
            {
                "success": True,
                "appointment_id": "APT-1",
                "new_date": "2026-12-02",
                "new_time": "11:00",
            },
            "en",
        )
        assert text == "Your appointment APT-1 is rescheduled to 2026-12-02 at 11:00."

    def test_untemplated_tool_returns_none(self):
        assert confirmation_text("verify_patient", {"verified": True}, "en") is None

    def test_error_result_returns_none(self):
        assert confirmation_text("book_appointment", {"error": "boom"}, "en") is None

    def test_failed_booking_returns_none(self):
        assert (
            confirmation_text("book_appointment", {"success": False}, "en") is None
        )


class TestGenerateReplyExtractMode:
    async def test_acts_and_speaks_a_deterministic_confirmation(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
        llm = _ScriptedLLM(
            routed_action={
                "tool": "book_appointment",
                "arguments": {"date": "2026-12-01"},
            },
            replies=[[StreamEvent(text="এক মুহূর্ত।")]],
        )
        executed: list[tuple[str, dict]] = []

        async def _fake_execute(name: str, arguments: dict, session: Any):
            executed.append((name, arguments))
            return {
                "success": True,
                "appointment_id": "APT-9",
                "date": "2026-12-01",
                "time": "10:00",
                "doctor": "ডাক্তার করিম",
            }

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.execute_tool", _fake_execute
        )
        tts = _FakeTTS()
        session = _session(("user", "আমাকে কাল অ্যাপয়েন্টমেন্ট দিন"))

        reply = await VoicePipeline()._generate_reply(llm, tts, session, _Sink())

        assert executed == [("book_appointment", {"date": "2026-12-01"})]
        assert "2026-12-01" in reply
        assert "APT-9" in reply
        assert tts.spoken == ["এক মুহূর্ত।", reply]
        # facts never go back through the model
        assert len(llm.stream_calls) == 1

    async def test_untemplated_tool_falls_back_to_a_grounded_model_reply(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
        llm = _ScriptedLLM(
            routed_action={"tool": "verify_patient", "arguments": {"name": "রহিম"}},
            replies=[
                [StreamEvent(text="এক মুহূর্ত।")],
                [StreamEvent(text="ধন্যবাদ, আপনি যাচাই হয়েছেন।")],
            ],
        )

        async def _fake_execute(name: str, arguments: dict, session: Any):
            return {"verified": True, "patient_id": "P1"}

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.execute_tool", _fake_execute
        )
        session = _session(("user", "আমার নাম রহিম"))

        reply = await VoicePipeline()._generate_reply(llm, _FakeTTS(), session, _Sink())

        assert reply == "ধন্যবাদ, আপনি যাচাই হয়েছেন।"
        assert len(llm.stream_calls) == 2
        grounding = llm.stream_calls[1]["messages"][0]
        assert grounding["role"] == "system"
        assert "P1" in grounding["content"]

    async def test_no_action_streams_a_single_reply(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
        llm = _ScriptedLLM(
            routed_action=None,
            replies=[[StreamEvent(text="আমি সাহায্য করতে পারি।")]],
        )
        called: list[str] = []

        async def _fake_execute(name: str, arguments: dict, session: Any):
            called.append(name)
            return {}

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.execute_tool", _fake_execute
        )
        session = _session(("user", "আপনি কেমন আছেন?"))

        reply = await VoicePipeline()._generate_reply(llm, _FakeTTS(), session, _Sink())

        assert reply == "আমি সাহায্য করতে পারি।"
        assert called == []
        assert len(llm.stream_calls) == 1


class TestGenerateReplyNativeMode:
    async def test_executes_declared_tool_calls_and_confirms(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings.pipeline.llm, "tool_calls", True)
        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.get_tool_definitions", lambda: _TOOLS
        )
        call = {"id": "c1", "name": "book_appointment", "arguments": {"date": "tomorrow"}}
        llm = _ScriptedLLM(
            routed_action=None,
            replies=[
                [
                    StreamEvent(text="এক মুহূর্ত।"),
                    StreamEvent(tool_calls=[call], finish_reason="tool_calls"),
                ],
                [StreamEvent(text="বুক হয়ে গেছে।")],
            ],
        )
        executed: list[str] = []

        async def _fake_execute(name: str, arguments: dict, session: Any):
            executed.append(name)
            return {"success": True}

        monkeypatch.setattr(
            "sefa.pipeline.voice_pipeline.execute_tool", _fake_execute
        )
        session = _session(("user", "বুক করুন"))

        reply = await VoicePipeline()._generate_reply(llm, _FakeTTS(), session, _Sink())

        assert reply == "বুক হয়ে গেছে।"
        assert executed == ["book_appointment"]
        assert llm.stream_calls[0]["tools"] == _TOOLS
        assert session.history[-1].role == "tool"


class TestConfigFlag:
    def test_tool_calls_defaults_true(self):
        from sefa.config.settings import LLMConfig

        assert LLMConfig().tool_calls is True
