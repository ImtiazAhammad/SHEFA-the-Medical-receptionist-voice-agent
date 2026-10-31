from __future__ import annotations

import pytest

from shefa.config.settings import TelephonyProvider, settings
from shefa.telephony import asterisk, outbound, twilio


@pytest.fixture
def provider(monkeypatch):
    def use(value: TelephonyProvider) -> None:
        monkeypatch.setattr(settings.telephony, "provider", value)

    return use


async def test_asterisk_dials_through_ari(monkeypatch, provider):
    provider(TelephonyProvider.ASTERISK)
    calls = []

    async def fake(number, call_uuid, variables):
        calls.append((number, call_uuid, variables))
        return {"call_sid": "u"}

    monkeypatch.setattr(asterisk, "originate_call", fake)
    assert await outbound.place_call("017", "u", {"A": "1"}) == {"call_sid": "u"}
    assert calls == [("017", "u", {"A": "1"})]


async def test_twilio_dials_through_twilio(monkeypatch, provider):
    provider(TelephonyProvider.TWILIO)

    async def fake(number):
        return {"call_sid": "tw", "number": number}

    monkeypatch.setattr(twilio, "initiate_outbound_call", fake)
    assert (await outbound.place_call("017"))["call_sid"] == "tw"


async def test_unimplemented_provider_is_an_error_not_a_silent_drop(provider):
    provider(TelephonyProvider.FREESWITCH)
    assert "freeswitch" in (await outbound.place_call("017"))["error"]


def test_configured_checks_the_selected_providers_credentials(monkeypatch, provider):
    provider(TelephonyProvider.ASTERISK)
    monkeypatch.setattr(settings.telephony.asterisk, "ari_password", "")
    assert outbound.outbound_configured() is False
    monkeypatch.setattr(settings.telephony.asterisk, "ari_password", "x")
    assert outbound.outbound_configured() is True
    provider(TelephonyProvider.TWILIO)
    monkeypatch.setattr(settings.telephony.twilio, "account_sid", "")
    assert outbound.outbound_configured() is False
    provider(TelephonyProvider.FREESWITCH)
    assert outbound.outbound_configured() is False
