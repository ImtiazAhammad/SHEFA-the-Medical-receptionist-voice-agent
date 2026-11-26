"""The brain's call greeting (one generated welcome, then the fixed disclosure) and its closing."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from shefa.brain.greeting import closing, greeting
from shefa.brain.state import CallState
from shefa.clinic.store import CLINIC_TZ
from shefa.config.settings import settings

NOW = datetime(2026, 11, 26, 8, 30, tzinfo=CLINIC_TZ)
CONFIG = {"prompt.greeting": "GREETING PROMPT TEXT"}


class StreamLLM:
    """Streams one scripted reply three characters at a time and counts the streams closed."""

    def __init__(self, reply: str = "", *, delay: float = 0, fail: bool = False) -> None:
        self.reply = reply
        self.delay = delay
        self.fail = fail
        self.calls: list[tuple[list[dict[str, str]], dict]] = []
        self.closed = 0
        self.sent = ""

    async def generate_stream(self, messages, tools=None, **kwargs):
        self.calls.append((messages, kwargs))
        try:
            if self.fail:
                raise RuntimeError("model is down")
            if self.delay:
                await asyncio.sleep(self.delay)
            for i in range(0, len(self.reply), 3):
                piece = self.reply[i : i + 3]
                self.sent += piece
                yield piece
                await asyncio.sleep(0)
        finally:
            self.closed += 1


def ask(llm, *, language="en", caller_name=None, config=CONFIG, now=NOW) -> str:
    return asyncio.run(
        greeting(
            llm, config, clinic_name="SHEFA Clinic", language=language, now=now,
            caller_name=caller_name,
        )
    )  # fmt: skip


def fixed(language: str) -> str:
    return settings.languages.default_greeting[language]


def test_the_disclosure_default_is_the_default_greeting_without_its_welcome_sentence() -> None:
    en = settings.brain.disclosure["en"]
    assert fixed("en").endswith(en) and en.startswith("I am an automated assistant")
    assert fixed("en").startswith("Thank you for calling SHEFA Clinic. ")
    bn = settings.brain.disclosure["bn"]
    assert fixed("bn").endswith(bn) and bn.startswith("আমি একটি স্বয়ংক্রিয় সহকারী")
    assert fixed("bn").startswith("শেফা ক্লিনিকে আপনাকে স্বাগতম। ")


def test_the_greeting_is_the_generated_welcome_then_the_fixed_disclosure() -> None:
    llm = StreamLLM("Good morning, welcome to SHEFA Clinic.")
    text = ask(llm)
    assert text == f"Good morning, welcome to SHEFA Clinic. {settings.brain.disclosure['en']}"
    assert "SHEFA Clinic" in text
    assert llm.closed == 1


def test_the_model_gets_the_prompt_and_the_facts_it_may_use() -> None:
    llm = StreamLLM("Good morning, welcome to SHEFA Clinic.")
    ask(llm, caller_name="Karim")
    messages, _ = llm.calls[0]
    assert messages[0] == {"role": "system", "content": "GREETING PROMPT TEXT"}
    user = messages[-1]["content"]
    assert "SHEFA Clinic" in user and "morning" in user and "English" in user
    assert "Karim" in user


def test_without_a_caller_name_none_is_given() -> None:
    llm = StreamLLM("Welcome to SHEFA Clinic.")
    ask(llm)
    assert "name" not in llm.calls[0][0][-1]["content"].lower()


@pytest.mark.parametrize(
    ("hour", "word"), [(8, "morning"), (13, "afternoon"), (18, "evening"), (22, "night")]
)
def test_the_part_of_the_day_follows_the_clinic_clock(hour: int, word: str) -> None:
    llm = StreamLLM("Welcome to SHEFA Clinic.")
    ask(llm, now=datetime(2026, 11, 26, hour, 0, tzinfo=CLINIC_TZ))
    assert word in llm.calls[0][0][-1]["content"]


def test_a_bangla_call_gets_a_bangla_welcome_and_disclosure() -> None:
    llm = StreamLLM("শুভ সকাল, শেফা ক্লিনিকে আপনাকে স্বাগতম।")
    text = ask(llm, language="bn")
    assert text == f"শুভ সকাল, শেফা ক্লিনিকে আপনাকে স্বাগতম। {settings.brain.disclosure['bn']}"
    assert "Bangla" in llm.calls[0][0][-1]["content"]


def test_only_the_first_sentence_of_the_reply_is_kept_and_the_stream_is_closed() -> None:
    llm = StreamLLM("Welcome to SHEFA Clinic. We are glad you called. Ask me anything.")
    text = ask(llm)
    assert text == f"Welcome to SHEFA Clinic. {settings.brain.disclosure['en']}"
    assert llm.closed == 1
    assert len(llm.sent) < len(llm.reply)  # it stopped reading once the sentence was whole


def test_a_reply_that_never_ends_a_sentence_is_taken_whole() -> None:
    assert ask(StreamLLM("Welcome to SHEFA Clinic")).startswith("Welcome to SHEFA Clinic. ")


def test_a_slow_model_falls_back_to_the_fixed_greeting_and_closes_the_stream(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "greeting_timeout_s", 0.05)
    llm = StreamLLM("Welcome to SHEFA Clinic.", delay=2)
    assert ask(llm) == fixed("en")
    assert llm.closed == 1


def test_a_model_error_falls_back_to_the_fixed_greeting() -> None:
    assert ask(StreamLLM(fail=True), language="bn") == fixed("bn")


@pytest.mark.parametrize(
    "reply",
    [
        "Welcome to SHEFA Clinic, open from 9 to 5.",
        "Welcome to SHEFA Clinic, we open at nine.",
        "শেফা ক্লিনিকে স্বাগতম, আমরা সকাল নয়টায় খুলি।",
        "Welcome to SHEFA Clinic, Dr. Rahman is in today.",
        "Welcome to SHEFA Clinic, the doctor Karim is here.",
        "শেফা ক্লিনিকে স্বাগতম, ডাক্তার রহমান আছেন।",
        "Welcome to SHEFA Clinic, please take paracetamol for your fever.",
        "",
        "   ",
    ],
)
def test_a_reply_that_fails_the_check_falls_back_to_the_fixed_greeting(reply: str) -> None:
    language = "bn" if "ক্লিনিক" in reply else "en"
    assert ask(StreamLLM(reply), language=language) == fixed(language)


def test_a_reply_in_the_wrong_language_falls_back() -> None:
    assert ask(StreamLLM("শেফা ক্লিনিকে আপনাকে স্বাগতম।"), language="en") == fixed("en")
    assert ask(StreamLLM("Welcome to SHEFA Clinic."), language="bn") == fixed("bn")
    assert ask(StreamLLM("शेफा क्लिनिक में स्वागत है।"), language="bn") == fixed("bn")


def test_the_caller_name_is_allowed_in_the_welcome() -> None:
    llm = StreamLLM("Good morning Karim, welcome to SHEFA Clinic.")
    assert ask(llm, caller_name="Karim").startswith("Good morning Karim,")


def test_with_no_disclosure_configured_the_greeting_is_the_fixed_one(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "disclosure", {})
    assert ask(StreamLLM("Welcome to SHEFA Clinic.")) == fixed("en")


def test_the_greeting_prompt_missing_from_the_config_falls_back() -> None:
    assert ask(StreamLLM("Welcome to SHEFA Clinic."), config={}) == fixed("en")


# --- the closing -------------------------------------------------------------------------------


def state_with(*done: dict) -> CallState:
    return CallState(done=list(done))


BOOKED = {"kind": "book", "doctor": "Dr. Rahman", "date": "2026-11-27", "time": "16:00"}
MOVED = {
    "kind": "reschedule_booking",
    "doctor": "Dr. Sultana",
    "date": "2026-11-29",
    "time": "10:30",
}


def test_the_closing_sums_up_a_booking_in_english() -> None:
    assert closing(state_with(BOOKED), "en") == (
        "Your appointment is with Dr. Rahman on Friday 27 November at 4 pm. Take care."
    )


def test_the_closing_sums_up_a_booking_in_bangla() -> None:
    text = closing(state_with(BOOKED), "bn")
    assert text.startswith("আপনার সিরিয়াল ডাক্তার Rahman-এর কাছে ")
    assert "সাতাশ নভেম্বর বিকেল চারটায়।" in text
    assert text.endswith("ভালো থাকবেন।")


def test_a_bangla_doctor_name_takes_the_possessive_ending() -> None:
    entry = {**BOOKED, "doctor": "রহমান"}
    assert closing(state_with(entry), "bn").startswith("আপনার সিরিয়াল ডাক্তার রহমানের কাছে ")


def test_an_entry_missing_its_facts_is_not_summed_up() -> None:
    half = {"kind": "book", "doctor": "Dr. Rahman", "date": "", "time": ""}
    assert closing(state_with(half), "en") == "Thank you for calling. Take care."


def test_the_closing_sums_up_a_move() -> None:
    assert closing(state_with(MOVED), "en") == (
        "Your appointment is with Dr. Sultana on Sunday 29 November at 10:30 am. Take care."
    )


def test_the_closing_uses_the_last_booking_or_move() -> None:
    cancelled = {"kind": "cancel_booking", "doctor": "Dr. X", "date": "2026-11-30", "time": "09:00"}
    text = closing(state_with(BOOKED, MOVED, cancelled), "en")
    assert "Dr. Sultana" in text and "Dr. X" not in text and "Rahman" not in text


@pytest.mark.parametrize("language", ["en", "bn"])
def test_the_closing_with_nothing_done_just_thanks_the_caller(language: str) -> None:
    expected = {
        "en": "Thank you for calling. Take care.",
        "bn": "ফোন করার জন্য ধন্যবাদ, ভালো থাকবেন।",
    }[language]
    assert closing(state_with(), language) == expected
    callback = {"kind": "request_callback", "doctor": "", "date": "", "time": ""}
    assert closing(state_with(callback), language) == expected
