"""The call's first and last words.

The greeting is one welcome sentence the model writes (it can fit the hour and use the caller's
name), then the disclosure, which is fixed text from the settings: what is said about being an
assistant and about the call being written down is never left to a model. The welcome states no
fact, so it is held to a stricter rule than a reply: no number, no doctor, the call's language.
Anything wrong or slow, and the whole greeting is the fixed `languages.default_greeting`.

The closing is built by code from what the call finished, so it can only say what is true.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from shefa.brain.check import _BN_DOCTOR, _EN_DOCTOR, Grounds, check_sentence, numbers_in
from shefa.clinic.store import CLINIC_TZ
from shefa.config.settings import settings
from shefa.pipeline.replycheck import tidy
from shefa.spoken import of, spoken_date, spoken_doctor, spoken_time

if TYPE_CHECKING:
    from datetime import datetime

    from shefa.brain.state import CallState

logger = logging.getLogger(__name__)

MAX_TOKENS = 60  # one sentence; a longer reply is cut off after its first
_CLOSING_KINDS = ("book", "reschedule_booking")  # the tools that leave an appointment to sum up
_NOT_SPOKEN = "{}`"  # a tool line or code fence is never words for the caller
_ENDINGS = ".!?।"


def _part_of_day(now: datetime) -> str:
    hour = (now.astimezone(CLINIC_TZ) if now.tzinfo else now).hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 16:
        return "afternoon"
    if 16 <= hour < 20:
        return "evening"
    return "night"


def _fixed(language: str) -> str:
    greetings = settings.languages.default_greeting
    return greetings.get(language) or greetings.get("en") or ""


def _facts(clinic_name: str, language: str, now: datetime, caller_name: str | None) -> str:
    lines = [
        f"Clinic: {clinic_name}",
        f"Language: {'Bangla' if language == 'bn' else 'English'}",
        f"Time of day: {_part_of_day(now)}",
    ]
    if caller_name:
        lines.append(f"Caller: {caller_name}")
    return "\n".join(lines)


async def _first_sentence(llm: Any, messages: list[dict[str, str]]) -> str:
    """The model's first sentence; the stream is closed as soon as it is whole."""
    from shefa.pipeline.voice_pipeline import split_complete_sentences

    text = ""
    stream = llm.generate_stream(messages, temperature=0.3, max_tokens=MAX_TOKENS)
    try:
        async for chunk in stream:
            text += chunk
            found, _ = split_complete_sentences(text)
            if found:
                return found[0]
        return text.strip()
    finally:
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()


def _welcome_fault(welcome: str, clinic_name: str, language: str) -> str:
    """Why the welcome may not be said, or "" when it may. The clinic's own name is allowed."""
    if not welcome:
        return "empty"
    if any(c in welcome for c in _NOT_SPOKEN):
        return "not words"
    if numbers_in(welcome) - numbers_in(clinic_name):
        return "a number"
    if _BN_DOCTOR.search(welcome) or _EN_DOCTOR.search(welcome):
        return "a doctor"
    verdict = check_sentence(
        welcome, Grounds(texts=[clinic_name]), goal="unknown", language=language
    )
    return "" if verdict.ok else f"{verdict.kind}: {verdict.reason}"


async def greeting(
    llm: Any,
    config: dict[str, Any],
    *,
    clinic_name: str,
    language: str,
    now: datetime,
    caller_name: str | None,
) -> str:
    """The generated welcome and the fixed disclosure; the fixed greeting if either is missing,
    or the model is slow, fails, or writes anything the welcome rules refuse."""
    disclosure = settings.brain.disclosure.get(language, "")
    prompt = config.get("prompt.greeting") or ""
    if not disclosure or not prompt:
        return _fixed(language)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": _facts(clinic_name, language, now, caller_name)},
    ]
    try:
        raw = await asyncio.wait_for(
            _first_sentence(llm, messages), timeout=settings.brain.greeting_timeout_s
        )
    except TimeoutError:
        logger.warning("greeting: the model was too slow, the fixed greeting is used")
        return _fixed(language)
    except Exception as exc:  # noqa: BLE001 - the caller must hear a greeting whatever happens
        logger.warning("greeting: the model failed (%s), the fixed greeting is used", exc)
        return _fixed(language)
    welcome = tidy(raw)
    if fault := _welcome_fault(welcome, clinic_name, language):
        logger.warning("greeting: the welcome was refused (%s), the fixed greeting is used", fault)
        return _fixed(language)
    if welcome[-1] not in _ENDINGS:
        welcome += "।" if language == "bn" else "."
    return f"{welcome} {disclosure}"


_THANKS = {
    "bn": "ফোন করার জন্য ধন্যবাদ, ভালো থাকবেন।",
    "en": "Thank you for calling. Take care.",
}


def closing(state: CallState, language: str) -> str:
    """One sentence summing up the last booking or move of the call, then a goodbye; a plain
    thank-you when the call left no appointment."""
    last = next(
        (
            e
            for e in reversed(state.done)
            if e.get("kind") in _CLOSING_KINDS
            and e.get("doctor")
            and e.get("date")
            and e.get("time")
        ),
        None,
    )
    if last is None:
        return _THANKS.get(language) or _THANKS["en"]
    doctor = spoken_doctor(str(last["doctor"]), language)
    day = spoken_date(str(last["date"]), language)
    if language == "bn":
        when = spoken_time(str(last["time"]), "bn", at=True)
        return f"আপনার সিরিয়াল {of(doctor)} কাছে {day} {when}। ভালো থাকবেন।"
    return (
        f"Your appointment is with {doctor} on {day} at {spoken_time(str(last['time']), 'en')}."
        " Take care."
    )
