"""T7 countermeasures for the telephony surface and the PHI gatekeeper.

Two things the plan makes unconditional:

1. The Twilio router exists to be dialed. Its webhooks take unauthenticated
   POSTs by design, so it may only be mounted when the box is explicitly in
   single-user dev mode *and* bound to loopback. A public mount is an
   unauthenticated dial-in.
2. `validate_phi_access` has to be a real decision with a true audit trail.
   The old stub logged `authorized: True` for everyone, which is worse than
   no log at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sefa import main as main_module
from sefa.auth import AuthStore, hash_token
from sefa.config.settings import settings
from sefa.utils import compliance

CLINICIAN_TOKEN = "test-clinician-token-abcdefghijkl"
VIEWER_TOKEN = "test-viewer-token-abcdefghijklmnop"

ROLE_PERMISSIONS = {
    "viewer": ["sessions:read"],
    "clinician": ["sessions:read", "calls:place", "chat:use"],
    "admin": ["sessions:read", "calls:place", "chat:use", "config:read"],
}


def _viewer_store() -> AuthStore:
    return AuthStore(
        [("viewer", "viewer", hash_token(VIEWER_TOKEN))],
        ROLE_PERMISSIONS,
    )


@pytest.fixture
def store() -> AuthStore:
    return AuthStore(
        [("clinician", "clinician", hash_token(CLINICIAN_TOKEN))],
        ROLE_PERMISSIONS,
    )


def _toggle_dev_config(
    monkeypatch,
    *,
    provider: str = "twilio",
    dev_mode: bool = True,
    bind_host: str = "127.0.0.1",
) -> None:
    monkeypatch.setattr(settings.telephony, "provider", provider)
    monkeypatch.setattr(settings.auth, "dev_mode", dev_mode)
    monkeypatch.setattr(settings.auth, "bind_host", bind_host)


class TestTelephonyRouterGating:
    def test_not_mounted_by_default(self):
        """Out of the box this box is not dialable."""
        assert main_module._telephony_router_allowed() is False

    def test_mounted_only_with_twilio_plus_dev_mode_plus_loopback(self, monkeypatch):
        _toggle_dev_config(monkeypatch)
        assert main_module._telephony_router_allowed() is True

    def test_non_twilio_provider_is_never_mounted(self, monkeypatch):
        _toggle_dev_config(monkeypatch, provider="websocket")
        assert main_module._telephony_router_allowed() is False

    def test_off_dev_mode_is_never_mounted(self, monkeypatch):
        _toggle_dev_config(monkeypatch, dev_mode=False)
        assert main_module._telephony_router_allowed() is False

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::"])
    def test_a_routable_bind_is_never_mounted(self, monkeypatch, host):
        """Loopback is the point: dev_mode on a real interface is a live dial-in."""
        _toggle_dev_config(monkeypatch, bind_host=host)
        assert main_module._telephony_router_allowed() is False

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_loopback_aliases_count_as_loopback(self, monkeypatch, host):
        _toggle_dev_config(monkeypatch, bind_host=host)
        assert main_module._telephony_router_allowed() is True

    def test_gated_app_has_no_telephony_routes(self, monkeypatch, store):
        """When gating denies the mount, a webhook is a dead path, not an open one.

        A valid token is needed to reach the router at all — the auth middleware
        refuses first — so a credentialed request landing on the path proves the
        router is genuinely absent rather than merely guarded.
        """
        _toggle_dev_config(monkeypatch, bind_host="0.0.0.0", dev_mode=True)
        headers = {"Authorization": f"Bearer {CLINICIAN_TOKEN}"}
        with TestClient(main_module.create_app(store)) as test_client:
            for path in ("/api/v1/telephony/incoming-call", "/api/v1/telephony/status"):
                response = test_client.post(path, headers=headers)
                assert response.status_code == 404, path

    def test_mounted_router_still_requires_a_token(self, monkeypatch, store):
        """Dev mode shrinks the blast radius; it does not remove auth."""
        _toggle_dev_config(monkeypatch)
        with TestClient(main_module.create_app(store)) as test_client:
            response = test_client.post(
                "/api/v1/telephony/incoming-call", headers={"Authorization": "Bearer x"}
            )
            assert response.status_code in (401, 403)

    def test_static_route_does_not_unmount_the_telephony_gate(self, monkeypatch, store):
        """Route-level declared permissions keep applying even to the router."""
        _toggle_dev_config(monkeypatch, bind_host="localhost")
        with TestClient(main_module.create_app(store)) as test_client:
            response = test_client.get(
                "/api/v1/telephony/schema", headers={"Authorization": "Bearer x"}
            )
            assert response.status_code in (401, 403, 404)


class TestValidatePhiAccessIsARealDecision:
    def test_patient_phi_read_requires_permission(self, store, monkeypatch):
        granted: list[dict] = []
        monkeypatch.setattr(compliance, "audit_log", lambda **kw: granted.append(kw))

        assert compliance.validate_phi_access("clinician", "PAT-1", "read", store)
        assert granted[-1]["details"]["authorized"] is True

    def test_unknown_requester_is_refused(self, store):
        assert compliance.validate_phi_access("auditor", "PAT-1", "read", store) is False

    def test_underprivileged_requester_is_refused(self):
        """A viewer can read sessions but cannot place a PHI-bearing call.

        The denial has to come from the permission decision, not from a missing
        principal.
        """
        viewer_store = _viewer_store()
        assert (
            compliance.validate_phi_access("viewer", "PAT-1", "call", viewer_store)
            is False
        )

    def test_the_audit_trail_records_the_real_verdict(self, store, monkeypatch):
        events: list[dict] = []
        monkeypatch.setattr(compliance, "audit_log", lambda **kw: events.append(kw))

        assert compliance.validate_phi_access("unknown", "PAT-1", "read", store) is False
        assert compliance.validate_phi_access("clinician", "PAT-1", "read", store)

        assert events[0]["details"]["authorized"] is False
        assert events[1]["details"]["authorized"] is True
        assert events[0]["patient_id"] == "PAT-1"

    def test_unknown_action_is_refused_without_a_fabricated_grant(self, store):
        assert (
            compliance.validate_phi_access("clinician", "PAT-1", "delete", store)
            is False
        )

    def test_no_principals_means_no_access(self):
        empty = AuthStore([], {})
        assert compliance.validate_phi_access("clinician", "PAT-1", "read", empty) is False

    def test_action_permissions_are_applied(self):
        """The action must map to a permission the requester holds.

        A viewer has sessions:read but not calls:place, so 'read' is granted and
        'call' is refused — proof the action maps to a real permission rather
        than every action being yes.
        """
        viewer_store = _viewer_store()
        assert (
            compliance.validate_phi_access("viewer", "PAT-1", "read", viewer_store)
            is True
        )
        assert (
            compliance.validate_phi_access("viewer", "PAT-1", "call", viewer_store)
            is False
        )