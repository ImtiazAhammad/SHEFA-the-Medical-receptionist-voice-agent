"""SHEFA checks itself: a failure reaches Telegram, a pass pings the outside monitor, and the
booking walk-through never touches the real clinic database."""

from __future__ import annotations

import pytest

from shefa import selftest
from shefa.clinic import default_clinic_store
from shefa.clinic.store import ClinicStore
from shefa.config.settings import settings


class Post:
    def __init__(self, status=200):
        self.status, self.calls = status, []

    def __call__(self, url, form):
        self.calls.append((url, form))
        return self.status


@pytest.fixture
def real_db(tmp_path, monkeypatch):
    path = tmp_path / "shefa.db"
    clinic = ClinicStore(path)
    dept = clinic.add_department("Medicine", "মেডিসিন")
    doctor = clinic.add_doctor("Kabir", dept, name_bn="কবির")
    for weekday in range(7):
        clinic.add_schedule(doctor, weekday, "00:00", "23:30", 30)
    clinic.close()
    monkeypatch.setattr(settings.storage, "db_path", str(path))
    return path


@pytest.fixture
def telegram(monkeypatch):
    monkeypatch.setenv("SHEFA_TELEGRAM_TOKEN", "bot-token")
    monkeypatch.setattr(settings.alerts, "telegram_chat_id", "12345")
    monkeypatch.setattr(settings.alerts, "heartbeat_url", "https://hc.example/ping/abc")


def test_a_booking_walks_through_on_a_copy_only(real_db):
    before = real_db.read_bytes()
    check = selftest.check_booking(real_db)
    assert check.ok, check.detail
    assert real_db.read_bytes() == before  # the real database is untouched
    assert default_clinic_store().path != real_db.parent / "selftest.db"  # store restored


@pytest.mark.parametrize("mode", ["slot", "serial"])
def test_both_booking_modes_walk_through(real_db, mode):
    store = ClinicStore(real_db)
    store.set_booking_mode(store.doctors()[0]["id"], mode)
    store.close()
    assert selftest.check_booking(real_db).ok


def test_no_free_doctor_is_a_failure(tmp_path):
    path = tmp_path / "empty.db"
    ClinicStore(path).close()
    check = selftest.check_booking(path)
    assert not check.ok and "free place" in check.detail


def test_a_dead_model_is_reported():
    check = selftest.check_llm("http://127.0.0.1:9/v1")
    assert not check.ok and "does not answer" in check.detail


def test_a_full_disk_is_reported(tmp_path):
    assert not selftest.check_disk(tmp_path, min_free_mb=10**12).ok
    assert selftest.check_disk(tmp_path, min_free_mb=1).ok


def test_failure_goes_to_telegram_and_no_heartbeat(real_db, telegram, monkeypatch):
    monkeypatch.setattr(selftest, "check_llm", lambda: selftest.Check("llm", False, "down"))
    post = Post()
    checks = selftest.run(full=False, poster=post)
    assert not all(c.ok for c in checks)
    [(url, form)] = post.calls
    assert "api.telegram.org/botbot-token/sendMessage" in url
    assert form["chat_id"] == "12345" and "llm: down" in form["text"]


def test_a_pass_pings_the_outside_monitor_and_sends_no_alert(real_db, telegram, monkeypatch):
    monkeypatch.setattr(selftest, "check_llm", lambda: selftest.Check("llm", True))
    post = Post()
    assert all(c.ok for c in selftest.run(full=True, poster=post))
    assert post.calls == [("https://hc.example/ping/abc", None)]


def test_without_telegram_the_alert_is_logged_not_lost(monkeypatch, caplog):
    monkeypatch.delenv("SHEFA_TELEGRAM_TOKEN", raising=False)
    assert selftest.notify("x") is False
    assert "ALERT" in caplog.text


def test_selftest_bookings_are_kept_out_of_the_report(real_db, tmp_path):
    from shefa.report import weekly_report
    from shefa.store.calls import CallsStore

    store = ClinicStore(real_db)
    doctor = store.doctors()[0]
    slot = store.next_available(doctor["id"])
    patient = store.upsert_patient(selftest.TEST_PHONE, "Self Test")
    store.book(patient, doctor["id"], slot["date"], slot["time"], source="test")
    calls = CallsStore(tmp_path / "calls.db")
    assert weekly_report(store, calls)["bookings"]["total"] == 0
    calls.close()
    store.close()
