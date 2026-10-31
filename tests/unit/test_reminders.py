from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from shefa.clinic import ClinicStore
from shefa.clinic.loader import import_directory
from shefa.clinic.store import CLINIC_TZ
from shefa.reminders import in_quiet_hours, reminder_text, run_reminder_cycle
from shefa.telephony.call_context import OutboundContext, pop_context

DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "name_bn": "হৃদরোগ",
            "doctors": [
                {
                    "name": "Rahman",
                    "name_bn": "রহমান",
                    "schedule": [
                        {"days": [d], "start": "09:00", "end": "11:00", "slot_minutes": 30}
                        for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
                    ],
                }
            ],
        }
    ]
}

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=CLINIC_TZ)  # a Monday, mid-morning
TOMORROW = "2026-11-03"


@pytest.fixture
def store(tmp_path):
    clinic = ClinicStore(tmp_path / "c.db")
    import_directory(clinic, DIRECTORY)
    yield clinic
    clinic.close()


def book(store, phone="01711000000", day=TOMORROW, start="09:00"):
    patient = store.upsert_patient(phone, "Karim")
    return store.book(patient, 1, day, start, now=NOW)


def test_appointment_within_the_lead_window_is_due(store):
    appointment = book(store)
    due = store.due_reminders(NOW)
    assert [d["appointment_id"] for d in due] == [appointment["appointment_id"]]
    assert due[0]["phone"] == "01711000000" and due[0]["doctor_en"] == "Rahman"


def test_cancelled_and_far_off_appointments_are_not_due(store):
    cancelled = book(store, "01711000001", start="09:00")
    store.cancel(cancelled["appointment_id"], cancelled["patient_id"])
    book(store, "01711000002", day="2026-11-09")  # a week away
    assert store.due_reminders(NOW) == []


def test_an_appointment_that_has_already_started_is_not_due(store):
    book(store, day="2026-11-02", start="10:30")
    assert len(store.due_reminders(NOW)) == 1
    assert store.due_reminders(NOW + timedelta(hours=1)) == []


def test_attempt_cap_and_retry_gap(store):
    appointment = book(store)
    aid = appointment["appointment_id"]
    store.record_reminder_attempt(aid, "reminder", "failed", NOW)
    assert store.due_reminders(NOW + timedelta(minutes=30)) == []  # too soon to retry
    assert len(store.due_reminders(NOW + timedelta(minutes=100))) == 1
    store.record_reminder_attempt(aid, "reminder", "failed", NOW + timedelta(minutes=100))
    assert store.due_reminders(NOW + timedelta(hours=5)) == []  # max attempts reached


def test_an_answered_reminder_is_never_repeated(store):
    appointment = book(store)
    store.mark_reminder_done(appointment["appointment_id"], "reminder")
    assert store.due_reminders(NOW) == []
    store.record_reminder_attempt(appointment["appointment_id"], "reminder", "x", NOW)
    assert store.due_reminders(NOW + timedelta(days=0, hours=3)) == []


def test_followup_targets_visits_completed_a_day_or_two_ago(store):
    appointment = book(store, day="2026-11-03", start="09:00")
    store.mark_status(appointment["appointment_id"], "completed")
    later = datetime(2026, 11, 4, 12, 0, tzinfo=CLINIC_TZ)
    assert len(store.due_reminders(later, kind="followup")) == 1
    assert store.due_reminders(NOW, kind="followup") == []  # visit not over yet
    assert store.due_reminders(later + timedelta(days=5), kind="followup") == []  # too old
    assert store.due_reminders(later, kind="reminder") == []


def test_mark_status_rejects_nonsense(store):
    from shefa.clinic import ClinicError

    appointment = book(store)
    with pytest.raises(ClinicError):
        store.mark_status(appointment["appointment_id"], "banana")


def test_reminder_text_speaks_the_facts_in_both_languages(store):
    due = book(store) and store.due_reminders(NOW)[0]
    en = reminder_text(due, "en")
    bn = reminder_text(due, "bn")
    for text in (en, bn):
        assert TOMORROW in text and "09:00" in text and due["appointment_id"] in text
    assert "Rahman" in en and "রহমান" in bn
    assert "feeling" in reminder_text(due, "en", "followup")
    assert "কেমন" in reminder_text(due, "bn", "followup")


@pytest.mark.parametrize(
    ("hour", "quiet"), [(7, True), (8, False), (12, False), (19, False), (20, True), (23, True)]
)
def test_quiet_hours_cross_midnight(hour, quiet):
    assert in_quiet_hours(datetime(2026, 11, 2, hour, 0, tzinfo=CLINIC_TZ)) is quiet


def test_quiet_hours_same_day_window():
    noon = datetime(2026, 11, 2, 12, 30, tzinfo=CLINIC_TZ)
    assert in_quiet_hours(noon, "12:00", "13:00") is True
    assert in_quiet_hours(noon, "13:00", "14:00") is False


async def test_cycle_places_calls_records_attempts_and_hands_over_context(store):
    appointment = book(store)
    placed_calls = []

    async def place(number, call_uuid, variables):
        placed_calls.append((number, call_uuid, variables))
        return {"call_sid": call_uuid, "status": "dialing"}

    result = await run_reminder_cycle(store, place, NOW)
    assert [r["appointment_id"] for r in result] == [appointment["appointment_id"]]
    number, call_uuid, variables = placed_calls[0]
    assert number == "01711000000" and variables == {"SHEFA_KIND": "reminder"}

    context = pop_context(call_uuid)
    assert isinstance(context, OutboundContext)
    assert appointment["appointment_id"] in context.greeting
    assert context.patient_id == str(appointment["patient_id"])
    context.on_answered()  # the pipeline reports the pick-up
    assert store.due_reminders(NOW + timedelta(hours=3)) == []


async def test_failed_dial_is_recorded_and_leaves_no_context(store):
    book(store)

    async def place(number, call_uuid, variables):
        return {"error": "ari down"}

    result = await run_reminder_cycle(store, place, NOW)
    assert result[0]["ok"] is False
    assert pop_context(result[0]["call_uuid"]) is None
    assert store.due_reminders(NOW + timedelta(minutes=100))  # will be retried


async def test_nothing_is_dialled_in_quiet_hours(store):
    book(store)
    calls = []

    async def place(*args):
        calls.append(args)
        return {}

    night = datetime(2026, 11, 2, 22, 0, tzinfo=CLINIC_TZ)
    assert await run_reminder_cycle(store, place, night) == []
    assert calls == []


async def test_run_forever_survives_a_failing_cycle(store, monkeypatch):
    import asyncio

    from shefa import reminders
    from shefa.config.settings import settings

    monkeypatch.setattr(settings.reminders, "interval_minutes", 1)
    runs = []

    async def cycle(*args, **kwargs):
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("boom")
        return []

    async def fast_sleep(_):
        if len(runs) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(reminders, "run_reminder_cycle", cycle)
    monkeypatch.setattr(reminders.asyncio, "sleep", fast_sleep)
    with pytest.raises(asyncio.CancelledError):
        await reminders.run_forever(store, lambda *a: None)
    assert len(runs) == 2


def test_cli_run_once_requires_configured_telephony(monkeypatch, capsys):
    from shefa.cli import main
    from shefa.config.settings import settings

    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "")
    assert main(["reminders", "run-once"]) == 1
    assert "not configured" in capsys.readouterr().err
    assert main(["reminders"]) == 2


def test_cli_run_once_with_nothing_due_places_nothing(store, monkeypatch, capsys):
    from shefa.cli import main
    from shefa.clinic import set_default_clinic_store
    from shefa.config.settings import settings

    book(store, day="2030-01-01")  # nowhere near the real clock's 24h window
    set_default_clinic_store(store)
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "AC1")
    monkeypatch.setattr("shefa.reminders.in_quiet_hours", lambda *a: False)
    assert main(["reminders", "run-once"]) == 0
    assert "0 of 0" in capsys.readouterr().out


async def test_outbound_context_shapes_the_greeting_and_the_session(monkeypatch):
    from shefa.audio import AudioFrame
    from shefa.pipeline.voice_pipeline import VoicePipeline
    from shefa.telephony.call_context import OutboundContext, set_context

    spoken = []
    answered = []

    class Tts:
        async def synthesize_stream(self, text, language="en"):
            spoken.append((text, language))
            yield AudioFrame(b"\x00" * 320, rate=16000)

    async def get_tts():
        return Tts()

    async def never(*a, **k):
        raise asyncio.CancelledError

    import asyncio

    from shefa.models.registry import registry

    monkeypatch.setattr(registry, "get_tts", get_tts)
    monkeypatch.setattr(registry, "get_stt", never)
    pipeline = VoicePipeline()
    set_context(
        "out-1",
        OutboundContext(
            greeting="আপনার অ্যাপয়েন্টমেন্ট APT-00001",
            patient_id="7",
            patient_name="Karim",
            on_answered=lambda: answered.append(1),
        ),
    )
    queue: asyncio.Queue = asyncio.Queue()

    async def sink(frame):
        return None

    with pytest.raises(asyncio.CancelledError):
        await pipeline.process_audio_stream("out-1", queue, sink)
    assert spoken[0] == ("আপনার অ্যাপয়েন্টমেন্ট APT-00001", "bn")
    assert answered == [1]
    session = await pipeline._session_manager.get_or_create("out-1")
    assert session.patient_id == "7" and session.patient_name == "Karim"


async def test_app_lifespan_runs_the_reminder_scheduler_when_enabled(monkeypatch):
    import asyncio

    from shefa import reminders
    from shefa.config.settings import settings
    from shefa.main import _lifespan

    started = asyncio.Event()

    async def fake_forever(store, place):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(settings.reminders, "enabled", True)
    monkeypatch.setattr(reminders, "run_forever", fake_forever)
    async with _lifespan(None):
        await asyncio.wait_for(started.wait(), 1)
