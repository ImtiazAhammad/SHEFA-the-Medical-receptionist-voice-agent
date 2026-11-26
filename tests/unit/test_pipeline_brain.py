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
import struct
from types import SimpleNamespace

import httpx
import openai
import pytest

from shefa.audio import AudioFrame
from shefa.brain import actions as brain_actions
from shefa.brain import engine as brain_engine
from shefa.brain import greeting as brain_greeting
from shefa.brain.engine import Brain
from shefa.brain.state import CallState, load, save
from shefa.clinic import default_clinic_store
from shefa.config.settings import settings
from shefa.models.base import Language, LLMResult, StreamEvent, STTResult
from shefa.models.registry import registry
from shefa.pipeline.error_taxonomy import MalformedLLMOutputError
from shefa.pipeline.voice_pipeline import VoicePipeline
from shefa.session.manager import CallSession
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


def test_the_engine_is_read_once_per_call(monkeypatch):
    monkeypatch.setattr(settings.pipeline, "engine", "agent")
    session = CallSession(call_sid="CA-frozen")
    assert VoicePipeline._engine(session) == "agent"
    monkeypatch.setattr(settings.pipeline, "engine", "guided")
    assert VoicePipeline._engine(session) == "agent"  # frozen in metadata["brain_config"]


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


async def test_any_other_brain_error_is_a_failed_turn_as_before(agent):
    FakeBrain.lines, FakeBrain.error = [], ValueError("a bug")
    pipe = VoicePipeline()
    with pytest.raises(ValueError):
        await pipe.handle_text("CA-bug", "ফি কত?")
    assert agent.guided == []
    session = await pipe.session_for("CA-bug")
    assert [t.role for t in session.history] == ["assistant"]  # resendable, as for guided


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
        pending={"name": "book_appointment", "arguments": {}, "preview": {}},
        offer={"name": "book_appointment", "arguments": {}},
        choices={"doctor_id": 1, "times": ["10:00", "10:30"], "turns_left": 2},
        guided={"step": "confirm"},
    )
    session.add_turn("user", "হ্যাঁ")
    await VoicePipeline()._generate_reply(_QuietLLM(), _SilentVoice(), session, _sink)
    for key in ("pending", "offer", "choices", "guided"):
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
    assert [t.content for t in session.history] == ["স্বাগতম।"]
    assert (
        "brain_trace" not in session.metadata
        and "brain" not in session.metadata
        or (load(session).turn == 0)
    )


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
