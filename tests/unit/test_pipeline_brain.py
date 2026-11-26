# ruff: noqa: F811 - the brain tests' fixtures are imported here and used by name
"""Task 11: the brain behind `pipeline.engine`, its guided fallback, and a cancelled turn.

The brain's own tests fake the executor and the model; these drive the brain through the voice
pipeline (`handle_text`, `_generate_reply`, the greeting) and check what the pipeline keeps and
what the brain keeps agree, whatever happens to the turn.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import random
import sqlite3
import struct
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from shefa.audio import AudioFrame
from shefa.brain import actions as brain_actions
from shefa.brain import config as brain_config
from shefa.brain import engine as brain_engine
from shefa.brain import greeting as brain_greeting
from shefa.brain import safe
from shefa.brain.engine import Brain
from shefa.brain.state import CallState, load, save
from shefa.clinic import default_clinic_store
from shefa.config.settings import settings
from shefa.models.base import Language, LLMResult, StreamEvent, STTResult
from shefa.models.registry import registry
from shefa.pipeline.error_taxonomy import MalformedLLMOutputError
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession, SessionManager
from tests.unit.test_brain_actions import (  # noqa: F401 - fixtures used by name
    BOOK_LINE,
    BOOKED,
    TODAY,
    FakeLLM,
    Recorder,
    example_clinic,
    executor,
    frozen_clock,
    identified_session,
    read_back_booking,
    route_json,
    say,
)


class _Hang:
    """A `speak` that never finishes: the caller barges in while it plays."""

    def __init__(self) -> None:
        self.started: list[str] = []

    async def __call__(self, text: str) -> None:
        self.started.append(text)
        await asyncio.Event().wait()


async def _cancel_once(turn: asyncio.Task, ready) -> None:
    while not ready():
        await asyncio.sleep(0.001)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn


# --- a cancelled turn: the brain's state matches what happened ------------------------------


def test_a_yes_cancelled_while_its_confirmation_plays_never_books_twice(executor):
    session, _, _ = read_back_booking(executor)
    session.add_turn("user", "হ্যাঁ")
    hang = _Hang()

    async def run():
        turn = asyncio.create_task(Brain().turn(session, "হ্যাঁ", FakeLLM(), hang, today=TODAY))
        await _cancel_once(turn, lambda: hang.started)

    asyncio.run(run())
    assert [name for name, _ in executor.ran] == ["book_appointment"]
    state = load(session)
    assert state.pending is None  # the booking ran: its read-back is spent
    assert state.done and state.done[-1]["kind"] == "book"
    assert session.metadata["brain_trace"][-1]["cancelled"] is True
    say(session, "হ্যাঁ", FakeLLM("জি।", route=route_json()))
    assert [name for name, _ in executor.ran] == ["book_appointment"]  # not again


def test_a_yes_cancelled_before_it_settles_changes_nothing(executor, monkeypatch):
    session, _, _ = read_back_booking(executor)
    session.add_turn("user", "হ্যাঁ")
    before = copy.deepcopy(session.metadata)
    from shefa.brain import engine

    started = []

    class _SlowSearch:
        def search(self, said):
            started.append(said)
            import time

            time.sleep(0.2)
            return []

    monkeypatch.setattr(engine, "retriever_for", lambda clinic: _SlowSearch())

    async def run():
        turn = asyncio.create_task(Brain().turn(session, "হ্যাঁ", FakeLLM(), Recorder(), today=TODAY))
        await _cancel_once(turn, lambda: started)

    asyncio.run(run())
    assert executor.ran == []  # the read-back was not executed by the cancelled turn
    assert session.metadata == before  # and the brain left no trace of the turn


def test_a_read_back_cut_off_by_a_barge_in_is_not_left_waiting_for_a_yes(executor):
    executor.previews["book_appointment"] = {"preview": BOOKED | {"serial_no": None}}
    executor.results["book_appointment"] = BOOKED
    session = identified_session()
    session.add_turn("user", BOOK_LINE)
    hang = _Hang()
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))

    async def run():
        turn = asyncio.create_task(Brain().turn(session, BOOK_LINE, llm, hang, today=TODAY))
        await _cancel_once(turn, lambda: hang.started)

    asyncio.run(run())
    assert hang.started  # the read-back began
    assert load(session).pending is None  # but nobody can say yes to half of it
    assert session.metadata["brain_trace"][-1]["cancelled"] is True
    say(session, "হ্যাঁ", FakeLLM("জি।", route=route_json()))
    assert executor.ran == []


# --- the pipeline: which engine answers ---------------------------------------------------------


GUIDED_REPLY = "guided says this"
_REAL_GUIDED_REPLY = VoicePipeline._reply  # before any test stubs it


def _connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "http://llm/v1/chat"))


class FakeBrain:
    """Stands in for `Brain`: says `lines`, then raises `error` (if any), or hangs."""

    lines: list[str] = []
    error: BaseException | None = None
    hang = False
    end_state: str | None = None
    seen: list[tuple[str, str]] = []

    async def turn(self, session, said, llm, speak, *, today=None, cues=None):
        last_user = next(t.content for t in reversed(session.history) if t.role == "user")
        FakeBrain.seen.append((said, last_user))
        for line in FakeBrain.lines:
            await speak(line)
        if FakeBrain.hang:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if FakeBrain.lines:  # as the real brain does: what was said is kept
                    session.metadata.setdefault("brain_trace", []).append({"cancelled": True})
                raise
        if FakeBrain.error is not None:
            raise FakeBrain.error
        if FakeBrain.end_state:
            session.state = FakeBrain.end_state
        return " ".join(FakeBrain.lines)


class _QuietLLM:
    async def generate(self, messages, tools=None, **kwargs):
        return LLMResult(text="{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="ঠিক আছে।")

    async def close(self):
        pass


@pytest.fixture
def agent(monkeypatch):
    """Engine `agent` with the fake brain; the guided path answers with a fixed line."""
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    monkeypatch.setattr(settings.languages, "primary", "bn")
    FakeBrain.lines, FakeBrain.error, FakeBrain.hang, FakeBrain.end_state = (
        ["জি, বলুন।"],
        None,
        False,
        None,
    )
    FakeBrain.seen = []
    monkeypatch.setattr(brain_engine, "Brain", FakeBrain)
    guided_calls = []

    async def guided_reply(self, llm, tts, session, put_playback):
        guided_calls.append(session.history[-1].content)
        return GUIDED_REPLY

    monkeypatch.setattr(VoicePipeline, "_reply", guided_reply)
    monkeypatch.setattr(registry, "_llm", _QuietLLM())

    async def fixed_greeting(llm, config, **kw):
        return "স্বাগতম।"

    monkeypatch.setattr(brain_greeting, "greeting", fixed_greeting)
    return SimpleNamespace(guided=guided_calls)


@pytest.mark.parametrize(
    ("held", "engine"),
    [("agent", "agent"), ("guided", "guided"), ("banana", "guided"), (None, "guided"),
     ("Agent", "guided")],
)  # fmt: skip
def test_only_exactly_agent_selects_the_brain(held, engine):
    session = CallSession(call_sid="CA-engine")
    session.metadata["brain_config"] = {} if held is None else {"engine": held}
    assert VoicePipeline._engine(session) == engine


async def test_the_engine_is_read_once_per_call(monkeypatch):
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    session = CallSession(call_sid="CA-frozen")
    assert await VoicePipeline()._engine_ready(session) == "agent"
    monkeypatch.setattr(settings.pipeline, "engine", "guided")
    assert await VoicePipeline()._engine_ready(session) == "agent"  # frozen for the call
    assert VoicePipeline._engine(session) == "agent"


async def test_a_typed_turn_goes_through_the_brain_with_the_history_string(agent):
    pipe = VoicePipeline()
    out = await pipe.handle_text("CA-agent", "  ডাক্তার রহমান কবে বসেন?  ")
    assert out["reply"] == "জি, বলুন।" and agent.guided == []
    said, stored = FakeBrain.seen[-1]
    assert said == stored == "  ডাক্তার রহমান কবে বসেন?  "  # the same string the history keeps
    session = await pipe.session_for("CA-agent")
    assert [t.role for t in session.history] == ["assistant", "user", "assistant"]
    assert session.history[-1].content == "জি, বলুন।"


@pytest.mark.parametrize(
    "error",
    [_connection_error(), TimeoutError(), ConnectionError("down"),
     MalformedLLMOutputError("empty")],
)  # fmt: skip
async def test_a_brain_failing_before_it_speaks_gets_the_guided_reply(agent, error):
    FakeBrain.lines, FakeBrain.error = [], error
    pipe = VoicePipeline()
    out = await pipe.handle_text("CA-fall", "ফি কত?")
    assert out["reply"] == GUIDED_REPLY and agent.guided == ["ফি কত?"]
    session = await pipe.session_for("CA-fall")
    assert session.metadata["brain_fallbacks"] == 1
    FakeBrain.error = None
    FakeBrain.lines = ["জি।"]
    again = await pipe.handle_text("CA-fall", "আচ্ছা")
    assert again["reply"] == "জি।"  # the next turn tries the brain again
    assert session.metadata["brain_fallbacks"] == 1


async def test_review_focus_5_a_brain_failing_after_it_spoke_keeps_what_was_said(agent):
    FakeBrain.lines, FakeBrain.error = ["ডাক্তার রহমান শনিবার বসেন।"], _connection_error()
    pipe = VoicePipeline()
    out = await pipe.handle_text("CA-half", "ডাক্তার রহমান কবে বসেন?")
    assert out["reply"] == "ডাক্তার রহমান শনিবার বসেন।"
    assert agent.guided == []  # never a second answer over the first
    session = await pipe.session_for("CA-half")
    assert "brain_fallbacks" not in session.metadata


async def test_a_brain_bug_before_it_speaks_gets_the_guided_reply_and_a_traceback(agent, caplog):
    # Fix round 1, ruling 3: any Exception before speech (a bug too) never silences the turn.
    FakeBrain.lines, FakeBrain.error = [], KeyError("slot")
    pipe = VoicePipeline()
    with caplog.at_level("ERROR"):
        out = await pipe.handle_text("CA-bug", "ফি কত?")
    assert out["reply"] == GUIDED_REPLY and agent.guided == ["ফি কত?"]
    assert any(r.exc_info and r.exc_info[0] is KeyError for r in caplog.records)
    session = await pipe.session_for("CA-bug")
    assert session.metadata["brain_fallbacks"] == 1


async def test_a_brain_bug_after_it_spoke_ends_the_turn_there(agent):
    FakeBrain.lines, FakeBrain.error = ["জি।"], KeyError("slot")
    out = await VoicePipeline().handle_text("CA-bug2", "ফি কত?")
    assert out["reply"] == "জি।" and agent.guided == []


async def test_a_voice_failure_still_goes_to_the_voice_rescue(agent):
    from shefa.pipeline.voice_pipeline import _SynthesisError

    FakeBrain.lines, FakeBrain.error = [], _SynthesisError("tts down")
    session = CallSession(call_sid="CA-tts", language=Language.BANGLA)
    session.add_turn("user", "ফি কত?")
    with pytest.raises(_SynthesisError):
        await VoicePipeline()._generate_reply(_QuietLLM(), _SilentVoice(), session, _sink)
    assert agent.guided == []


async def test_a_fallback_voids_the_brains_open_read_back(agent):
    session = CallSession(call_sid="CA-void", language=Language.BANGLA)
    state = CallState(pending={"tool": "book", "executor": "book_appointment", "args": {}})
    save(session, state)
    session.metadata[brain_actions.WAIT] = {"for": "phone", "tool": "book", "args": {}}
    session.add_turn("user", "ফি কত?")
    FakeBrain.lines, FakeBrain.error = [], _connection_error()
    reply = await VoicePipeline()._generate_reply(_QuietLLM(), None, session, None)
    assert reply == GUIDED_REPLY
    # The caller heard the guided answer last: a "yes" now is no yes to the brain's read-back.
    assert load(session).pending is None
    assert brain_actions.WAIT not in session.metadata


async def test_a_brain_turn_voids_the_guided_engines_open_questions(agent):
    session = CallSession(call_sid="CA-void2", language=Language.BANGLA)
    session.metadata.update(
        offer={"name": "book_appointment", "arguments": {}},
        choices={"doctor_id": 1, "times": ["10:00", "10:30"], "turns_left": 2},
        guided={"step": "confirm"},
    )
    session.add_turn("user", "হ্যাঁ")
    await VoicePipeline()._generate_reply(_QuietLLM(), _SilentVoice(), session, _sink)
    for key in ("offer", "choices", "guided"):
        assert key not in session.metadata


async def test_the_brain_speaks_through_the_pipelines_voice(agent):
    voice = _SilentVoice()
    session = CallSession(call_sid="CA-voice", language=Language.BANGLA)
    session.add_turn("user", "হ্যালো")
    FakeBrain.lines = ["জি।", "বলুন।"]
    reply = await VoicePipeline()._generate_reply(_QuietLLM(), voice, session, _sink)
    assert reply == "জি। বলুন।"
    assert voice.spoken == [("জি।", "bn"), ("বলুন।", "bn")]


async def test_the_brain_starts_in_the_calls_language(agent, monkeypatch):
    seen = []

    class Looks(FakeBrain):
        async def turn(self, session, said, llm, speak, **kw):
            seen.append(load(session).language)
            return await super().turn(session, said, llm, speak, **kw)

    monkeypatch.setattr(brain_engine, "Brain", Looks)
    session = CallSession(call_sid="CA-en", language=Language.ENGLISH)
    session.add_turn("user", "ok")
    await VoicePipeline()._generate_reply(_QuietLLM(), _SilentVoice(), session, _sink)
    assert seen == ["en"]


class _SilentVoice:
    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []

    async def synthesize_stream(self, text: str, language: str = "en"):
        self.spoken.append((text, language))
        yield AudioFrame(b"\x00" * 320, rate=8000)


async def _sink(frame):
    return None


# --- a cancelled turn: the pipeline's history matches the brain's -------------------------------


async def test_a_turn_cut_off_before_anything_was_said_leaves_no_caller_line(agent):
    pipe = VoicePipeline()
    await pipe.handle_text("CA-cut", "হ্যালো")
    FakeBrain.lines, FakeBrain.hang = [], True
    turn = asyncio.create_task(pipe.handle_text("CA-cut", "ফি কত?"))
    await asyncio.sleep(0.01)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    session = await pipe.session_for("CA-cut")
    assert [t.content for t in session.history][-1] == "জি, বলুন।"  # "ফি কত?" is gone


async def test_a_turn_cut_off_after_a_sentence_keeps_the_line_and_what_was_said(agent):
    pipe = VoicePipeline()
    FakeBrain.lines, FakeBrain.hang = ["জি।"], True
    turn = asyncio.create_task(pipe.handle_text("CA-cut2", "ফি কত?"))
    await asyncio.sleep(0.01)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    session = await pipe.session_for("CA-cut2")
    assert [(t.role, t.content) for t in session.history][-2:] == [
        ("user", "ফি কত?"),
        ("assistant", "জি।"),
    ]


async def test_the_real_brain_and_the_pipeline_agree_on_a_cut_off_turn(monkeypatch):
    """No fake brain: the turn is cut while the brain holds its first sentence."""
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    session = CallSession(call_sid="CA-real", language=Language.BANGLA)
    session.add_turn("assistant", "স্বাগতম।")
    session.add_turn("user", "ফি কত?")
    llm = FakeLLM("ফি ৮০০ টাকা।", route=route_json(), route_delay=5)
    turn = asyncio.create_task(VoicePipeline()._generate_reply(llm, _SilentVoice(), session, _sink))
    while not llm.calls:
        await asyncio.sleep(0.001)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    # Fix round 1, ruling 9: like guided, the reply path keeps the caller's line on a cut-off
    # (the turn deadline); only a typed chat's cancelled request drops it (see below).
    assert [t.content for t in session.history] == ["স্বাগতম।", "ফি কত?"]
    assert "brain_trace" not in session.metadata
    assert load(session).turn == 0


# --- greeting and closing -----------------------------------------------------------------------


async def test_the_agent_greeting_is_generated_with_the_caller_id_name(agent, monkeypatch):
    seen = []

    async def generated(llm, config, *, clinic_name, language, now, caller_name):
        seen.append((clinic_name, language, caller_name))
        return "শুভ সকাল।"

    monkeypatch.setattr(brain_greeting, "greeting", generated)
    default_clinic_store().upsert_patient("01712345678", "করিম")
    pipe = VoicePipeline()
    out = await pipe.handle_text("CA-greet", "হ্যালো", "01712345678")
    assert out["greeting"] == "শুভ সকাল।"
    assert seen == [(default_clinic_store().clinic_name("bn"), "bn", "করিম")]
    out = await pipe.handle_text("CA-greet-2", "হ্যালো")
    assert seen[-1][2] is None  # no caller ID, no name


async def test_a_guided_call_keeps_the_fixed_greeting(agent, monkeypatch):
    monkeypatch.setattr(settings.pipeline, "engine", "guided")
    out = await VoicePipeline().handle_text("CA-fixed", "হ্যালো")
    assert out["greeting"] == settings.languages.default_greeting["bn"]


async def test_a_slow_greeting_never_holds_the_answer_past_its_timeout(agent, monkeypatch):
    monkeypatch.setattr(settings.brain, "greeting_timeout_s", 0.05)

    async def slow_llm():
        await asyncio.sleep(5)

    monkeypatch.setattr(registry, "get_llm", slow_llm)
    loop = asyncio.get_running_loop()
    began = loop.time()
    greeting = await VoicePipeline()._opening(CallSession(call_sid="CA-slow"), "fixed")
    assert greeting == "fixed" and loop.time() - began < 1


async def test_end_call_in_a_typed_chat_ends_it(agent):
    FakeBrain.lines, FakeBrain.end_state = ["ধন্যবাদ, ভালো থাকবেন।"], "completed"
    out = await VoicePipeline().handle_text("CA-bye", "আর কিছু না, ধন্যবাদ")
    assert out["state"] == "completed"
    assert out["reply"] == "ধন্যবাদ, ভালো থাকবেন।"


def _pcm(rms: float, seed: int, n: int = 1600) -> bytes:
    rng = random.Random(seed)
    samples = [rng.uniform(-1.0, 1.0) for _ in range(n // 2)]
    scale = rms / ((sum(s * s for s in samples) / len(samples)) ** 0.5 + 1e-9)
    return b"".join(struct.pack("<h", int(max(-32768.0, min(32767.0, s * scale)))) for s in samples)


class _STT:
    async def transcribe(self, buffer: bytes, language: str = "auto"):
        return STTResult(text="আর কিছু না, ধন্যবাদ", language=Language.BANGLA, confidence=0.95)


@pytest.mark.parametrize("end", ["completed", "escalated"])
async def test_a_spoken_call_the_brain_ends_is_left_like_a_guided_goodbye(agent, monkeypatch, end):
    FakeBrain.lines, FakeBrain.end_state = ["ভালো থাকবেন।"], end
    voice = _SilentVoice()
    monkeypatch.setattr(registry, "_stt", _STT())
    monkeypatch.setattr(registry, "_tts", voice)
    pipe = VoicePipeline()
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    task = asyncio.create_task(pipe.process_audio_stream("SID-END", queue, _sink))
    for _ in range(10):
        await queue.put(_pcm(200.0, 0))
    for _ in range(12):
        await queue.put(_pcm(3000.0, 1))
        await asyncio.sleep(0.01)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=5)  # the loop leaves by itself
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    session = await pipe.session_for("SID-END")
    assert session.state == end
    assert voice.spoken[0] == ("স্বাগতম।", "bn")  # the generated greeting opened the call
    assert ("ভালো থাকবেন।", "bn") in voice.spoken
    assert session.history[-1].content == "ভালো থাকবেন।"


# --- review round: the real brain under failure and cut-off ------------------------------------


def test_a_read_back_whose_voice_failed_is_not_left_waiting_for_a_yes(executor):
    executor.previews["book_appointment"] = {"preview": BOOKED | {"serial_no": None}}
    executor.results["book_appointment"] = BOOKED
    session = identified_session()
    session.add_turn("user", BOOK_LINE)
    llm = FakeLLM("unused", route=route_json("book", "calm", "booking"))

    async def broken_voice(text):
        raise RuntimeError("voice down")

    with pytest.raises(RuntimeError):
        asyncio.run(Brain().turn(session, BOOK_LINE, llm, broken_voice, today=TODAY))
    assert load(session).pending is None  # the caller never heard it: no yes can book it
    assert session.metadata["brain_trace"][-1]["error"].startswith("RuntimeError")
    say(session, "হ্যাঁ", FakeLLM("জি।", route=route_json()))
    assert executor.ran == []


def test_a_cancelled_turn_undoes_what_settling_changed(executor, monkeypatch):
    session, _, _ = read_back_booking(executor)
    line = "হ্যাঁ, তবে বিকেলে হলে ভালো"  # voids the read-back and forgets its facts, at once
    session.add_turn("user", line)
    before = copy.deepcopy(session.metadata)
    started = []

    class _SlowSearch:
        def search(self, said):
            started.append(said)
            import time

            time.sleep(0.2)
            return []

    monkeypatch.setattr(brain_engine, "retriever_for", lambda clinic: _SlowSearch())

    async def run():
        turn = asyncio.create_task(Brain().turn(session, line, FakeLLM(), Recorder(), today=TODAY))
        await _cancel_once(turn, lambda: started)

    asyncio.run(run())
    assert session.metadata == before
    assert load(session).pending is not None  # the read-back the caller heard still stands


async def test_the_real_brain_cut_off_after_a_sentence_is_kept_on_both_sides(monkeypatch):
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    session = CallSession(call_sid="CA-real2", language=Language.BANGLA)
    session.add_turn("assistant", "স্বাগতম।")
    session.add_turn("user", "হ্যালো")
    llm = FakeLLM("জি, বলুন। কীভাবে সাহায্য করতে পারি?", route=route_json())

    second = asyncio.Event()

    class _Voice:
        def __init__(self):
            self.played = []

        async def synthesize_stream(self, text, language="en"):
            if self.played:
                second.set()
                await asyncio.Event().wait()  # the caller barges in on the second sentence
            self.played.append(text)
            yield AudioFrame(b"\x00" * 320, rate=8000)

    voice = _Voice()
    turn = asyncio.create_task(VoicePipeline()._generate_reply(llm, voice, session, _sink))
    await asyncio.wait_for(second.wait(), timeout=5)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    assert [(t.role, t.content) for t in session.history][-2:] == [
        ("user", "হ্যালো"),
        ("assistant", "জি, বলুন।"),
    ]
    assert session.metadata["brain_trace"][-1]["cancelled"] is True
    assert load(session).turn == 1


async def test_the_real_brain_failing_after_a_sentence_ends_the_turn_there(monkeypatch):
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    session = CallSession(call_sid="CA-real3", language=Language.BANGLA)
    session.add_turn("assistant", "স্বাগতম।")
    session.add_turn("user", "হ্যালো")

    class _Dies(FakeLLM):
        async def _reply_stream(self, messages):
            self.calls.append(messages)
            yield "জি, বলুন। "
            yield "কী"
            raise _connection_error()

    llm = _Dies(route=route_json())
    guided = []

    async def guided_reply(self, *a):
        guided.append(1)
        return GUIDED_REPLY

    monkeypatch.setattr(VoicePipeline, "_reply", guided_reply)
    reply = await VoicePipeline()._generate_reply(llm, _SilentVoice(), session, _sink)
    assert reply == "জি, বলুন।" and guided == []
    assert "brain_fallbacks" not in session.metadata
    assert session.metadata["brain_trace"][-1]["error"].startswith("APIConnectionError")


# --- fix round 1 -------------------------------------------------------------------------------


@pytest.fixture
def locked_platform(tmp_path, monkeypatch):
    """The platform database held by another writer (rollback journal), nothing opened yet."""
    path = tmp_path / "locked" / "shefa.db"
    path.parent.mkdir()
    writer = sqlite3.connect(str(path))
    writer.execute("PRAGMA journal_mode=DELETE")
    writer.execute("CREATE TABLE t (x)")
    writer.commit()
    writer.execute("BEGIN EXCLUSIVE")
    monkeypatch.setattr(settings.storage, "db_path", str(path))
    brain_config.set_default_config_store(None)

    async def release() -> None:
        """Let the writer go and wait for the read that timed out, still in its thread."""
        writer.rollback()
        deadline = time.monotonic() + 6
        while brain_config._default_config_store is None and time.monotonic() < deadline:
            await asyncio.sleep(0.02)

    yield SimpleNamespace(path=path, release=release)
    writer.rollback()
    writer.close()


async def test_a_locked_platform_database_never_holds_the_greeting(locked_platform, monkeypatch):
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    session = CallSession(call_sid="CA-locked")
    began = time.monotonic()
    greeting = await VoicePipeline()._opening(session, "fixed")
    assert greeting == "fixed"
    assert time.monotonic() - began < settings.brain.greeting_timeout_s
    assert session.metadata["brain_config"] == {"engine": "guided"}  # frozen for the call
    await locked_platform.release()


async def test_a_locked_platform_database_never_holds_a_guided_turn(locked_platform, monkeypatch):
    async def guided_reply(self, llm, tts, session, put_playback):
        return GUIDED_REPLY

    monkeypatch.setattr(VoicePipeline, "_reply", guided_reply)
    monkeypatch.setattr(registry, "_llm", _QuietLLM())
    pipe = VoicePipeline()
    began = time.monotonic()
    first = await pipe.handle_text("CA-locked2", "ফি কত?")
    second = await pipe.handle_text("CA-locked2", "আচ্ছা")
    assert first["reply"] == second["reply"] == GUIDED_REPLY
    assert time.monotonic() - began < 1.5  # one bounded read (0.5 s) for the whole call
    await locked_platform.release()


async def test_a_failed_config_read_never_flips_the_call_later(monkeypatch):
    class Broken:
        reads = 0

        def live_values(self, scope="platform"):
            Broken.reads += 1
            raise sqlite3.DatabaseError("malformed")

    monkeypatch.setattr(settings.pipeline, "engine", "guided")
    brain_config.set_default_config_store(Broken())
    pipe = VoicePipeline()
    session = CallSession(call_sid="CA-flip")
    assert await pipe._engine_ready(session) == "guided"
    # The store recovers with a live "agent" row: the call that began guided stays guided.
    healthy = brain_config.ConfigStore(Path(settings.storage.db_path).parent / "ok.db")
    healthy.publish(healthy.draft("engine", "agent", author="t"), author="t")
    brain_config.set_default_config_store(healthy)
    assert await pipe._engine_ready(session) == "guided"
    assert Broken.reads == 1


async def test_a_guided_call_freezes_only_its_engine_an_agent_call_the_whole_snapshot(
    monkeypatch,
):
    pipe = VoicePipeline()
    monkeypatch.setattr(settings.pipeline, "engine", "guided")
    guided_call = CallSession(call_sid="CA-g")
    await pipe._engine_ready(guided_call)
    assert guided_call.metadata["brain_config"] == {"engine": "guided"}
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    brain_config._clear_cache()  # the snapshot cache would hold the guided read for 5 s
    agent_call = CallSession(call_sid="CA-a")
    await pipe._engine_ready(agent_call)
    assert agent_call.metadata["brain_config"]["engine"] == "agent"
    assert agent_call.metadata["brain_config"]["prompt.persona"]


async def test_a_greeting_that_fails_any_way_is_the_fixed_one(agent, monkeypatch):
    async def broken():
        raise RuntimeError("no model")

    monkeypatch.setattr(registry, "get_llm", broken)
    assert await VoicePipeline()._opening(CallSession(call_sid="CA-g2"), "fixed") == "fixed"


async def test_a_yes_to_the_fallbacks_read_back_books(agent, monkeypatch):
    """Ruling 4: the guided fallback ended on a read-back, so guided hears the answer."""
    from shefa.tools.executor import preview_action

    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    pipe = VoicePipeline()
    store = default_clinic_store()
    session = await pipe._session_manager.get_or_create("CA-lost")
    session.patient_id = str(store.upsert_patient("01712345678", "করিম"))
    rahman = next(d for d in store.doctors() if d["name_en"] == "Rahman")
    args = {"doctor_id": rahman["id"], "doctor_name": "Rahman", "date": "2026-11-26",
            "time": "18:00"}  # fmt: skip
    preview = await preview_action("book_appointment", args, session)
    assert "preview" in preview

    async def guided_reads_back(self, llm, tts, session, put_playback):
        session.metadata["pending"] = {
            "name": "book_appointment", "arguments": args, "preview": preview["preview"],
        }  # fmt: skip
        return "ডাক্তার রহমান, কাল সন্ধ্যা ৬টা। ঠিক আছে?"

    monkeypatch.setattr(VoicePipeline, "_reply", guided_reads_back)
    FakeBrain.lines, FakeBrain.error = [], _connection_error()
    await pipe.handle_text("CA-lost", "কাল সন্ধ্যা ৬টায় ডাক্তার রহমান")
    assert "pending" in session.metadata
    # The brain would answer the "yes" now; it must not get the turn.
    monkeypatch.setattr(VoicePipeline, "_reply", _REAL_GUIDED_REPLY)
    FakeBrain.error = None
    FakeBrain.seen = []
    out = await pipe.handle_text("CA-lost", "হ্যাঁ")
    assert FakeBrain.seen == []
    assert "book_appointment" in out["actions"]
    patient = store.upsert_patient("01712345678")
    assert [a["start_time"] for a in store.appointments_for_patient(patient)] == ["18:00"]
    assert "pending" not in session.metadata
    FakeBrain.seen = []
    await pipe.handle_text("CA-lost", "ধন্যবাদ")
    assert FakeBrain.seen  # the read-back settled: the brain answers again


class _JsonSessions(SessionManager):
    """Sessions kept as JSON, as on Redis: every `get` is a fresh copy, only `save` persists."""

    def __init__(self) -> None:
        super().__init__()
        self.saved: dict[str, str] = {}

    async def get(self, call_sid):
        import json

        raw = self.saved.get(call_sid)
        return CallSession.from_dict(json.loads(raw)) if raw else None

    async def save(self, session):
        import json

        self.saved[session.call_sid] = json.dumps(session.to_dict())


async def test_a_cancelled_typed_turn_is_saved_on_a_json_session_store(agent):
    class Books(FakeBrain):
        holding = asyncio.Event()

        async def turn(self, session, said, llm, speak, **kw):
            await speak("জি, হয়ে গেছে।")
            session.metadata["brain_trace"] = [{"cancelled": True}]
            session.metadata["brain"] = {"pending": None, "done": [{"kind": "book"}]}
            Books.holding.set()
            await asyncio.Event().wait()

    import shefa.brain.engine as eng

    original = eng.Brain
    eng.Brain = Books
    try:
        sessions = _JsonSessions()
        pipe = VoicePipeline(sessions)
        turn = asyncio.create_task(pipe.handle_text("CA-redis", "হ্যাঁ"))
        await asyncio.wait_for(Books.holding.wait(), timeout=5)
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
    finally:
        eng.Brain = original
    stored = await sessions.get("CA-redis")
    assert stored.metadata["brain"]["done"] == [{"kind": "book"}]  # the booking is remembered
    assert [(t.role, t.content) for t in stored.history][-2:] == [
        ("user", "হ্যাঁ"),
        ("assistant", "জি, হয়ে গেছে।"),
    ]


async def test_a_fallback_after_a_saved_call_back_says_so_and_saves_no_second(agent):
    class Saves(FakeBrain):
        async def turn(self, session, said, llm, speak, **kw):
            session.metadata.setdefault(brain_actions.SUCCEEDED, []).append("request_callback")
            session.metadata.setdefault("brain_trace", []).append({"error": "x"})
            raise _connection_error()

    import shefa.brain.engine as eng

    original, eng.Brain = eng.Brain, Saves
    try:
        out = await VoicePipeline().handle_text("CA-cb", "আমাকে ফোন করবেন")
    finally:
        eng.Brain = original
    assert out["reply"] == safe.callback_saved("bn")
    assert agent.guided == []  # the guided path would route the line and save it again


async def test_a_fallback_after_a_transfer_says_the_transfer(agent):
    class Transfers(FakeBrain):
        async def turn(self, session, said, llm, speak, **kw):
            session.metadata.setdefault(brain_actions.SUCCEEDED, []).append("hand_over")
            session.state = "escalated"
            session.metadata.setdefault("brain_trace", []).append({"error": "x"})
            raise _connection_error()

    import shefa.brain.engine as eng

    original, eng.Brain = eng.Brain, Transfers
    try:
        out = await VoicePipeline().handle_text("CA-tr", "আমার একটা সমস্যা আছে")
    finally:
        eng.Brain = original
    assert out["reply"] == safe.connecting("bn") and out["state"] == "escalated"
    assert agent.guided == []


async def test_a_cancel_during_the_transfer_counts_as_handed_over(monkeypatch):
    from shefa.telephony import control as control_module
    from shefa.tools.executor import execute_tool

    started = asyncio.Event()

    async def slow_transfer(call_sid, to):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(control_module.control, "transfer", slow_transfer)
    monkeypatch.setattr(settings.escalation, "on_call_numbers", ["01700000000"])
    monkeypatch.setattr(settings.escalation, "hold_audio_url", "")
    session = CallSession(call_sid="CA-xfer")
    turn = asyncio.create_task(execute_tool("transfer_to_human", {"reason": "x"}, session))
    await asyncio.wait_for(started.wait(), timeout=5)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    assert session.state == "escalated"  # the PBX may already have moved the call


async def test_the_turn_deadline_keeps_the_callers_line_on_a_spoken_call(agent, monkeypatch):
    FakeBrain.lines, FakeBrain.hang = [], True
    monkeypatch.setattr(settings.pipeline, "turn_deadline_s", 0.2)
    monkeypatch.setattr(registry, "_stt", _STT())
    monkeypatch.setattr(registry, "_tts", _SilentVoice())
    pipe = VoicePipeline()
    rescued = asyncio.Event()

    async def no_wait(delay):
        rescued.set()

    pipe._sleep = no_wait
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    task = asyncio.create_task(pipe.process_audio_stream("SID-DEADLINE", queue, _sink))
    for _ in range(10):
        await queue.put(_pcm(200.0, 0))
    for _ in range(12):
        await queue.put(_pcm(3000.0, 1))
        await asyncio.sleep(0.01)
    await asyncio.wait_for(rescued.wait(), timeout=5)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    session = await pipe.session_for("SID-DEADLINE")
    assert session.history[-1].role == "user"
    assert session.history[-1].content == "আর কিছু না, ধন্যবাদ"
