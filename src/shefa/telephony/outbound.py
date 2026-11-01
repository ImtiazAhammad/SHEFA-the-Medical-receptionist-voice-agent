"""Provider-neutral outbound dialling."""

from __future__ import annotations

from typing import Any

from shefa.config.settings import TelephonyProvider, settings


def outbound_configured() -> bool:
    """True when the selected provider has what it needs to place a call."""
    provider = settings.telephony.provider
    if provider == TelephonyProvider.BROWSER:
        return True
    if provider == TelephonyProvider.TWILIO:
        return bool(settings.telephony.twilio.account_sid)
    if provider == TelephonyProvider.ASTERISK:
        return bool(settings.telephony.asterisk.ari_password)
    return False


async def place_call(
    number: str,
    call_uuid: str | None = None,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Dial `number` on the configured provider; failures come back as `{"error": ...}`."""
    provider = settings.telephony.provider
    if provider == TelephonyProvider.ASTERISK:
        from shefa.telephony.asterisk import originate_call

        return await originate_call(number, call_uuid, variables)
    if provider == TelephonyProvider.BROWSER:
        from shefa.telephony.browser import place_call as ring_console

        return await ring_console(number, call_uuid, variables)
    if provider == TelephonyProvider.TWILIO:
        from shefa.telephony.twilio import initiate_outbound_call

        return await initiate_outbound_call(number)
    return {"error": f"Outbound calls are not implemented for provider {provider.value!r}"}
