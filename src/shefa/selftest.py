"""SHEFA checks itself and tells the founder when something is wrong, before a clinic does.

`shefa selftest` (run by a timer, see deploy/autostart/install.sh --selftest) checks:

  llm       the language model answers
  database  the clinic database can be written
  disk      there is room left for recordings and the database
  booking   (full run only) a whole booking walks through SHEFA's guided booking code on a
            throwaway COPY of the clinic database: the real bookings and the owner's report
            are never touched

A failure is sent to Telegram (`alerts.telegram_chat_id`, bot token in the environment variable
named by `alerts.telegram_token_env`). Nothing on this machine can report that the machine itself
is off, so a passing run also pings `alerts.heartbeat_url` (for example a free healthchecks.io
check), which alerts when the pings stop. With neither set, results go to the log and the exit
code only.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MIN_FREE_MB = 2000
TEST_PHONE = "01700000000"  # never a real subscriber prefix in use by a patient here


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


# (url, form or None) -> http status; replaced in tests so no test sends anything
Poster = Callable[[str, dict[str, str] | None], int]


def _post(url: str, form: dict[str, str] | None) -> int:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    with urllib.request.urlopen(url, data=data, timeout=10) as r:  # noqa: S310 - configured URLs
        return r.status


def check_llm(base_url: str | None = None) -> Check:
    from shefa.config.settings import settings

    adapter = settings.models.adapters.get("llm_local")
    base = (base_url or getattr(adapter, "base_url", "") or "http://localhost:8001/v1").rstrip("/")
    try:
        urllib.request.urlopen(f"{base}/models", timeout=5)  # noqa: S310 - local address
    except OSError as e:
        return Check("llm", False, f"the language model does not answer at {base}: {e}")
    return Check("llm", True)


def check_database(store: Any) -> Check:
    try:
        store.set_setting("selftest_at", str(int(time.time())))
    except sqlite3.Error as e:
        return Check("database", False, f"the clinic database cannot be written: {e}")
    return Check("database", True)


def check_disk(path: Path, min_free_mb: int = MIN_FREE_MB) -> Check:
    free = shutil.disk_usage(path).free // 1_000_000
    if free < min_free_mb:
        return Check("disk", False, f"only {free} MB free on the data disk (want {min_free_mb})")
    return Check("disk", True, f"{free} MB free")


def check_booking(db_path: Path) -> Check:
    """A whole booking through the guided flow, on a copy of the clinic database."""
    from shefa.clinic import default_clinic_store, set_default_clinic_store
    from shefa.clinic.store import ClinicStore
    from shefa.models.base import Language
    from shefa.pipeline import guided
    from shefa.session.manager import CallSession

    if not db_path.exists():
        return Check("booking", False, f"no clinic database at {db_path}")
    previous = default_clinic_store()
    with tempfile.TemporaryDirectory() as tmp:
        copy_path = Path(tmp) / "selftest.db"
        source = sqlite3.connect(str(db_path))
        target = sqlite3.connect(str(copy_path))
        source.backup(target)  # consistent even while SHEFA writes
        source.close()
        target.close()
        copy = ClinicStore(copy_path)
        set_default_clinic_store(copy)
        try:
            return _walk_a_booking(copy, guided, CallSession, Language)
        except Exception as e:  # noqa: BLE001 - any crash in the booking code is the finding
            logger.exception("self-test booking crashed")
            return Check("booking", False, f"the booking code crashed: {type(e).__name__}: {e}")
        finally:
            set_default_clinic_store(previous)
            copy.close()


def _walk_a_booking(copy: Any, guided: Any, call_session: Any, language: Any) -> Check:
    doctor = next((d for d in copy.doctors() if copy.next_available(d["id"])), None)
    if doctor is None:
        return Check("booking", False, "no doctor has a free place in the next month")
    session = call_session(call_sid=f"selftest-{int(time.time())}", language=language.BANGLA)
    session.patient_id = str(copy.upsert_patient(TEST_PHONE, "Self Test"))
    name = doctor["name_bn"] or doctor["name_en"]
    reply = guided.start(session, f"ডাক্তার {name} এর কাছে সবচেয়ে আগে দেখাতে চাই")
    answers = {
        "pick_doctor": "প্রথমজন",
        "day": "সবচেয়ে আগে",
        "accept": "হ্যাঁ",
        "time": "প্রথমটা",
        "name": "সেলফ টেস্ট",
        "phone": TEST_PHONE,
        "phone_confirm": "হ্যাঁ",
    }
    for _ in range(8):
        if reply.propose:
            p = reply.propose
            booked = copy.book(
                int(session.patient_id), p["doctor_id"], p["date"], p["time"], source="test"
            )
            if booked["doctor_id"] != doctor["id"]:
                return Check("booking", False, "the booking went to the wrong doctor")
            return Check("booking", True, f"booked {p['date']} {p['time']} on a copy")
        if reply.handover or reply.done:
            return Check("booking", False, f"the flow gave up: {reply.text[:120]}")
        step = session.metadata.get("guided", {}).get("step", "")
        if step not in answers:
            return Check("booking", False, f"the flow stopped at an unexpected step '{step}'")
        reply = guided.advance(session, answers[step])
    return Check("booking", False, "the flow did not reach a booking in 8 turns")


def notify(text: str, poster: Poster | None = None) -> bool:
    """Send one alert to Telegram. False (and a log line) when it is not set up or fails."""
    from shefa.config.settings import settings

    cfg = settings.alerts
    token = os.environ.get(cfg.telegram_token_env, "")
    if not (token and cfg.telegram_chat_id):
        logger.warning("ALERT (Telegram not set up): %s", text)
        return False
    try:
        status = (poster or _post)(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": cfg.telegram_chat_id, "text": text[:3500]},
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Telegram alert failed (%s): %s", type(e).__name__, text)
        return False
    return 200 <= status < 300


def heartbeat(poster: Poster | None = None) -> bool:
    from shefa.config.settings import settings

    url = settings.alerts.heartbeat_url
    if not url:
        return False
    try:
        return 200 <= (poster or _post)(url, None) < 300
    except Exception:  # noqa: BLE001 - the outside monitor alerts when pings stop
        logger.warning("heartbeat ping failed")
        return False


def run(*, full: bool, poster: Poster | None = None) -> list[Check]:
    from shefa.clinic import default_clinic_store
    from shefa.config.settings import settings

    db_path = Path(settings.storage.db_path)
    checks = [
        check_llm(),
        check_database(default_clinic_store()),
        check_disk(db_path.parent if db_path.parent.exists() else Path(".")),
    ]
    if full:
        checks.append(check_booking(db_path))
    failed = [c for c in checks if not c.ok]
    if failed:
        lines = "\n".join(f"✗ {c.name}: {c.detail}" for c in failed)
        notify(f"SHEFA self-test failed on {os.uname().nodename}:\n{lines}", poster)
    else:
        heartbeat(poster)
    return checks
