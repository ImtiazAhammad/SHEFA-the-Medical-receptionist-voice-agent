# ruff: noqa: E501
"""Sending an SMS through a Bangladeshi bulk-SMS gateway, and saying honestly when it did not go.

Most Bangladeshi gateways take one HTTP request with an API key, a sender id, the number and the
text. Instead of one adapter per company, the clinic writes its gateway's address as a template:

    integrations.notifications.sms:
      provider: http
      url: "https://gateway.example/api/send?api_key={api_key}&senderid={sender_id}&number={to}&message={text}"
      method: GET            # or POST (form fields from `form`)
      api_key_env: SHEFA_SMS_API_KEY   # the key is read from this environment variable
      sender_id: "SHEFA"
      number_format: "880"   # 8801711000000; "0" for 01711000000
      success_contains: ""   # some gateways answer 200 with an error body: text a success must contain

With `provider: none` (the default) nothing is sent and every message is recorded as
`not_configured`, so no screen and no voice ever claims an SMS that was not sent.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

TIMEOUT_S = 15


@dataclass(frozen=True)
class SmsResult:
    status: str  # 'sent' | 'failed' | 'not_configured'
    detail: str = ""

    @property
    def sent(self) -> bool:
        return self.status == "sent"


# (method, url, form or None) -> (http status, body text); replaced in tests
Transport = Callable[[str, str, dict[str, str] | None], tuple[int, str]]


def _http(method: str, url: str, form: dict[str, str] | None) -> tuple[int, str]:
    import httpx

    with httpx.Client(timeout=TIMEOUT_S) as client:
        response = client.request(method, url, data=form)
    return response.status_code, response.text[:500]


def bd_number(phone: str, number_format: str = "880") -> str:
    """01711000000 / +8801711000000 / 8801711000000 in the form the gateway wants."""
    from shefa.clinic.store import normalize_phone

    local = normalize_phone(phone)
    if number_format == "880" and local.startswith("01") and len(local) == 11:
        return "88" + local
    return local


class SmsSender:
    def __init__(self, config: Any, transport: Transport | None = None):
        self.cfg = config
        self.transport = transport or _http

    def problem(self) -> str:
        """Why this sender cannot send, or '' when it can."""
        provider = (getattr(self.cfg, "provider", "") or "none").lower()
        if provider == "none":
            return "no SMS gateway is set up"
        if provider != "http":
            return f"SMS provider '{provider}' is not supported (use 'http')"
        if not getattr(self.cfg, "url", ""):
            return "the SMS gateway address (url) is empty"
        if "{api_key}" in self.cfg.url + str(getattr(self.cfg, "form", {})) and not self._key():
            return f"the SMS API key is missing (set {self.cfg.api_key_env})"
        return ""

    def _key(self) -> str:
        return os.environ.get(getattr(self.cfg, "api_key_env", "") or "", "")

    def send(self, to: str, text: str) -> SmsResult:
        why = self.problem()
        if why:
            return SmsResult("not_configured", why)
        number = bd_number(to, getattr(self.cfg, "number_format", "880"))
        values = {
            "api_key": self._key(),
            "sender_id": getattr(self.cfg, "sender_id", ""),
            "to": number,
            "text": text,
        }
        method = (getattr(self.cfg, "method", "GET") or "GET").upper()
        quoted = {k: urllib.parse.quote(v, safe="") for k, v in values.items()}
        try:
            url = self.cfg.url.format(**quoted)
            fields = getattr(self.cfg, "form", {}) or {}
            form = (
                {k: str(v).format(**values) for k, v in fields.items()}
                if method == "POST"
                else None
            )
        except (KeyError, IndexError, ValueError) as e:
            return SmsResult("failed", f"the gateway template has an unknown field: {e}")
        try:
            status, body = self.transport(method, url, form)
        except Exception as e:  # network down, DNS, TLS: the message did not go
            logger.warning("SMS to %s failed: %s", number[-4:], e)
            return SmsResult("failed", f"could not reach the gateway: {type(e).__name__}")
        if not 200 <= status < 300:
            return SmsResult("failed", f"gateway answered {status}: {body[:120]}")
        must = getattr(self.cfg, "success_contains", "") or ""
        if must and must not in body:
            return SmsResult("failed", f"gateway did not confirm: {body[:120]}")
        return SmsResult("sent", body[:120])


def sender_from_settings(transport: Transport | None = None) -> SmsSender:
    from shefa.config.settings import settings

    return SmsSender(settings.integrations.notifications.sms, transport)
