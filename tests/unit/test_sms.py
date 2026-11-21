"""SMS: sent only when a gateway accepts it, recorded every time, never claimed when it did not go.

The old code returned `sent: True` without sending anything; these tests pin the honest version.
A fake transport stands in for the gateway: no test sends a real message."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from shefa.auth import AuthStore, hash_token
from shefa.clinic import default_clinic_store
from shefa.config.settings import settings
from shefa.integrations.notifications import confirmation_text, send_booking_sms, send_confirmation
from shefa.integrations.sms import SmsSender, bd_number
from shefa.main import create_app

PHONE = "01711000123"


def gateway(**over):
    base = {
        "provider": "http",
        "url": "https://sms.example/send?key={api_key}&from={sender_id}&to={to}&msg={text}",
        "method": "GET",
        "form": {},
        "api_key_env": "SHEFA_TEST_SMS_KEY",
        "sender_id": "CLINIC",
        "number_format": "880",
        "success_contains": "",
    }
    return SimpleNamespace(**(base | over))


class FakeGateway:
    def __init__(self, status=200, body='{"ok":true}', boom=None):
        self.status, self.body, self.boom, self.calls = status, body, boom, []

    def __call__(self, method, url, form):
        self.calls.append((method, url, form))
        if self.boom:
            raise self.boom
        return self.status, self.body


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("SHEFA_TEST_SMS_KEY", "secret-key")


@pytest.fixture
def booking():
    clinic = default_clinic_store()
    clinic.set_setting("name_bn", "আলো ক্লিনিক")
    dept = clinic.add_department("Neurology", "নিউরোলজি")
    doctor = clinic.add_doctor("Kabir", dept, name_bn="কবির")
    for weekday in range(7):
        clinic.add_schedule(doctor, weekday, "17:00", "21:00", 15)
    patient = clinic.upsert_patient(PHONE, "রহিম")
    day = (date.today() + timedelta(days=1)).isoformat()
    return clinic, patient, clinic.book(patient, doctor, day, "17:30")


def test_no_gateway_means_not_sent_and_says_why():
    result = SmsSender(SimpleNamespace(provider="none")).send(PHONE, "hi")
    assert not result.sent and result.status == "not_configured" and "gateway" in result.detail


def test_old_twilio_setting_is_not_silently_treated_as_working():
    result = SmsSender(SimpleNamespace(provider="twilio")).send(PHONE, "hi")
    assert result.status == "not_configured" and "twilio" in result.detail


def test_missing_key_is_reported_not_sent_with_an_empty_key(monkeypatch):
    monkeypatch.delenv("SHEFA_TEST_SMS_KEY", raising=False)
    fake = FakeGateway()
    result = SmsSender(gateway(), fake).send(PHONE, "hi")
    assert result.status == "not_configured" and "SHEFA_TEST_SMS_KEY" in result.detail
    assert fake.calls == []


def test_a_good_gateway_gets_the_bangladeshi_number_and_the_bangla_text_encoded(key):
    fake = FakeGateway()
    result = SmsSender(gateway(), fake).send(PHONE, "আপনার বুকিং নিশ্চিত")
    assert result.sent
    method, url, form = fake.calls[0]
    assert method == "GET" and form is None
    assert "to=8801711000123" in url and "key=secret-key" in url and "from=CLINIC" in url
    assert "আপনার" not in url and "%E0%A6" in url  # percent-encoded UTF-8


def test_post_gateways_get_form_fields(key):
    fake = FakeGateway()
    cfg = gateway(
        method="POST",
        url="https://sms.example/api",
        form={"api_key": "{api_key}", "msisdn": "{to}"},
    )
    assert SmsSender(cfg, fake).send(PHONE, "x").sent
    assert fake.calls[0][2] == {"api_key": "secret-key", "msisdn": "8801711000123"}


@pytest.mark.parametrize(
    ("fake", "why"),
    [
        (FakeGateway(status=500, body="down"), "500"),
        (FakeGateway(boom=ConnectionError("no route")), "could not reach"),
        (FakeGateway(body='{"status":"error","msg":"low balance"}'), "did not confirm"),
    ],
)
def test_gateway_failures_are_failures(key, fake, why):
    cfg = gateway(success_contains='"ok":true')
    result = SmsSender(cfg, fake).send(PHONE, "x")
    assert result.status == "failed" and why in result.detail


def test_numbers_in_either_form():
    assert bd_number("+8801711000123") == "8801711000123"
    assert bd_number("01711000123", "0") == "01711000123"


def test_confirmation_text_is_short_and_says_the_real_booking(booking):
    clinic, _patient, appt = booking
    doctor = clinic.doctor(appt["doctor_id"])
    text = confirmation_text(appt, doctor, "আলো ক্লিনিক", "bn")
    assert text.startswith("আলো ক্লিনিক: বুকিং নিশ্চিত") and "কবির" in text
    assert "বিকাল ৫:৩০" in text and appt["appointment_id"] in text
    assert len(text) <= 140  # two Bangla SMS parts at most
    serial = confirmation_text({**appt, "serial_no": 3}, doctor, "X", "bn")
    assert "সিরিয়াল ৩" in serial and "আনুমানিক" in serial
    assert "5:30 pm" in confirmation_text(appt, doctor, "Alo", "en")


def test_every_attempt_is_recorded_sent_or_not(booking, key):
    clinic, _patient, appt = booking
    off = send_booking_sms(
        appt["appointment_id"], sender=SmsSender(SimpleNamespace(provider="none"))
    )
    assert off["sent"] is False and off["status"] == "not_configured"
    on = send_booking_sms(appt["appointment_id"], sender=SmsSender(gateway(), FakeGateway()))
    assert on["sent"] is True
    log = clinic.messages(appointment_id=appt["id"])
    assert [m["status"] for m in log] == ["sent", "not_configured"]
    assert log[0]["to_phone"] == PHONE and "কবির" in log[0]["body"]


async def test_the_agent_tool_no_longer_claims_a_message_it_did_not_send(booking):
    _clinic, patient, appt = booking
    got = await send_confirmation(str(patient), appt["appointment_id"], "sms", "bn")
    assert got["sent"] is False and got["reason"]  # default config: no gateway


async def test_the_agent_tool_refuses_someone_elses_booking(booking):
    clinic, _patient, appt = booking
    other = clinic.upsert_patient("01811000999", "অন্য")
    got = await send_confirmation(str(other), appt["appointment_id"], "sms", "bn")
    assert got["sent"] is False and got["reason"] == "unknown appointment"


async def test_email_is_reported_as_not_set_up(booking):
    _clinic, patient, appt = booking
    got = await send_confirmation(str(patient), appt["appointment_id"], "email", "bn")
    assert got["sent"] is False and got["status"] == "not_configured"


def test_the_desk_confirm_button_reports_the_sms_outcome(booking, monkeypatch):
    clinic, _patient, appt = booking
    monkeypatch.setattr(settings.integrations.notifications.sms, "provider", "none")
    staff = TestClient(
        create_app(
            AuthStore([("desk", "admin", hash_token("y" * 32))], {"admin": ["records:write"]})
        ),
        base_url="https://testserver",
    )
    staff.headers["Authorization"] = "Bearer " + "y" * 32
    got = staff.post(f"/api/v1/appointments/{appt['appointment_id']}/confirm").json()
    assert got["confirmed"] is True and got["sms"]["sent"] is False
    assert got["sms"]["status"] == "not_configured"
    assert clinic.messages(appointment_id=appt["id"])[0]["kind"] == "confirmation"
