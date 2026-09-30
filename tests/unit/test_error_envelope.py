"""T10: one error envelope, one status map, no 200-with-error-body.

D-ENG14: four endpoints (and the auth middleware) smuggled `{"error": ...}`
out on a `200` status, so an HTTP client that checks the status line saw a
success and only a body-inspecting client saw the failure. The envelope
contract here is that every failure renders as
`{"error": {"code": str, "message": str}}` on a *non-2xx* status, and the
status map is the single source of truth for the code→status pairing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from sefa import main as main_module
from sefa.auth import AuthStore, hash_token

ADMIN_TOKEN = "admin-token-abcdefghijklmnop"
CLINICIAN_TOKEN = "clinician-token-abcdefghijklmno"
VIEWER_TOKEN = "viewer-token-abcdefghijklmnopq"

ROLE_PERMISSIONS = {
    "viewer": ["sessions:read"],
    "clinician": ["sessions:read", "calls:place", "chat:use"],
    "admin": ["sessions:read", "calls:place", "chat:use", "config:read"],
}


@pytest.fixture
def client():
    store = AuthStore(
        [
            ("viewer", "viewer", hash_token(VIEWER_TOKEN)),
            ("clinician", "clinician", hash_token(CLINICIAN_TOKEN)),
            ("admin", "admin", hash_token(ADMIN_TOKEN)),
        ],
        ROLE_PERMISSIONS,
    )
    with TestClient(main_module.create_app(store)) as test_client:
        yield test_client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestEveryErrorWearsTheEnvelope:
    def test_auth_middleware_failures_use_the_envelope(self, client):
        resp = client.get("/health")
        assert resp.status_code == 401
        assert resp.json() == {
            "error": {"code": "authentication_required", "message": "Authentication required."}
        }

    def test_insufficient_role_uses_the_envelope(self, client):
        resp = client.get("/api/v1/tools", headers=_bearer(VIEWER_TOKEN))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "insufficient_role"

    def test_undeclared_routes_use_the_envelope(self, client):
        resp = client.get("/api/v1/nonexistent", headers=_bearer(VIEWER_TOKEN))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "route_not_authorized"

    def test_missing_session_is_a_404_with_the_envelope(self, client):
        resp = client.get(
            "/api/v1/sessions/absent", headers=_bearer(CLINICIAN_TOKEN)
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "session_not_found"

    def test_required_outbound_number_is_a_422_with_the_envelope(self, client):
        resp = client.post(
            "/api/v1/calls/outbound", headers=_bearer(CLINICIAN_TOKEN)
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "required_param"

    def test_unconfigured_twilio_is_a_503_with_the_envelope(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module.settings.telephony.twilio, "account_sid", ""
        )
        resp = client.post(
            "/api/v1/calls/outbound",
            params={"to_number": "+15551234567"},
            headers=_bearer(CLINICIAN_TOKEN),
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "not_configured"

    def test_missing_chat_message_is_a_422_with_the_envelope(self, client):
        resp = client.post("/api/v1/chat", headers=_bearer(CLINICIAN_TOKEN))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "required_param"

    def test_call_me_without_a_verified_number_is_a_503(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module.settings.telephony.twilio, "account_sid", "AC123"
        )
        monkeypatch.setattr(main_module.settings.telephony.twilio, "phone_number", "")
        monkeypatch.delenv("VERIFIED_NUMBER", raising=False)
        resp = client.post("/api/v1/calls/call-me", headers=_bearer(CLINICIAN_TOKEN))
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "verified_number_missing"


class TestTheStatusMapIsTheSingleSourceOfTruth:
    def test_every_code_maps_to_a_range_non_2xx_status(self):
        assert main_module.ERROR_STATUS_MAP
        for code, status in main_module.ERROR_STATUS_MAP.items():
            assert 400 <= status < 600, (code, status) 

    def test_the_map_covers_every_code_the_handlers_speak(self):
        covered = set(main_module.ERROR_STATUS_MAP)
        assert {
            "authentication_required",
            "insufficient_role",
            "route_not_authorized",
            "session_not_found",
            "required_param",
            "not_configured",
            "verified_number_missing",
            "validation",
        } <= covered


class TestFastAPIValidationIsEnveloped:
    def test_request_validation_errors_are_422_envelopes(self, client):
        handler = client.app.exception_handlers[RequestValidationError]

        class _FakeRequest:
            url = None

        exc = RequestValidationError(
            [{"type": "missing", "loc": ("query", "to_number"), "msg": "Field required"}]
        )
        response = handler(_FakeRequest(), exc)
        assert response.status_code == 422
        assert json.loads(response.body)["error"]["code"] == "validation"

    def test_plain_http_exception_details_are_also_enveloped(self, client):
        handler = client.app.exception_handlers[HTTPException]

        class _FakeRequest:
            url = None

        response = handler(_FakeRequest(), HTTPException(status_code=400, detail="boom"))
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"]["code"] == "http_error"
        assert body["error"]["message"] == "boom"


class TestTheMigrationListIsDeclared:
    def test_main_names_an_explicit_http_exception_migration_list(self):
        source = Path(main_module.__file__).read_text(encoding="utf-8")
        assert "HTTPException migration list" in source
        assert "session_not_found" in source
        assert "required_param" in source