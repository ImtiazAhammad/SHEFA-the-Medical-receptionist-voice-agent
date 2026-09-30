"""Every route must reject an unauthenticated caller.

The plan's bar for T7 is exact: an unauthenticated request gets 401/403 on
*every* route. That includes `/health` and `/`, because a liveness probe that
answers anyone is also an open door to whatever else the app reveals, and a
half-protected surface is the kind of thing that gets assumed safe in review.

These tests walk the live route table rather than a hand-written list, so a route
added later cannot quietly skip authorization.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sefa import main as main_module
from sefa.auth import AuthStore, TokenError, hash_token

ADMIN_TOKEN = "admin-token-abcdefghijklmnop"
CLINICIAN_TOKEN = "clinician-token-abcdefghijklmno"
VIEWER_TOKEN = "viewer-token-abcdefghijklmnopq"

ROLE_PERMISSIONS = {
    "viewer": ["sessions:read"],
    "clinician": ["sessions:read", "calls:place", "chat:use"],
    "admin": ["sessions:read", "calls:place", "chat:use", "config:read"],
}

TOKENS = {
    "admin": ADMIN_TOKEN,
    "clinician": CLINICIAN_TOKEN,
    "viewer": VIEWER_TOKEN,
}


def _store(principals: dict[str, str] | None = None) -> AuthStore:
    """A store built from `role=token` pairs, with production KDF settings."""
    pairs = TOKENS if principals is None else principals
    return AuthStore(
        [(role, role, hash_token(token)) for role, token in pairs.items()],
        {role: ROLE_PERMISSIONS[role] for role in pairs if role in ROLE_PERMISSIONS},
    )


@pytest.fixture(scope="module")
def shared_store() -> AuthStore:
    """Hashed once for the module: production KDF cost is ~0.5s per token."""
    return _store()


@pytest.fixture
def client(shared_store):
    """An app whose auth store is fully configured with all three roles."""
    with TestClient(main_module.create_app(shared_store)) as test_client:
        yield test_client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _routes(app) -> list[tuple[str, str, str]]:
    """(method, path, name) for every request-serving route, docs excluded."""
    found = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        if path.startswith(("/openapi", "/docs", "/redoc")):
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            found.append((method, path, getattr(route, "name", "?")))
    return found


class TestEveryRouteRequiresAuthentication:
    def test_an_unauthenticated_request_is_refused_everywhere(self, client):
        app = client.app
        routes = _routes(app)

        assert routes, "route table came back empty; the test would pass vacuously"

        allowed = []
        for method, path, _name in routes:
            response = client.request(method, path)
            if response.status_code not in (401, 403):
                allowed.append((method, path, response.status_code))

        assert allowed == [], f"routes served without a credential: {allowed}"

    def test_a_wrong_token_is_refused_everywhere(self, client):
        allowed = []
        for method, path, _name in _routes(client.app):
            response = client.request(
                method, path, headers=_bearer("wrong-token-aaaaaaaaaaaaaaaaaaaa")
            )
            if response.status_code not in (401, 403):
                allowed.append((method, path, response.status_code))

        assert allowed == [], f"routes accepted a wrong token: {allowed}"

    def test_every_route_declares_its_required_permission(self, client):
        """A route with no declared permission is denied, not skipped.

        Fail-closed means an undeclared route is unreachable. A developer adding
        a route must also declare its permission, and this test is what makes
        that a deliberate step rather than an oversight.
        """
        undeclared = [
            (method, path)
            for method, path, _name in _routes(client.app)
            if main_module.required_permission(client.app, method, path) is None
        ]

        assert undeclared == [], (
            f"routes with no declared permission (denied by default): {undeclared}"
        )

    def test_a_static_asset_is_not_readable_without_a_token(self, client):
        response = client.get("/static/index.html")

        assert response.status_code in (401, 403)

    def test_the_docs_are_not_reachable_without_a_token(self, client):
        for path in ("/docs", "/openapi.json"):
            response = client.get(path)
            assert response.status_code in (401, 403), path


class TestStatusCodes:
    def test_no_credentials_is_401(self, client):
        response = client.get("/api/v1/sessions")

        assert response.status_code == 401

    def test_bad_credentials_is_401(self, client):
        response = client.get("/api/v1/sessions", headers=_bearer("nope" * 6))

        assert response.status_code == 401

    def test_a_malformed_header_is_401(self, client):
        for header in ("Bearer", "Basic abc", "Bearer   ", ADMIN_TOKEN, "Token x"):
            response = client.get("/api/v1/sessions", headers={"Authorization": header})
            assert response.status_code == 401, header

    def test_a_valid_token_without_the_permission_is_403(self, client):
        response = client.get(
            "/api/v1/calls/call-me", headers=_bearer(VIEWER_TOKEN)
        )

        assert response.status_code == 403

    def test_401_and_403_do_not_leak_whether_a_token_exists(self, client):
        """A body difference between 'no token' and 'bad token' is an oracle."""
        anonymous = client.get("/api/v1/sessions")
        wrong = client.get("/api/v1/sessions", headers=_bearer("x" * 40))

        assert anonymous.status_code == wrong.status_code
        assert anonymous.json() == wrong.json()

    def test_a_401_advertises_the_scheme(self, client):
        response = client.get("/api/v1/sessions")

        assert response.headers.get("WWW-Authenticate") == "Bearer"

    def test_an_unmatched_http_method_on_a_known_path_is_still_refused(self, client):
        """POST to a GET-only path must not fall through to a route's permission.

        The middleware matches method-to-route before looking up a permission;
        a write that misses its method must be refused, not silently reused.
        """
        response = client.post("/api/v1/sessions", headers=_bearer(CLINICIAN_TOKEN))

        assert response.status_code in (401, 403, 405)
        assert response.status_code != 200

    def test_a_patternless_route_is_not_granted_access(self):
        """A route without a compiled path pattern cannot match, so it is skipped
        and the request is refused rather than inferred open."""
        from types import SimpleNamespace

        app = SimpleNamespace(
            routes=[SimpleNamespace(path="/x", path_regex=None, methods={"GET"})]
        )

        assert main_module.required_permission(app, "GET", "/x") is None


class TestAuthorizedAccess:
    def test_a_viewer_can_read_sessions(self, client):
        response = client.get("/api/v1/sessions", headers=_bearer(VIEWER_TOKEN))

        assert response.status_code == 200

    def test_a_viewer_cannot_place_a_call(self, client):
        assert (
            client.post(
                "/api/v1/calls/call-me", headers=_bearer(VIEWER_TOKEN)
            ).status_code
            == 403
        )

    def test_a_clinician_can_place_a_call(self, client, monkeypatch):
        monkeypatch.setattr(main_module.settings.telephony.twilio, "account_sid", "AC1")
        monkeypatch.setattr(
            main_module.settings.telephony.twilio, "phone_number", "+15551234567"
        )

        async def fake_call(number: str) -> dict:
            return {"status": "queued", "to": number}

        monkeypatch.setattr("sefa.telephony.twilio.initiate_outbound_call", fake_call)

        response = client.post("/api/v1/calls/call-me", headers=_bearer(CLINICIAN_TOKEN))

        assert response.status_code == 200
        assert response.json()["to"] == "+15551234567"

    def test_an_admin_can_read_config(self, client):
        response = client.get("/api/v1/config", headers=_bearer(ADMIN_TOKEN))

        assert response.status_code == 200

    def test_a_clinician_cannot_read_config(self, client):
        response = client.get("/api/v1/config", headers=_bearer(CLINICIAN_TOKEN))

        assert response.status_code == 403

    def test_a_viewer_cannot_use_chat(self, client):
        response = client.post(
            "/api/v1/chat", params={"message": "hi"}, headers=_bearer(VIEWER_TOKEN)
        )

        assert response.status_code == 403

    def test_health_needs_a_token_too(self, client):
        assert client.get("/health").status_code == 401
        assert client.get("/health", headers=_bearer(VIEWER_TOKEN)).status_code == 200

    def test_a_clinician_can_read_the_root_index(self, client):
        response = client.get("/", headers=_bearer(CLINICIAN_TOKEN))

        assert response.status_code == 200

    def test_a_clinician_can_open_the_dashboard(self, client):
        response = client.get("/dashboard", headers=_bearer(CLINICIAN_TOKEN))

        assert response.status_code == 200
        assert response.text.strip() != ""

    def test_list_sessions_round_trips_a_created_session(self, client, monkeypatch):
        from sefa.session.manager import CallSession

        main_module.session_manager._sessions["SID-1"] = CallSession(
            call_sid="SID-1", patient_id="PAT-1", patient_name="Tester"
        )

        response = client.get("/api/v1/sessions", headers=_bearer(VIEWER_TOKEN))
        assert response.status_code == 200
        assert [s["call_sid"] for s in response.json()] == ["SID-1"]

        found = client.get("/api/v1/sessions/SID-1", headers=_bearer(VIEWER_TOKEN))
        assert found.status_code == 200
        assert "PAT-1" in str(found.json())

        missing = client.get("/api/v1/sessions/absent", headers=_bearer(VIEWER_TOKEN))
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "session_not_found"

    def test_outbound_call_requires_a_number(self, client):
        response = client.post("/api/v1/calls/outbound", headers=_bearer(CLINICIAN_TOKEN))

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "required_param"

    def test_outbound_call_refuses_when_twilio_is_unconfigured(self, client, monkeypatch):
        monkeypatch.setattr(main_module.settings.telephony.twilio, "account_sid", "")
        response = client.post(
            "/api/v1/calls/outbound",
            params={"to_number": "+15551234567"},
            headers=_bearer(CLINICIAN_TOKEN),
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "not_configured"

    def test_outbound_call_places_when_configured(self, client, monkeypatch):
        monkeypatch.setattr(
            main_module.settings.telephony.twilio, "account_sid", "AC1"
        )

        async def fake_call(number: str) -> dict:
            return {"status": "queued", "to": number}

        monkeypatch.setattr("sefa.telephony.twilio.initiate_outbound_call", fake_call)

        response = client.post(
            "/api/v1/calls/outbound",
            params={"to_number": "+15551234567"},
            headers=_bearer(CLINICIAN_TOKEN),
        )

        assert response.status_code == 200
        assert response.json()["to"] == "+15551234567"

    def test_an_admin_can_list_the_tool_definitions(self, client):
        response = client.get("/api/v1/tools", headers=_bearer(ADMIN_TOKEN))

        assert response.status_code == 200
        assert all("name" in tool for tool in response.json())

    def test_a_viewer_cannot_read_tools(self, client):
        assert (
            client.get("/api/v1/tools", headers=_bearer(VIEWER_TOKEN)).status_code
            == 403
        )


class TestUnconfiguredAuthLocksEverything:
    def test_no_configured_principal_means_no_access_at_all(self, monkeypatch):
        """Misconfiguration must fail closed, not open.

        An operator who forgot to onboard a token gets a locked API and a
        startup error, not a silently unauthenticated one.
        """
        with TestClient(main_module.create_app(AuthStore([], {}))) as test_client:
            for method, path, _name in _routes(test_client.app):
                response = test_client.request(
                    method, path, headers=_bearer(ADMIN_TOKEN)
                )
                assert response.status_code in (401, 403), (method, path)

    def test_create_app_with_no_store_reads_the_configured_principals(
        self, monkeypatch
    ):
        """Production entry point has to trust the config when no store is passed."""
        from sefa.config.settings import AuthPrincipalConfig

        monkeypatch.setattr(
            main_module.settings.auth,
            "principals",
            [
                AuthPrincipalConfig(
                    name="ops", role="admin", token_hash=hash_token(ADMIN_TOKEN)
                )
            ],
        )

        with TestClient(main_module.create_app()) as test_client:
            response = test_client.get("/api/v1/config", headers=_bearer(ADMIN_TOKEN))
            assert response.status_code == 200

    def test_a_weak_token_in_config_is_rejected_at_load(self):
        """Refuse to accept a credential that is really just a password."""
        with pytest.raises(TokenError, match="at least"):
            hash_token("short")

    def test_build_auth_store_reads_the_configured_principals(self, monkeypatch):
        """The store comes from config, so an operator can onboard without code."""
        from sefa.config.settings import AuthPrincipalConfig

        monkeypatch.setattr(
            main_module.settings.auth,
            "principals",
            [
                AuthPrincipalConfig(
                    name="front-desk", role="clinician", token_hash=hash_token(CLINICIAN_TOKEN)
                )
            ],
        )

        store = main_module.build_auth_store()

        assert store.is_configured is True
        assert store.authenticate(CLINICIAN_TOKEN).role == "clinician"
        assert store.authenticate(VIEWER_TOKEN) is None

    def test_an_unparseable_principal_hash_fails_the_startup(self, monkeypatch):
        """A bad record must be a loud startup failure, not a silent 401.

        Operators debug a locked API; they do not debug a 401 that looks like a
        wrong password. `sefa doctor` is where this should be caught, and the
        import must not paper over it either.
        """
        from sefa.config.settings import AuthPrincipalConfig

        monkeypatch.setattr(
            main_module.settings.auth,
            "principals",
            [
                AuthPrincipalConfig(
                    name="broken", role="admin", token_hash="not-a-real-record"
                )
            ],
        )

        with pytest.raises(TokenError):
            main_module.build_auth_store()
