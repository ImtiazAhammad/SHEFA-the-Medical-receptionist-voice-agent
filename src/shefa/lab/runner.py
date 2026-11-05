"""Run conversation-lab scenarios through the real agent and judge what happened.

Each scenario gets its own throw-away clinic database (seeded from the clinic YAML plus
the scenario's `setup`) and its own session, and every patient line goes through
`VoicePipeline.handle_text`: the same router, tools, booking engine, templates and
emergency handoff as a phone call. Optional layers make it closer to a call:

* `voice`: every agent reply is synthesised sentence by sentence, as on a call, and
  time-to-first-audio is measured.
* `voice` + `stt` (speech mode): every patient line is synthesised, squeezed through a
  simulated phone line (8 kHz mu-law), and transcribed; the agent only gets what the
  speech model heard, and the word error rate is recorded.
* `patient_llm`: persona scenarios have the model play the patient.
"""

from __future__ import annotations

import contextlib
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shefa.audio import mulaw8k_to_s16le_16k_mono, s16le_16k_mono_to_mulaw8k
from shefa.models.tts.routed import script_language

if TYPE_CHECKING:
    from shefa.lab.scenarios import Scenario

BRIEF_WORDS = 40
_LEAK = re.compile(r"[{}<>]|```|\[internal|\btool_?(call|result)?\b|\bjson\b", re.IGNORECASE)
_END = "[END]"
_LANGUAGE_NAMES = {"bn": "Bangla (Bangladeshi, spoken, informal-polite)", "en": "English"}

PATIENT_PROMPT = (
    "You are role-playing a PATIENT phoning a clinic in Bangladesh; the other side is the "
    "clinic's receptionist. Persona and goal: {persona}\n"
    "Speak only as the patient: one short, natural spoken sentence per turn, in {language}, "
    "the way a real caller talks (hesitations and everyday words are fine). Never describe "
    "actions, never write stage directions, never play the receptionist. When your goal is "
    "done or the receptionist has handed you on, reply with exactly {end}."
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class TurnRecord:
    said: str
    heard: str
    reply: str
    state: str
    language: str
    actions: list[str] = field(default_factory=list)
    greeting: str | None = None
    wer: float | None = None
    llm_ms: float = 0.0
    stt_ms: float | None = None
    first_audio_ms: float | None = None
    patient_audio: bytes | None = None
    agent_audio: bytes | None = None
    greeting_audio: bytes | None = None
    checks: list[CheckResult] = field(default_factory=list)


@dataclass
class ScenarioResult:
    scenario: Scenario
    turns: list[TurnRecord] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    appointments: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        every = [*self.checks, *(c for t in self.turns for c in t.checks)]
        return self.error is None and all(check.ok for check in every)


def _words(text: str) -> list[str]:
    # Strip punctuation and symbols by Unicode category, not with a `\w` regex: Python's
    # `\w` does not match Bangla vowel signs, so it would cut every Bangla word apart.
    text = unicodedata.normalize("NFC", text.lower())
    kept = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text)
    return kept.split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word-level edit distance / reference length (NFC, case and punctuation ignored)."""
    ref, hyp = _words(reference), _words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, 1):
        current = [i]
        for j, other in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (word != other)))
        previous = current
    return previous[-1] / len(ref)


def latin_share(text: str) -> float:
    """Latin letters / (Latin + Bangla characters), ignoring tokens with digits (IDs,
    times). Bangla vowel signs count: they are not `isalpha()`, but they are the script."""
    words = [token for token in text.split() if not any(ch.isdigit() for ch in token)]
    latin = sum(1 for token in words for c in token if c.isascii() and c.isalpha())
    bangla = sum(1 for token in words for c in token if "ঀ" <= c <= "৿")
    return latin / (latin + bangla) if latin + bangla else 0.0


def has_devanagari(text: str) -> bool:
    """Hindi-script letters in a reply. The danda (U+0964/0965) is excluded: Bangla uses
    it as its full stop, although it lives in the Devanagari block."""
    return any("ऀ" <= c <= "ॿ" and c not in "।॥" for c in text)


def turn_checks(record: TurnRecord, expected_language: str | None) -> list[CheckResult]:
    """Checks every reply must pass, whatever the scenario."""
    checks: list[CheckResult] = []
    ended = record.state != "active"
    reply = record.reply.strip()
    checks.append(CheckResult("replied", bool(reply) or ended, "" if reply else "no reply"))
    if not reply:
        return checks
    leak = _LEAK.search(reply)
    checks.append(CheckResult(
        "no internal text", leak is None, f"contains {leak.group(0)!r}" if leak else ""
    ))
    words = len(reply.split())
    checks.append(CheckResult("brief", words <= BRIEF_WORDS, f"{words} words"))
    if ended:
        return checks
    language = expected_language or script_language(record.heard)
    if language in {"bn", "en"}:
        spoken = script_language(reply)
        checks.append(CheckResult(
            "answers in the caller's language", spoken in (language, None),
            f"caller {language}, reply {spoken}",
        ))
        if language == "bn":
            share = latin_share(reply)
            checks.append(CheckResult(
                "clean Bangla script", share <= 0.2 and not has_devanagari(reply),
                f"{share:.0%} Latin letters",
            ))
    return checks


def scenario_checks(scenario: Scenario, result: ScenarioResult) -> list[CheckResult]:
    expect = scenario.expect
    turns = result.turns
    checks: list[CheckResult] = []
    actions = [action for turn in turns for action in turn.actions]
    final = turns[-1] if turns else None
    if expect.state is not None:
        state = final.state if final else "none"
        checks.append(CheckResult(f"call ends {expect.state}", state == expect.state, state))
    if expect.actions_any:
        hit = [a for a in actions if a in expect.actions_any]
        checks.append(CheckResult(
            f"does one of: {', '.join(expect.actions_any)}", bool(hit),
            ", ".join(actions) or "no action",
        ))
    for action in expect.actions_none:
        checks.append(CheckResult(f"never {action}", action not in actions,
                                  ", ".join(actions) or "no action"))
    if expect.booked is not None:
        booked = sum(1 for a in result.appointments if a.get("status") == "booked")
        checks.append(CheckResult(
            f"caller holds {expect.booked} appointment(s)", booked == expect.booked, str(booked)
        ))
    if expect.booked_dates:
        dates = sorted(a.get("date", "") for a in result.appointments
                       if a.get("status") == "booked")
        checks.append(CheckResult(
            "booked on " + ", ".join(expect.booked_dates), dates == sorted(expect.booked_dates),
            ", ".join(dates) or "nothing booked",
        ))
    if expect.never_say:
        said = [w for t in turns for w in expect.never_say if w.lower() in t.reply.lower()]
        checks.append(CheckResult(
            "never says " + " / ".join(expect.never_say), not said, ", ".join(said)
        ))
    if expect.final_reply_contains_any:
        text = final.reply if final else ""
        hit = any(word.lower() in text.lower() for word in expect.final_reply_contains_any)
        checks.append(CheckResult(
            "final reply mentions " + " / ".join(expect.final_reply_contains_any), hit, text[:80]
        ))
    return checks


def _clean_patient_line(text: str) -> str | None:
    """The simulated patient's line, or None when it ended the call."""
    if _END in text:
        return None
    line = re.sub(r"^\s*(patient|রোগী)\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    line = line.strip().strip('"').strip()
    return line or None


class Lab:
    def __init__(
        self,
        *,
        clinic_file: str | Path = "configs/clinic.example.yaml",
        work_dir: str | Path,
        voice: Any = None,
        stt: Any = None,
        patient_llm: Any = None,
        today: date | None = None,
        clock: Any = time.perf_counter,
    ) -> None:
        self.clinic_file = Path(clinic_file)
        self.work_dir = Path(work_dir)
        self.voice = voice
        self.stt = stt
        self.patient_llm = patient_llm
        self.today = today or date.today()
        self.clock = clock

    # --- audio ---------------------------------------------------------------------
    async def speak(self, text: str, language: str) -> tuple[bytes, float | None]:
        """16 kHz PCM of `text` read sentence by sentence, and ms to the first sound."""
        from shefa.pipeline.voice_pipeline import split_complete_sentences

        sentences, tail = split_complete_sentences(text)
        if tail.strip():
            sentences.append(tail.strip())
        started, first, chunks = self.clock(), None, []
        for sentence in sentences:
            async with contextlib.aclosing(self.voice.synthesize_stream(sentence, language)) as s:
                async for frame in s:
                    if first is None:
                        first = (self.clock() - started) * 1000
                    chunks.append(frame.to_s16le_16k_mono())
        return b"".join(chunks), first

    async def hear(self, text: str, language: str) -> tuple[bytes, str, float]:
        """The patient's line as a phone caller: synthesised, 8 kHz mu-law, transcribed."""
        pcm, _first = await self.speak(text, language)
        phone = mulaw8k_to_s16le_16k_mono(s16le_16k_mono_to_mulaw8k(pcm))
        started = self.clock()
        result = await self.stt.transcribe(phone)
        return phone, result.text, (self.clock() - started) * 1000

    # --- the simulated patient -------------------------------------------------------
    async def next_patient_line(self, scenario: Scenario, transcript: list[tuple[str, str]]):
        system = PATIENT_PROMPT.format(
            persona=scenario.persona,
            language=_LANGUAGE_NAMES.get(scenario.language, scenario.language),
            end=_END,
        )
        messages = [{"role": "system", "content": system}]
        for role, text in transcript:
            messages.append({"role": "user" if role == "agent" else "assistant", "content": text})
        if len(messages) == 1:
            messages.append({"role": "user", "content": "(the phone is answered)"})
        result = await self.patient_llm.generate(messages)
        return _clean_patient_line(result.text)

    # --- one scenario ----------------------------------------------------------------
    def _prepare_store(self, scenario: Scenario) -> Any:
        from shefa.clinic import ClinicStore
        from shefa.clinic.loader import import_directory_file

        path = self.work_dir / f"{scenario.id}.db"
        for leftover in self.work_dir.glob(f"{scenario.id}.db*"):
            leftover.unlink()
        store = ClinicStore(path)
        import_directory_file(store, self.clinic_file)
        for leave in scenario.setup.get("leave", []):
            doctor = store.find_doctor(leave["doctor"])
            store.add_leave(doctor["id"], leave["from"], leave.get("to", leave["from"]),
                            leave.get("reason", ""))
        for booking in scenario.setup.get("appointments", []):
            patient = store.upsert_patient(scenario.phone, booking.get("name", ""))
            doctor = store.find_doctor(booking["doctor"])
            store.book(patient, doctor["id"], booking["date"], booking["time"])
        return store

    async def run(self, scenario: Scenario) -> ScenarioResult:
        from shefa.clinic import default as clinic_default
        from shefa.clinic import set_default_clinic_store
        from shefa.pipeline.voice_pipeline import VoicePipeline
        from shefa.session.manager import SessionManager

        scenario = scenario.filled(self.today)
        result = ScenarioResult(scenario)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        previous = clinic_default._store  # noqa: SLF001 - restored as found, never opened here
        store = self._prepare_store(scenario)
        set_default_clinic_store(store)
        pipeline = VoicePipeline(SessionManager())
        call_sid = f"lab-{scenario.id}"
        transcript: list[tuple[str, str]] = []
        scripted = list(scenario.turns)
        try:
            while len(result.turns) < max(scenario.max_turns, len(scenario.turns)):
                if scripted:
                    said = scripted.pop(0)
                elif scenario.persona and self.patient_llm is not None:
                    said = await self.next_patient_line(scenario, transcript)
                    if said is None:
                        break
                else:
                    break
                await self._turn(pipeline, call_sid, scenario, said, result, transcript)
                if result.turns[-1].state != "active":
                    break
        except Exception as error:  # noqa: BLE001 - one broken scenario never stops the rest
            result.error = f"{type(error).__name__}: {error}"
        finally:
            if scenario.phone:
                patient = store.upsert_patient(scenario.phone)
                result.appointments = store.appointments_for_patient(patient)
            set_default_clinic_store(previous)
            store.close()
        result.checks = scenario_checks(scenario, result)
        return result

    async def _turn(self, pipeline, call_sid, scenario, said, result, transcript) -> None:
        record = TurnRecord(said=said, heard=said, reply="", state="active",
                            language=scenario.language)
        if self.voice is not None and self.stt is not None:
            record.patient_audio, record.heard, record.stt_ms = await self.hear(
                said, scenario.language
            )
            record.wer = word_error_rate(said, record.heard)
        elif self.voice is not None:
            record.patient_audio, _ = await self.speak(said, scenario.language)
        started = self.clock()
        turn = await pipeline.handle_text(call_sid, record.heard or said, scenario.phone)
        record.llm_ms = (self.clock() - started) * 1000
        record.reply, record.state = turn["reply"], turn["state"]
        record.language, record.actions = turn["language"], turn["actions"]
        record.greeting = turn["greeting"]
        if record.greeting:
            transcript.append(("agent", record.greeting))
        transcript.extend([("patient", said), ("agent", record.reply)])
        if self.voice is not None:
            if record.greeting:
                record.greeting_audio, _ = await self.speak(record.greeting, record.language)
            if record.reply:
                record.agent_audio, record.first_audio_ms = await self.speak(
                    record.reply, record.language
                )
        record.checks = turn_checks(record, scenario.expect.reply_language)
        result.turns.append(record)
