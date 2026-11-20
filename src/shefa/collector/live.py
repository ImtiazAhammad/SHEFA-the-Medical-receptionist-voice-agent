"""Live calls: a volunteer talks to the REAL SHEFA booking agent while we collect.

Each turn the volunteer records (push-to-talk) is uploaded as an ordinary clip (same consent,
limits and review queue), transcribed with the same Bangla Whisper the drafts use, handed to the
product's own pipeline (`VoicePipeline.handle_text`, LLM on vLLM), and the reply is spoken with
the product's voice. Every call is kept as a product test case: what was said, what SHEFA heard,
what it answered, how long each step took, and the volunteer's verdict.

Safety rails, all here so the API stays thin:
- The agent runs on a SANDBOX clinic database (`data/collector/live/agent-sandbox.db`), seeded
  from the collection's own made-up clinic. `prepare_product` points the product's storage there
  BEFORE any product store is opened, so the real `data/shefa.db` is never written. Bookings made
  in tests are wiped at start-up.
- A few calls at a time (one GPU), one call per contributor, idle calls are ended.
- Turns of one call never overlap; a retried upload gets the same answer, not a second turn.
- Nothing heard -> "আবার বলবেন?" without asking the agent; three times -> the call ends.
- The agent too slow or down -> a polite line and the call ends (the page offers scripted calls).
- The agent ending the call (booked and finished, emergency, hand-over) ends the live call.
- Very long calls end politely; the voice failing leaves the reply as text.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("shefa.collector.live")

# The product's ended states (shefa.pipeline.voice_pipeline.ENDED_STATES), copied so this module
# can be imported before the product's settings are redirected; a test keeps them equal.
ENDED_STATES = frozenset({"escalated", "escaped", "terminated", "completed"})
GREETING_FALLBACK = "শেফা ক্লিনিকে আপনাকে স্বাগতম। আমি একটি স্বয়ংক্রিয় সহকারী। আমি কীভাবে সাহায্য করতে পারি?"
ASK_AGAIN = "দুঃখিত, ঠিক শুনতে পাইনি। আরেকবার বলবেন?"
NOT_HEARD_END = "দুঃখিত, শুনতে সমস্যা হচ্ছে। আজ এখানেই রাখছি, পরে আবার চেষ্টা করবেন।"
AGENT_DOWN = "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না। একটু পরে আবার চেষ্টা করবেন।"
TOO_LONG = "অনেকক্ষণ কথা হলো, পরীক্ষার কলটা এখানেই শেষ করছি। আপনাকে অনেক ধন্যবাদ!"
VERDICTS = ("ok", "misheard", "odd", "slow", "other")

Hear = Callable[[Any], tuple[str, float]]
Agent = Callable[[str, str], Awaitable[dict[str, Any]]]
Voice = Callable[[str, str], Awaitable[bytes | None]]


class LiveError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ------------------------------------------------------------------------- the shared ear
class SharedSpeech:
    """ONE Bangla Whisper for the whole process. Live turns go first: background drafting waits
    while a volunteer is waiting for an answer. faster-whisper is not safe to call concurrently,
    so every call holds the lock."""

    def __init__(
        self, device: str | None = None, loader: Callable[[str | None], Hear] | None = None
    ):
        self.device = device
        self._loader = loader
        self._model: Hear | None = None
        self._lock = threading.Lock()
        self._waiting = 0
        self._count = threading.Lock()

    def _get(self) -> Hear:
        if self._model is None:
            if self._loader is None:
                from shefa.collector.tools import load_drafter

                self._loader = load_drafter
            self._model = self._loader(self.device)
        return self._model

    def live(self, samples: Any) -> tuple[str, float]:
        with self._count:
            self._waiting += 1
        try:
            with self._lock:
                return self._get()(samples)
        finally:
            with self._count:
                self._waiting -= 1

    def background(self, samples: Any) -> tuple[str, float]:
        while self._waiting:
            time.sleep(0.1)
        with self._lock:
            return self._get()(samples)

    def drafter_loader(self, _device: str | None = None) -> Hear:
        """For AutoDrafter: load now (so a missing model disables drafting cleanly), then share."""
        with self._lock:
            self._get()
        return self.background


# ------------------------------------------------------------------------- sandbox clinic
_LATIN = {
    "আকন্দ": "Akanda",
    "আক্তার": "Akter",
    "আজাদ": "Azad",
    "আফরোজা": "Afroza",
    "আলম": "Alam",
    "আহমেদ": "Ahmed",
    "ইয়াসমিন": "Yasmin",
    "ইসলাম": "Islam",
    "কবির": "Kabir",
    "করিম": "Karim",
    "কাদের": "Kader",
    "খাতুন": "Khatun",
    "খান": "Khan",
    "গাজী": "Gazi",
    "ঘোষ": "Ghosh",
    "চৌধুরী": "Chowdhury",
    "জামান": "Zaman",
    "জাহান": "Jahan",
    "জোয়ার্দার": "Joardar",
    "তরফদার": "Tarafdar",
    "তানজিলা": "Tanzila",
    "তালুকদার": "Talukder",
    "তাসনিম": "Tasnim",
    "দাস": "Das",
    "দেওয়ান": "Dewan",
    "নন্দী": "Nandi",
    "নাসরিন": "Nasrin",
    "নাহার": "Nahar",
    "নুসরাত": "Nusrat",
    "পাটোয়ারী": "Patwary",
    "পারভীন": "Parvin",
    "প্রামানিক": "Pramanik",
    "ফকির": "Fakir",
    "ফারহানা": "Farhana",
    "ফেরদৌসী": "Ferdousi",
    "বাকী": "Baki",
    "বাশার": "Bashar",
    "বিশ্বাস": "Biswas",
    "বেগম": "Begum",
    "ভূঁইয়া": "Bhuiyan",
    "মজুমদার": "Majumder",
    "মল্লিক": "Mallick",
    "মাহমুদ": "Mahmud",
    "মিত্র": "Mitra",
    "মিয়া": "Mia",
    "মুন্সী": "Munshi",
    "মুস্তাফা": "Mustafa",
    "মোর্শেদ": "Morshed",
    "মোল্লা": "Molla",
    "মৌসুমী": "Mousumi",
    "রশিদ": "Rashid",
    "রহমান": "Rahman",
    "রায়": "Roy",
    "রিয়াজ": "Riaz",
    "রুমানা": "Rumana",
    "লাইলা": "Laila",
    "শারমিন": "Sharmin",
    "শাহনাজ": "Shahnaz",
    "শিকদার": "Sikder",
    "শেখ": "Sheikh",
    "সরকার": "Sarkar",
    "সাবরিনা": "Sabrina",
    "সাহা": "Saha",
    "সিদ্দিকী": "Siddiqui",
    "সুলতানা": "Sultana",
    "সেলিনা": "Selina",
    "হক": "Haque",
    "হাওলাদার": "Howlader",
    "হোসেন": "Hossain",
}
_RANK_EN = {"prof": "Professor", "assoc": "Associate Professor", "asst": "Assistant Professor"}
_WEEKDAY_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def roster_directory() -> dict[str, Any]:
    """The collection's made-up clinic (23 departments, 69 doctors) in the product's clinic file
    format, so the live agent and the scripted calls describe the same clinic."""
    from shefa.clinic.department_names import BY_KEY
    from shefa.collector.scripts import ROSTER

    departments = []
    for key, dept in ROSTER.items():
        names = BY_KEY[key]
        doctors = []
        for doc in dept["doctors"]:
            doctors.append(
                {
                    "name": _LATIN.get(doc["surname"], doc["surname"]),
                    "name_bn": doc["surname"],
                    "qualification": "MBBS, FCPS",
                    "visit_fee": doc["fee"],
                    "profile": {
                        "designation": _RANK_EN[doc["rank"]],
                        "gender": "female" if doc["gender"] == "f" else "male",
                        # how a symptom finds a doctor; urgent symptoms are never listed here
                        "conditions": {"bn": list(dept["symptoms"]), "en": []},
                    },
                    "schedule": [
                        {
                            "days": [_WEEKDAY_EN[d] for d in doc["days"]],
                            "start": doc["start"],
                            "end": doc["end"],
                            "slot_minutes": 15,
                        }
                    ],
                }
            )
        departments.append(
            {
                "name": names["en"][0].title() if names["en"][0] != "ent" else "ENT",
                "name_bn": dept["name"],
                "doctors": doctors,
            }
        )
    return {"departments": departments}


def prepare_product(data_dir: Path) -> Path:
    """Point the product at a sandbox database and fill it with the made-up clinic. Must run
    before anything opens a product store (clinic, calls, staff, audit)."""
    from shefa.config.settings import settings

    db = Path(data_dir) / "live" / "agent-sandbox.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    settings.storage.db_path = str(db)
    from shefa.clinic.default import set_default_clinic_store
    from shefa.clinic.loader import import_directory
    from shefa.clinic.store import ClinicStore

    store = ClinicStore(db)
    if not store.departments():
        import_directory(store, roster_directory())
    # Test bookings fill the diary; start every run with free slots.
    store.connection.execute("DELETE FROM appointments")
    store.connection.commit()
    set_default_clinic_store(store)
    return db


# ------------------------------------------------------------------------- the product's parts
def product_agent() -> Agent:
    from shefa.pipeline.voice_pipeline import VoicePipeline
    from shefa.session.manager import SessionManager

    pipeline = VoicePipeline(SessionManager())

    async def agent(call_sid: str, text: str) -> dict[str, Any]:
        return await pipeline.handle_text(call_sid, text, "")

    return agent


def product_voice() -> Voice:
    import numpy as np

    from shefa.collector.audio import RATE, encode_m4a
    from shefa.models.registry import ModelRegistry

    registry = ModelRegistry()

    async def voice(text: str, language: str) -> bytes | None:
        tts = await registry.get_tts()
        result = await tts.synthesize(text, language if language in ("bn", "en") else "bn")
        pcm = np.frombuffer(result.audio_bytes, dtype="<i2").astype(np.float32) / 32768.0
        if result.sample_rate != RATE:
            pcm = np.interp(
                np.linspace(0, pcm.size, int(pcm.size * RATE / result.sample_rate), endpoint=False),
                np.arange(pcm.size),
                pcm,
            ).astype(np.float32)
        return await asyncio.to_thread(encode_m4a, pcm, normalise=True)

    return voice


def llm_ready_check(ttl_s: float = 10.0) -> Callable[[], bool]:
    """Is the product's language model answering? (vLLM's /v1/models), cached a few seconds."""
    import urllib.request

    from shefa.config.settings import settings

    adapter = settings.models.adapters.get("llm_local")
    base = (getattr(adapter, "base_url", "") or "http://localhost:8001/v1").rstrip("/")
    cache = {"at": 0.0, "ok": False}

    def ready() -> bool:
        if time.monotonic() - cache["at"] < ttl_s:
            return cache["ok"]
        try:
            urllib.request.urlopen(f"{base}/models", timeout=2)  # noqa: S310 - local address
            cache["ok"] = True
        except OSError:
            cache["ok"] = False
        cache["at"] = time.monotonic()
        return cache["ok"]

    return ready


# ------------------------------------------------------------------------- situations
_WHO = (
    ("আপনার মা", "parent"),
    ("আপনার বাবা", "parent"),
    ("আপনি নিজে", "self"),
    ("আপনার স্ত্রী", "spouse"),
    ("আপনার স্বামী", "spouse"),
    ("আপনার ছেলে", "child"),
    ("আপনার মেয়ে", "child"),
    ("আপনার শাশুড়ি", "inlaw"),
)
_TWISTS = (
    "মাঝখানে একবার দিন বদলাতে চান।",
    "কোন ডাক্তার সবচেয়ে ভালো, জিজ্ঞেস করুন।",
    "ফি কত আর কী কী আনতে হবে, জিজ্ঞেস করুন।",
    "প্রথমে ভুল নাম বলে পরে ঠিক করে দিন।",
    "বিভাগের নাম না বলে শুধু সমস্যাটা বলুন।",
    "পার্কিং, রিপোর্ট বা অন্য কিছু নিয়ে একটা প্রশ্ন করুন।",
    "যেভাবে আসল ফোনে কথা বলেন, ঠিক সেভাবে বলুন; কোনো নিয়ম নেই।",
    "তাড়াহুড়োয় আছেন, একটু অধৈর্য হয়ে কথা বলুন।",
)


def make_situation(rng: random.Random) -> dict[str, str]:
    from shefa.collector.scripts import ROSTER

    dept = ROSTER[rng.choice(list(ROSTER))]
    groups = set(dept["who"])
    options = [w for w, g in _WHO if g in groups or (g == "child" and "child" in groups)] or [
        "আপনি নিজে"
    ]
    if "gyn" in groups:
        options = ["আপনার স্ত্রী", "আপনার মেয়ে", "আপনি নিজে"]
    who = rng.choice(options)
    return {
        "who_bn": who,
        "problem_bn": rng.choice(dept["symptoms"]),
        "twist_bn": rng.choice(_TWISTS),
        "department_hint": dept["name"],
    }


# ------------------------------------------------------------------------- the calls
@dataclass
class LiveCall:
    id: str
    cid: str
    speaker: str
    started: float
    last: float
    turns: int = 0
    misses: int = 0
    ended: bool = False
    reason: str = ""
    errors: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    answered: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def sid(self) -> str:
        return f"live-{self.id}"


class LiveEngine:
    def __init__(
        self,
        store: Any,
        config: Any,
        hear: Hear,
        agent: Agent,
        voice: Voice | None,
        ready: Callable[[], bool],
        clock: Callable[[], float] = time.monotonic,
        greeting: str = "",
    ):
        self.store, self.cfg, self.hear, self.agent, self.voice = store, config, hear, agent, voice
        self.ready, self.clock = ready, clock
        self.greeting = greeting or GREETING_FALLBACK
        self.calls: dict[str, LiveCall] = {}
        self.rng = random.Random()
        self.warmed = False

    # -- state ------------------------------------------------------------------------------
    def active(self) -> list[LiveCall]:
        return [c for c in self.calls.values() if not c.ended]

    def reap(self) -> None:
        """End calls nobody touched for a while (closed tab, lost signal), freeing the slot."""
        now = self.clock()
        for call in self.active():
            if now - call.last > self.cfg.live_idle_s and not call.lock.locked():
                self._end(call, "abandoned")
        for cid in [k for k, c in self.calls.items() if c.ended and now - c.last > 3600]:
            del self.calls[cid]

    def status(self) -> dict[str, Any]:
        self.reap()
        ready = bool(self.cfg.live_enabled) and self.ready()
        return {
            "enabled": bool(self.cfg.live_enabled),
            "ready": ready,
            "busy": len(self.active()) >= self.cfg.live_max_calls,
        }

    def owns(self, call_id: str, cid: str) -> LiveCall | None:
        call = self.calls.get(call_id)
        return call if call and call.cid == cid and not call.ended else None

    def _get(self, call_id: str, cid: str) -> LiveCall:
        call = self.calls.get(call_id)
        if not call or call.cid != cid:
            raise LiveError("no_call", "এই কলটা আর নেই। নতুন করে শুরু করুন।", 404)
        return call

    def _end(self, call: LiveCall, reason: str) -> None:
        if call.ended:
            return
        call.ended, call.reason = True, reason
        self.store.live_end(call.id, reason, call.turns, call.errors)

    # -- start ------------------------------------------------------------------------------
    async def start(self, cid: str, speaker: str) -> dict[str, Any]:
        if not self.cfg.live_enabled:
            raise LiveError("live_off", "এই সুবিধা এখন বন্ধ আছে।", 404)
        self.reap()
        if not self.ready():
            raise LiveError("agent_off", "SHEFA এখন চালু নেই। একটু পরে চেষ্টা করুন।", 503)
        for old in self.active():  # one live call per phone: a new start replaces the old one
            if old.cid == cid:
                self._end(old, "restarted")
        if len(self.active()) >= self.cfg.live_max_calls:
            raise LiveError("busy", "এখন অন্যরা SHEFA-র সাথে কথা বলছেন। একটু পরে চেষ্টা করুন।", 429)
        now = self.clock()
        call = LiveCall(id=uuid.uuid4().hex, cid=cid, speaker=speaker, started=now, last=now)
        self.calls[call.id] = call
        situation = make_situation(self.rng)
        self.store.live_start(call.id, cid, speaker, situation)
        return {
            "call_id": call.id,
            "greeting": self.greeting,
            "audio": await self._speak(self.greeting, "bn"),
            "situation": situation,
            "max_turns": self.cfg.live_max_turns,
            "max_seconds": self.cfg.live_max_seconds,
        }

    # -- one turn ---------------------------------------------------------------------------
    async def turn(self, call_id: str, cid: str, clip_id: str) -> dict[str, Any]:
        call = self._get(call_id, cid)
        if clip_id in call.answered:  # a retried request: same answer, not a second turn
            return call.answered[clip_id]
        if call.ended:
            raise LiveError("ended", "এই কলটা শেষ হয়ে গেছে।", 410)
        if call.lock.locked():
            raise LiveError("turn_busy", "আগের কথার উত্তর আসছে, একটু অপেক্ষা করুন।", 409)
        async with call.lock:
            row = self.store.get_clip(clip_id)
            facts = json.loads((row or {}).get("facts") or "{}")
            if not row or row["contributor_id"] != cid or facts.get("live_call") != call_id:
                raise LiveError("bad_clip", "রেকর্ডিংটা এই কলের নয়।", 400)
            call.last = self.clock()
            call.turns += 1
            if (
                call.turns > self.cfg.live_max_turns
                or call.last - call.started > self.cfg.live_max_seconds
            ):
                return await self._answer(call, clip_id, "", TOO_LONG, "bn", end="too_long")
            timing: dict[str, int] = {}
            heard, confidence = await self._listen(call, clip_id, row["path"], timing)
            unsure = confidence < self.cfg.live_min_confidence
            if len(heard.replace(" ", "")) < 2 or unsure:
                call.misses += 1
                if call.misses >= self.cfg.live_max_misses:
                    return await self._answer(
                        call,
                        clip_id,
                        heard,
                        NOT_HEARD_END,
                        "bn",
                        end="not_heard",
                        timing=timing,
                        extra={"confidence": confidence, "unsure": unsure},
                    )
                return await self._answer(
                    call,
                    clip_id,
                    heard,
                    ASK_AGAIN,
                    "bn",
                    timing=timing,
                    extra={"confidence": confidence, "unsure": unsure},
                )
            call.misses = 0
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    self.agent(call.sid, heard), self.cfg.live_agent_timeout_s
                )
            except Exception as error:  # noqa: BLE001 - timeout, LLM down, any model fault
                log.warning("live agent failed: %s", type(error).__name__)
                call.errors += 1
                timing["agent_ms"] = int((time.monotonic() - t0) * 1000)
                return await self._answer(
                    call,
                    clip_id,
                    heard,
                    AGENT_DOWN,
                    "bn",
                    end="agent_error",
                    timing=timing,
                    error=type(error).__name__,
                )
            timing["agent_ms"] = int((time.monotonic() - t0) * 1000)
            reply = (result.get("reply") or "").strip()
            state = result.get("state") or "active"
            language = result.get("language") or "bn"
            ended = state in ENDED_STATES
            if not reply:
                reply = "ধন্যবাদ, কলটি শেষ হলো।" if ended else AGENT_DOWN
                if not ended:
                    call.errors += 1
            return await self._answer(
                call,
                clip_id,
                heard,
                reply,
                language,
                end=state if ended else "",
                timing=timing,
                extra={
                    "state": state,
                    "actions": result.get("actions") or [],
                    "confidence": confidence,
                },
            )

    async def _listen(
        self, call: LiveCall, clip_id: str, path: str, timing: dict[str, int]
    ) -> tuple[str, float]:
        from shefa.collector.tools import _decode, polish_draft

        t0 = time.monotonic()
        try:
            samples = await asyncio.to_thread(_decode, path)
            raw, confidence = await asyncio.wait_for(
                asyncio.to_thread(self.hear, samples), self.cfg.live_stt_timeout_s
            )
        except Exception as error:  # noqa: BLE001 - unreadable file, model fault, timeout
            log.warning("live speech recognition failed: %s", type(error).__name__)
            call.errors += 1
            raw, confidence = "", 0.0
        timing["stt_ms"] = int((time.monotonic() - t0) * 1000)
        heard, confidence = polish_draft(raw, confidence)
        # The reviewer gets this as the draft (the background drafter then skips the clip).
        self.store.set_draft(clip_id, heard, confidence if heard else 0.0)
        return heard, confidence

    async def _speak(self, text: str, language: str) -> str | None:
        """The reply as base64 m4a, or None (the page then shows the words only)."""
        import base64

        if not self.voice or not text:
            return None
        try:
            data = await asyncio.wait_for(self.voice(text, language), self.cfg.live_voice_timeout_s)
        except Exception as error:  # noqa: BLE001 - the words are still on screen
            log.warning("live voice failed: %s", type(error).__name__)
            return None
        return base64.b64encode(data).decode("ascii") if data else None

    async def _answer(
        self,
        call: LiveCall,
        clip_id: str,
        heard: str,
        reply: str,
        language: str,
        *,
        end: str = "",
        timing: dict[str, int] | None = None,
        error: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timing = dict(timing or {})
        t0 = time.monotonic()
        audio = await self._speak(reply, language)
        timing["voice_ms"] = int((time.monotonic() - t0) * 1000)
        if end:
            self._end(call, end)
        facts = {
            "live_call": call.id,
            "live_turn": call.turns,
            "heard": heard,
            "reply": reply,
            "reply_language": language,
            **(extra or {}),
            **timing,
            **({"error": error} if error else {}),
            **({"ended": end} if end else {}),
        }
        self.store.merge_clip_facts(clip_id, facts)
        self.store.live_progress(call.id, call.turns, call.errors)
        out = {
            "turn": call.turns,
            "heard": heard,
            "reply": reply,
            "language": language,
            "audio": audio,
            "ended": call.ended,
            "end_reason": call.reason,
        }
        call.answered[clip_id] = out
        return out

    # -- end and feedback -------------------------------------------------------------------
    def end(self, call_id: str, cid: str, reason: str = "caller_hung_up") -> None:
        self._end(self._get(call_id, cid), reason)

    def feedback(self, call_id: str, cid: str, verdict: str, note: str) -> None:
        call = self._get(call_id, cid)
        if verdict not in VERDICTS:
            raise LiveError("bad_verdict", "verdict", 400)
        self._end(call, call.reason or "caller_hung_up")
        self.store.live_feedback(call.id, verdict, note.strip()[:300])

    async def warm(self) -> None:
        """One throwaway turn so the first volunteer does not wait for the model to load."""
        try:
            await asyncio.wait_for(self.agent("live-warmup", "আসসালামু আলাইকুম"), 120)
        except Exception as error:  # noqa: BLE001 - only a warm-up
            log.info("live warm-up skipped: %s", type(error).__name__)
