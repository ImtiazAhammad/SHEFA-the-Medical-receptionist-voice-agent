"""SHEFA Receptionist - Main application entry point."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from shefa.auth import AuthStore, Principal, TokenError
from shefa.config.settings import TelephonyProvider, settings
from shefa.session.manager import SessionManager
from shefa.telephony.outbound import outbound_configured, place_call
from shefa.telephony.twilio import app as telephony_app
from shefa.tools.definitions import get_tool_definitions
from shefa.utils.logging import setup_logging

# The configured structlog pipeline is the ONLY server logger. Its PHI
# masking lives behind `monitoring.logging.phi_masking`, so every event in
# the process shares the same gate — no parallel renderer can unmask a
# number that this one already redacted.
setup_logging(
    level=settings.monitoring.logging.level,
    phi_masking=settings.monitoring.logging.phi_masking,
)

logger = structlog.get_logger("shefa")

session_manager = SessionManager()

_text_pipeline = None


def text_pipeline():
    """The pipeline behind typed chats; it shares `session_manager` so the chats are listed."""
    global _text_pipeline
    if _text_pipeline is None:
        from shefa.pipeline.voice_pipeline import VoicePipeline

        _text_pipeline = VoicePipeline(session_manager)
    return _text_pipeline

STATIC_DIR = Path(__file__).parent / "static"
APP_DIR = STATIC_DIR / "app"  # the built staff app (frontend/ -> npm run build)
APP_ASSETS_PREFIX = "/app-assets"

# --------------------------------------------------------------------------
# Error envelope + status map (D-ENG14).
#
# Every failure renders as `{"error": {"code": str, "message": str}}` on a
# non-2xx status. The map is the single source of truth between a stable
# machine code and the HTTP status, so an endpoint cannot drift back into
# the old 200-with-`{"error": ...}` style.
#
# HTTPException migration list — endpoints that used to smuggle an error out
# on a 200 status, now raised via `raise_http_error` and rendered by the
# shared exception handler:
#   GET  /api/v1/sessions/{sid}   session-not-found  200 -> 404
#   POST /api/v1/calls/outbound   required to_number 200 -> 422
#   POST /api/v1/calls/outbound   twilio unconfigured 200 -> 503
#   POST /api/v1/calls/call-me    no verified number 200 -> 503
#   POST /api/v1/calls/call-me    twilio unconfigured 200 -> 503
#   POST /api/v1/chat             required message   200 -> 422
# Routes are deliberately NOT auto-listed here; adding one to Child 1 means
# adding its code to the map and test_error_envelope.py coverage.
ERROR_STATUS_MAP: dict[str, int] = {
    "authentication_required": 401,
    "insufficient_role": 403,
    "route_not_authorized": 403,
    "session_not_found": 404,
    "call_not_found": 404,
    "callback_not_found": 404,
    "validation": 422,
    "required_param": 422,
    "not_configured": 503,
    "verified_number_missing": 503,
    "model_unavailable": 503,
    "name_invalid": 422,
    "phone_invalid": 422,
    "slot_invalid": 422,
    "doctor_unknown": 404,
    "rate_limited": 429,
    "too_many_open": 409,
    "already_booked": 409,
    "slot_taken": 409,
    "booking_not_found": 404,
    "not_cancellable": 409,
    "booking_closed": 404,
}

DEFAULT_ERROR_MESSAGES: dict[str, str] = {
    "authentication_required": "Authentication required.",
    "insufficient_role": "Insufficient role for this resource.",
    "route_not_authorized": "This route is not authorized.",
    "session_not_found": "Session not found",
    "call_not_found": "Call not found.",
    "callback_not_found": "Call-back not found.",
    "validation": "Request validation failed.",
    "required_param": "Required parameter missing.",
    "not_configured": "Dependency not configured.",
    "verified_number_missing": "No verified number configured.",
    "model_unavailable": "The language model did not answer.",
    "name_invalid": "Please give your name.",
    "phone_invalid": "Please give a mobile number.",
    "slot_invalid": "Please pick a day and a time.",
    "doctor_unknown": "That doctor is not available.",
    "rate_limited": "Too many requests. Please try again later.",
    "too_many_open": "Too many open bookings for this number.",
    "already_booked": "Already booked with this doctor that day.",
    "slot_taken": "That time was just taken.",
    "booking_not_found": "We could not find that booking.",
    "not_cancellable": "This booking cannot be cancelled.",
    "booking_closed": "Online booking is not available.",
}


def error_response(
    code: str,
    message: str | None = None,
    *,
    details: object = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Render one error in the shared envelope on its mapped status."""
    envelope_body = {
        "error": {
            "code": code,
            "message": message or DEFAULT_ERROR_MESSAGES.get(code, code),
        }
    }
    if details is not None:
        envelope_body["error"]["details"] = details
    return JSONResponse(
        status_code=ERROR_STATUS_MAP.get(code, 500),
        content=envelope_body,
        headers=headers,
    )


def raise_http_error(code: str, message: str | None = None) -> None:
    """Raise the HTTP error the shared handler renders for `code`."""
    raise HTTPException(
        status_code=ERROR_STATUS_MAP.get(code, 500),
        detail={"code": code, "message": message or DEFAULT_ERROR_MESSAGES.get(code, code)},
    )


def _http_error_handler(request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(
            status_code=exc.status_code, content={"error": detail}
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(detail)}},
    )


def _validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
    return error_response("validation", details=exc.errors())

MAX_EXPORT_DAYS = 93  # one quarter per request keeps an export a page, not a database dump

# The permission each route requires, keyed by (method, path).
# A permission value meaning "reachable without a credential". Distinct from
# `None`, which means "undeclared, therefore refused": naming a route with this
# is the deliberate, reviewable exception to "every route is protected".
PUBLIC_PERMISSION = "<public>"

#
# This map lives in code rather than config on purpose: config can grant a
# permission to a role, but it cannot un-protect a route. A route absent from
# this map is refused (see `required_permission`), so adding a route means
# adding its permission here as a deliberate act — `test_every_route_declares_
# its_required_permission` fails until you do.
ROUTE_PERMISSIONS: dict[tuple[str, str], str] = {
    ("GET", "/health"): "sessions:read",
    ("GET", "/"): "sessions:read",
    ("GET", "/dashboard"): "sessions:read",
    ("GET", "/test-call"): "calls:place",
    ("GET", "/api/v1/sessions"): "sessions:read",
    ("GET", "/api/v1/sessions/{call_sid}"): "sessions:read",
    ("POST", "/api/v1/calls/outbound"): "calls:place",
    ("POST", "/api/v1/calls/call-me"): "calls:place",
    ("POST", "/api/v1/chat"): "chat:use",
    ("GET", "/api/v1/config"): "config:read",
    ("GET", "/api/v1/tools"): "config:read",
    ("GET", "/api/v1/calls"): "records:read",
    ("GET", "/console"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/login"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/calls/ring"): "calls:place",
    ("GET", "/api/v1/calls/ringing"): "calls:place",
    ("GET", "/api/v1/calls/{call_sid}"): "records:read",
    ("POST", "/api/v1/calls/ringing/{call_uuid}/decline"): "calls:place",
    ("GET", "/api/v1/directory"): "records:read",
    ("POST", "/api/v1/appointments/{appointment_id}/status"): "records:write",
    ("POST", "/api/v1/appointments/{appointment_id}/confirm"): "records:write",
    ("POST", "/api/v1/appointments/walk-in"): "records:write",
    ("GET", "/api/v1/export/appointments"): "records:export",
    ("GET", "/api/v1/staff"): "staff:manage",
    ("GET", "/api/v1/staff/doctors"): "staff:manage",
    ("POST", "/api/v1/staff"): "staff:manage",
    ("POST", "/api/v1/staff/{username}/password"): "staff:manage",
    ("POST", "/api/v1/staff/{username}/active"): "staff:manage",
    ("POST", "/api/v1/reminders/run"): "records:write",
    ("GET", "/api/v1/appointments"): "records:read",
    ("GET", "/login"): PUBLIC_PERMISSION,
    ("DELETE", "/api/v1/calls/{call_sid}"): "records:write",
    ("GET", "/api/v1/callbacks"): "records:read",
    ("POST", "/api/v1/callbacks/{callback_id}/resolve"): "records:write",
    ("GET", "/api/v1/overview"): "overview:read",
    ("GET", "/api/v1/report"): "overview:read",
    ("GET", "/api/v1/me/day"): "doctor:self",
    ("GET", "/api/v1/me/doctor"): "doctor:self",
    ("POST", "/api/v1/me/appointments/{appointment_id}/status"): "doctor:self",
    ("GET", "/app"): PUBLIC_PERMISSION,
    ("GET", "/app/{path:path}"): PUBLIC_PERMISSION,
    ("GET", "/api/v1/me"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/logout"): PUBLIC_PERMISSION,
    # The patient booking page: public by design, limited and validated in shefa.booking.
    ("GET", "/api/v1/public/clinic"): PUBLIC_PERMISSION,
    ("GET", "/api/v1/public/slots"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/public/appointments"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/public/appointments/lookup"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/public/appointments/cancel"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/public/callback-requests"): PUBLIC_PERMISSION,
    ("GET", "/book"): PUBLIC_PERMISSION,
    ("GET", "/book/{path:path}"): PUBLIC_PERMISSION,
    # The public demo page: only mounted when demo.enabled (shefa.demo_api).
    ("GET", "/api/v1/public/demo"): PUBLIC_PERMISSION,
    ("POST", "/api/v1/public/demo/chat"): PUBLIC_PERMISSION,
    ("GET", "/demo"): PUBLIC_PERMISSION,
    ("GET", "/demo/{path:path}"): PUBLIC_PERMISSION,
}

from shefa.directory_api import ROUTES as _DIRECTORY_ROUTES  # noqa: E402 - the admin setup screen

ROUTE_PERMISSIONS.update(_DIRECTORY_ROUTES)


# Any telephony route, whatever the provider mounts. Matched by prefix so a new
# webhook cannot escape authorization by living under a different path.
TELEPHONY_PREFIX = "/api/v1/telephony"
TELEPHONY_PERMISSION = "calls:place"

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

# HttpOnly session cookie set by /login. HttpOnly keeps page script from reading
# it; SameSite=Lax keeps it off cross-site requests.
AUTH_COOKIE = "shefa_token"


def required_permission(app: FastAPI, method: str, path: str) -> str | None:
    """The permission a route needs, or None if it is not protected.

    None means "refuse", not "allow": an undeclared route is a route nobody has
    thought about, and failing open on it is how a debug endpoint ends up serving
    transcripts.

    `path` is the concrete request path; the permission map is keyed on the
    route *template* (Starlette uses `/api/v1/sessions/{call_sid}`, not the
    concrete `/api/v1/sessions/SID-1`), so the route's compiled regex is what
    matches here.
    """
    if path.startswith(TELEPHONY_PREFIX):
        return TELEPHONY_PERMISSION
    if path == "/static" or path.startswith("/static/"):
        return "sessions:read"
    if path.startswith(APP_ASSETS_PREFIX + "/"):
        return PUBLIC_PERMISSION  # the app's own script and styles: no data, and needed to sign in
    if path.startswith(("/docs", "/redoc", "/openapi")):
        return "config:read"

    for route in app.routes:
        template = getattr(route, "path", None)
        pattern = getattr(route, "path_regex", None)
        methods = getattr(route, "methods", None) or ()
        if not template or not pattern:
            continue
        if method not in methods:
            continue
        if pattern.match(path):
            return ROUTE_PERMISSIONS.get((method, template))
    return None


def build_auth_store() -> AuthStore:
    """Build the store from config, refusing to start on a broken record.

    A principal whose hash will not parse is a config fault. Letting it through
    would leave an operator staring at a 401 that looks exactly like a wrong
    password, with nothing in the logs to say otherwise.
    """
    auth = settings.auth
    for principal in auth.principals:
        # Parse eagerly so a bad record raises here, not on the first request.
        from shefa.auth import _parse_record

        try:
            _parse_record(principal.token_hash)
        except TokenError as error:
            raise TokenError(
                f"auth principal {principal.name!r} has an unusable token_hash: {error}"
            ) from error
    return AuthStore(
        [
            (principal.name, principal.role, principal.token_hash)
            for principal in auth.principals
        ],
        dict(auth.roles),
    )


def _bearer_token(header: str | None, cookies: dict[str, str] | None = None) -> str | None:
    """Pull a bearer token out of an Authorization header or the auth cookie.

    The header wins because it is the deliberate, per-request credential. The
    cookie exists only so a browser can hold a session: a page load cannot set
    an Authorization header, so without it every HTML route would be a 401 that
    no amount of correct credentials could get past.
    """
    if header:
        scheme, _, credentials = header.partition(" ")
        if scheme.lower() == "bearer":
            token = credentials.strip()
            if token:
                return token
    cookie = (cookies or {}).get(AUTH_COOKIE)
    return cookie or None


def _install_auth(app: FastAPI, store: AuthStore) -> None:
    """Require a valid token and a sufficient role on every request.

    Implemented as middleware rather than per-route dependencies on purpose: a
    dependency is opt-in, and a route added without one is public. Middleware has
    no such hole.
    """

    @app.middleware("http")
    async def enforce_auth(request, call_next):
        permission = required_permission(
            app, request.method, request.url.path
        )

        if permission is None:
            # Undeclared route: refuse rather than guess.
            return error_response("route_not_authorized")

        token = _bearer_token(
            request.headers.get("Authorization"), request.cookies
        )

        if permission == PUBLIC_PERMISSION:
            # Public routes take no credential, but one that is presented is
            # still checked — a wrong token should read as wrong, not silently
            # as anonymous.
            public_principal = (
                store.authenticate(token) if token is not None else None
            )
            if (
                token is not None
                and public_principal is None
                and request.headers.get("Authorization")
            ):
                # A bad header is a client bug and says so. A stale cookie (another server on
                # the same host, an expired session) is just "signed out": the page must still load.
                return error_response(
                    "authentication_required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.principal = public_principal
            return await call_next(request)

        if (
            settings.auth.dev_mode
            and request.url.path.startswith(TELEPHONY_PREFIX)
            and token is None
        ):
            # Dev-mode only. Twilio cannot present a bearer token — it signs
            # webhooks with X-Twilio-Signature instead, which nothing here
            # verifies — so requiring one rejects every inbound call before a
            # stream is ever opened. Unreachable in production because the
            # telephony router itself is only mounted when dev_mode is true
            # (see _telephony_router_allowed).
            request.state.principal = Principal(
                name="twilio-webhook", role="admin"
            )
            return await call_next(request)

        principal: Principal | None = store.authenticate(token)
        if principal is None:
            # One body for "no token" and "wrong token" — a difference between
            # them is an oracle for guessing valid credentials.
            return error_response(
                "authentication_required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not store.authorizes(principal, permission):
            return error_response("insufficient_role")

        request.state.principal = principal
        return await call_next(request)

    if not store.is_configured:
        logger.error(
            "no auth principals configured; every request will be refused. "
            "Run `shefa token mint` and add the result to auth.principals."
        )


def _telephony_router_allowed() -> bool:
    """The telephony router is dev-only and loopback-only.

    Mounting live telephony routes on a routable interface is the plan's
    explicit red line: the webhooks take unauthenticated POSTs, so a public
    mount is an unauthenticated way to inject calls and read transcripts.
    """
    if settings.telephony.provider == TelephonyProvider.ASTERISK:
        return False  # Asterisk connects over AudioSocket; there are no webhooks to mount
    if settings.telephony.provider != TelephonyProvider.TWILIO:
        _provider = settings.telephony.provider
        logger.warning(
            "telephony.provider=%s: no adapter is implemented; the telephony "
            "router stays unmounted. A live trunk on another provider would "
            "silently lose calls until it is wired up.",
            getattr(_provider, "value", _provider),
        )
        return False
    if not settings.auth.dev_mode:
        return False
    return settings.auth.bind_host in LOOPBACK_HOSTS



class LoginBody(BaseModel):
    token: str | None = None
    username: str | None = None
    password: str | None = None


class RingBody(BaseModel):
    message: str = ""
    phone: str = ""


class StatusBody(BaseModel):
    status: str


class WalkInBody(BaseModel):
    doctor_id: int
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(default="", max_length=20)


class StaffBody(BaseModel):
    username: str
    password: str
    role: str
    display_name: str = ""
    doctor_id: int | None = None


class PasswordBody(BaseModel):
    password: str


class ActiveBody(BaseModel):
    active: bool


class ResolveBody(BaseModel):
    note: str = ""


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Listen for Asterisk AudioSocket calls for as long as the server runs."""
    server = None
    if settings.telephony.provider in (TelephonyProvider.ASTERISK, TelephonyProvider.TWILIO):
        from shefa.health import emergency_transfer_status

        if emergency_transfer_status() != "ok":
            logger.error(
                "escalation.on_call_numbers is empty: an emergency call cannot be handed to a "
                "person. Set it before taking real calls."
            )
    if settings.telephony.provider == TelephonyProvider.ASTERISK:
        from shefa.telephony.asterisk import start_audiosocket_server

        server = await start_audiosocket_server()
    warm_task = None
    from shefa import warmup

    if warmup.warmup_enabled():
        import asyncio

        warm_task = asyncio.create_task(warmup.run_forever())
    reminder_task = None
    if settings.reminders.enabled:
        import asyncio

        from shefa.clinic import default_clinic_store
        from shefa.reminders import run_forever

        reminder_task = asyncio.create_task(run_forever(default_clinic_store(), place_call))
    try:
        yield
    finally:
        if reminder_task is not None:
            reminder_task.cancel()
        if warm_task is not None:
            warm_task.cancel()
        if server is not None:
            server.close()
            await server.wait_closed()


def create_app(auth_store: AuthStore | None = None) -> FastAPI:
    """Create and configure the main FastAPI application.

    `auth_store` is injectable so tests can supply their own principals instead
    of depending on whatever the config happens to contain.
    """
    store = auth_store if auth_store is not None else build_auth_store()
    from shefa.store.staff import default_staff_store

    staff = default_staff_store()
    store.staff = staff
    app = FastAPI(
        lifespan=_lifespan,
        title="SHEFA Receptionist",
        version="0.1.0",
        description="Privacy-first open-source bilingual voice AI medical receptionist",
    )
    app.add_exception_handler(HTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)

    _install_auth(app, store)

    if _telephony_router_allowed():
        app.include_router(
            telephony_app.router, prefix=TELEPHONY_PREFIX, tags=["telephony"]
        )
    else:
        logger.warning(
            "telephony router not mounted: requires provider=twilio, "
            "auth.dev_mode=true, and a loopback bind_host"
        )

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    from shefa.public_api import router as public_router

    # Mounted flat (not include_router): the auth middleware finds a route's permission by
    # walking app.routes, and an included router hides its routes from that walk.
    app.router.routes.extend(public_router.routes)
    from shefa.directory_api import router as directory_router

    app.router.routes.extend(directory_router.routes)
    if settings.demo.enabled:
        from shefa.demo_api import router as demo_router

        app.router.routes.extend(demo_router.routes)
    if APP_DIR.is_dir():
        app.mount(
            APP_ASSETS_PREFIX,
            StaticFiles(directory=str(APP_DIR)),
            name="app-assets",
        )


    @app.get("/health")
    async def health() -> dict:
        from shefa.health import health_report

        return await health_report()

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": "SHEFA Receptionist",
            "version": "0.1.0",
            "languages": ",".join(settings.languages.supported),
        }

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        index = STATIC_DIR / "index.html"
        return HTMLResponse(content=index.read_text(encoding="utf-8"))

    @app.get("/test-call", response_class=HTMLResponse)
    async def test_call() -> HTMLResponse:
        page = STATIC_DIR / "test-call.html"
        return HTMLResponse(content=page.read_text(encoding="utf-8"))

    @app.get("/login")
    async def login(token: str | None = None, redirect_to: str = "/test-call"):
        """Exchange a bearer token for an HttpOnly cookie, then redirect.

        A browser cannot attach an Authorization header to a page load, so this
        is the only way the HTML routes are reachable from a browser at all.
        The token is never echoed back into the page or the URL after this
        point — it lives in a cookie the page's JavaScript cannot read.

        The route is public precisely so that it can be reached with no
        credential whatsoever; it still refuses without one, because a session
        is exactly what it is there to issue.
        """
        if not token:
            return error_response(
                "authentication_required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        principal = store.authenticate(token)
        if principal is None:
            return error_response(
                "authentication_required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not store.authorizes(principal, "calls:place"):
            return error_response("insufficient_role")

        # Only local paths: `next=https://evil.example` would turn a legitimate
        # login into an open redirect.
        target = (
            redirect_to
            if redirect_to.startswith("/") and not redirect_to.startswith("//")
            else "/"
        )

        response = RedirectResponse(url=target, status_code=303)
        response.set_cookie(
            AUTH_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            secure=settings.auth.dev_mode is False,
            max_age=12 * 60 * 60,
        )
        return response

    @app.get("/api/v1/sessions")
    async def list_sessions() -> list[dict]:
        sessions = []
        for call_sid, session in session_manager._sessions.items():
            sessions.append({
                "call_sid": call_sid,
                "patient_id": session.patient_id,
                "patient_name": session.patient_name,
                "language": session.language.value,
                "state": session.state,
                "turns": len(session.history),
                "created_at": session.created_at,
                "last_activity": session.last_activity,
            })
        return sessions

    @app.get("/api/v1/sessions/{call_sid}")
    async def get_session(call_sid: str) -> dict:
        session = await session_manager.get(call_sid)
        if not session:
            raise_http_error("session_not_found")
        return session.to_dict()

    @app.post("/api/v1/calls/outbound")
    async def initiate_outbound(to_number: str = "") -> dict:
        if not to_number:
            raise_http_error("required_param", "to_number is required")
        if not outbound_configured():
            raise_http_error("not_configured", "Telephony provider not configured")
        return await place_call(to_number)

    @app.post("/api/v1/calls/call-me")
    async def call_me() -> dict:
        """Outbound call to the operator's own verified number.

        The number is never defaulted: T7 requires a dialable number to come
        only from configuration or the environment, never from source.
        """
        import os

        verified = os.environ.get("VERIFIED_NUMBER") or settings.telephony.twilio.phone_number
        if not verified:
            raise_http_error(
                "verified_number_missing",
                "No verified number configured. Set VERIFIED_NUMBER.",
            )
        if not outbound_configured():
            raise_http_error(
                "not_configured",
                "Telephony provider not configured (Twilio SID or Asterisk ARI password)",
            )
        return await place_call(verified)

    def _audit(request: Request, event: str, call_sid: str | None = None, **details) -> None:
        """Record who touched patient data. Ids and counts only: never names, phones or words."""
        from shefa.utils.compliance import audit_log

        who = getattr(request.state, "principal", None)
        try:
            audit_log(event, call_sid=call_sid, user=who.name if who else None, details=details)
        except Exception:  # noqa: BLE001 - a broken audit must be loud, not break the clinic
            logger.error("audit_write_failed", audit_event=event)

    @app.get("/api/v1/calls")
    async def list_calls(limit: int = 50) -> list[dict]:
        """Recent calls, newest first. Caller phone hashes are not exposed."""
        from shefa.call_log import default_calls_store

        rows = default_calls_store().list_calls()
        rows = [r for r in rows if not r.get("deleted_at")]
        keys = (
            "call_sid", "direction", "status", "disposition", "duration_seconds", "started_at",
            "summary",
        )  # fmt: skip
        return [{k: r.get(k) for k in keys} for r in reversed(rows)][: max(1, min(limit, 500))]

    @app.delete("/api/v1/calls/{call_sid}", response_model=None)
    async def delete_call(call_sid: str, request: Request) -> dict | JSONResponse:
        """Erase what was said on a call. The call row stays, marked deleted, as the audit trail."""
        from shefa.call_log import default_calls_store

        who = getattr(request.state, "principal", None)
        if not default_calls_store().tombstone(call_sid, user=who.name if who else "unknown"):
            return error_response("call_not_found")
        _audit(request, "call_deleted", call_sid=call_sid)
        return {"call_sid": call_sid, "deleted": True}

    @app.get("/api/v1/callbacks")
    async def list_callbacks(request: Request, include_resolved: bool = False) -> list[dict]:
        """People who were promised a person: open ones, oldest first."""
        from shefa.call_log import default_calls_store

        rows = default_calls_store().list_callbacks(open_only=not include_resolved)
        _audit(request, "callbacks_listed", count=len(rows))
        return rows

    @app.post("/api/v1/callbacks/{callback_id}/resolve", response_model=None)
    async def resolve_callback(
        callback_id: int, request: Request, body: ResolveBody | None = None
    ) -> dict | JSONResponse:
        from shefa.call_log import default_calls_store

        who = getattr(request.state, "principal", None)
        done = default_calls_store().resolve_callback(
            callback_id, user=who.name if who else "unknown", note=(body.note if body else "")
        )
        if not done:
            return error_response("callback_not_found")
        _audit(request, "callback_resolved", callback_id=callback_id)
        return {"id": callback_id, "resolved": True}

    def _own_doctor(request: Request) -> int:
        who = getattr(request.state, "principal", None)
        if who is None or who.doctor_id is None:
            raise HTTPException(
                status_code=403, detail={"code": "insufficient_role", "message": "Not a doctor"}
            )
        return who.doctor_id

    @app.get("/api/v1/me/doctor")
    async def my_doctor(request: Request) -> dict:
        """The signed-in doctor's own card."""
        from shefa.clinic import default_clinic_store
        from shefa.integrations.ehr import _doctor_card

        doctor_id = _own_doctor(request)
        for doc in default_clinic_store().doctors():
            if doc["id"] == doctor_id:
                return _doctor_card(doc)
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "No doctor"})

    @app.get("/api/v1/me/day")
    async def my_day(request: Request, date: str = "") -> list[dict]:
        """The signed-in doctor's own appointments for a day, and nobody else's."""
        from datetime import datetime

        from shefa.clinic import default_clinic_store
        from shefa.clinic.store import CLINIC_TZ

        doctor_id = _own_doctor(request)
        day = date or datetime.now(CLINIC_TZ).date().isoformat()
        _audit(request, "doctor_day_viewed", doctor_id=doctor_id, date=day)
        return [
            {
                "appointment_id": a["appointment_id"],
                "date": a["date"],
                "start_time": a["start_time"],
                "patient_name": a["patient_name"],
                "reason": a.get("reason", ""),
                "status": a["status"],
            }
            for a in default_clinic_store().appointments_on(day, status=None)
            if a["doctor_id"] == doctor_id
        ]

    @app.post("/api/v1/me/appointments/{appointment_id}/status")
    async def my_appointment_status(
        appointment_id: str, body: StatusBody, request: Request
    ) -> dict:
        """A doctor marks their own patient seen or absent; anyone else's is refused."""
        from shefa.clinic import ClinicError, default_clinic_store

        doctor_id = _own_doctor(request)
        clinic = default_clinic_store()
        try:
            if clinic.get_appointment(appointment_id)["doctor_id"] != doctor_id:
                raise HTTPException(
                    status_code=403,
                    detail={"code": "insufficient_role", "message": "Not your patient"},
                )
            updated = clinic.mark_status(appointment_id, body.status)
        except ClinicError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "validation", "message": str(exc)}
            ) from exc
        _audit(
            request,
            "appointment_status_changed",
            appointment_id=updated["appointment_id"],
            status=updated["status"],
            by="doctor",
        )
        return {"appointment_id": updated["appointment_id"], "status": updated["status"]}

    @app.get("/api/v1/overview")
    async def overview(days: int = 7) -> dict:
        """What the owner asks first: is it working? Counts over the last `days` days."""
        import time as _time
        from datetime import datetime

        from shefa.call_log import default_calls_store
        from shefa.clinic import default_clinic_store
        from shefa.clinic.store import CLINIC_TZ

        days = max(1, min(days, 90))
        since = _time.time() - days * 86400
        calls = default_calls_store().stats_since(since)
        clinic = default_clinic_store()
        booked = clinic.connection.execute(
            "SELECT COUNT(*) FROM appointments WHERE created_at >= ? AND source != 'staff'",
            (since,),
        ).fetchone()[0]
        reminders = clinic.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(done), 0) FROM reminders WHERE last_attempt >= ?",
            (since,),
        ).fetchone()
        return {
            "days": days,
            "calls": calls,
            "booked_by_agent": booked,
            "unconfirmed_web_bookings": clinic.connection.execute(
                "SELECT COUNT(*) FROM appointments WHERE source = 'web' AND confirmed = 0"
                " AND status = 'booked' AND date >= ?",
                (datetime.now(CLINIC_TZ).date().isoformat(),),
            ).fetchone()[0],
            "open_callbacks": len(default_calls_store().list_callbacks()),
            "reminders": {"attempted": reminders[0], "completed": int(reminders[1])},
        }

    @app.get("/api/v1/report")
    async def owner_report(days: int = 7, end: str = "") -> dict:
        """The weekly 'what SHEFA did for you' report (shefa/report.py)."""
        from datetime import date as _date

        from shefa.call_log import default_calls_store
        from shefa.clinic import default_clinic_store
        from shefa.report import weekly_report

        try:
            last = _date.fromisoformat(end) if end else None
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "validation", "message": "end must be YYYY-MM-DD"}
            ) from exc
        return weekly_report(default_clinic_store(), default_calls_store(), end=last, days=days)

    @app.get("/api/v1/appointments")
    async def list_appointments(
        request: Request, date: str = "", status: str = "booked"
    ) -> list[dict]:
        """Booked appointments for a day (default: today, clinic time), phones masked."""
        from datetime import datetime

        from shefa.call_log import mask_phone
        from shefa.clinic import default_clinic_store
        from shefa.clinic.store import CLINIC_TZ

        day = date or datetime.now(CLINIC_TZ).date().isoformat()
        rows = default_clinic_store().appointments_on(
            day, status=None if status == "all" else status
        )
        _audit(request, "appointments_listed", date=day, count=len(rows))
        return [
            {
                "appointment_id": a["appointment_id"],
                "date": a["date"],
                "start_time": a["start_time"],
                "doctor": a["doctor_en"],
                "doctor_bn": a.get("doctor_bn") or "",
                "doctor_id": a["doctor_id"],
                "serial_no": a.get("serial_no"),
                "patient_name": a["patient_name"],
                "phone": mask_phone(a["phone"]) if not a["phone"].startswith("W") else "",
                "status": a["status"],
                "source": a.get("source", "phone"),
                "confirmed": bool(a.get("confirmed", 1)),
            }
            for a in rows
        ]

    @app.post("/api/v1/appointments/walk-in")
    async def add_walk_in(body: WalkInBody, request: Request) -> dict:
        """Someone at the desk: the next free serial (or time) from now, through the same
        booking path as phone and web, so SHEFA never offers that place again."""
        import time as _clock
        from datetime import datetime

        from shefa.clinic import ClinicError, default_clinic_store
        from shefa.clinic.store import CLINIC_TZ, normalize_phone

        clinic = default_clinic_store()
        doctor = clinic.doctor(body.doctor_id)
        if doctor is None or not doctor["active"]:
            raise HTTPException(
                status_code=404, detail={"code": "validation", "message": "Unknown doctor"}
            )
        now = datetime.now(CLINIC_TZ)
        day = now.date().isoformat()
        slots = clinic.available_slots(body.doctor_id, day, now=now)
        if not slots:
            raise HTTPException(
                status_code=409,
                detail={"code": "full", "message": "No free place left today for this doctor"},
            )
        phone = normalize_phone(body.phone) if body.phone.strip() else ""
        # Someone without a phone still needs a patient row: a walk-in marker, never texted.
        patient = clinic.upsert_patient(phone or f"W{int(_clock.time() * 1000)}", body.name.strip())
        try:
            booked = clinic.book(
                patient, body.doctor_id, day, slots[0]["time"], source="walkin", confirmed=True,
                now=now,
            )
        except ClinicError as exc:
            raise HTTPException(
                status_code=409, detail={"code": "slot_taken", "message": str(exc)}
            ) from exc
        _audit(request, "walk_in_added", appointment_id=booked["appointment_id"])
        return {
            "appointment_id": booked["appointment_id"],
            "serial_no": booked.get("serial_no"),
            "start_time": booked["start_time"],
            "doctor": booked["doctor_en"],
        }

    @app.get("/console", response_class=HTMLResponse)
    async def console(request: Request) -> HTMLResponse:
        """The staff console. Signed out, it is a 401 carrying the sign-in form."""
        signed_in = getattr(request.state, "principal", None) is not None
        page = "console.html" if signed_in else "signin.html"
        return HTMLResponse(
            content=(STATIC_DIR / page).read_text(encoding="utf-8"),
            status_code=200 if signed_in else 401,
        )

    @app.get("/app", response_class=HTMLResponse)
    @app.get("/app/{path:path}", response_class=HTMLResponse)
    async def staff_app(request: Request, path: str = "") -> HTMLResponse:
        """The staff app. Signed out it is a 401 that carries the app, which shows its own
        sign-in form (like /console); the page holds no data, its API calls are protected."""
        index = APP_DIR / "index.html"
        if not index.is_file():
            return HTMLResponse(
                "<h1>The staff app is not built</h1><p>Run <code>npm install && npm run build"
                "</code> in <code>frontend/</code>, or use <a href='/console'>/console</a>.</p>",
                status_code=503,
            )
        signed_in = getattr(request.state, "principal", None) is not None
        return HTMLResponse(
            index.read_text(encoding="utf-8"), status_code=200 if signed_in else 401
        )

    @app.get("/api/v1/me", response_model=None)
    async def me(request: Request) -> dict | JSONResponse:
        """Who is signed in. Signed out is an answer, not an error: the app asks on load."""
        principal = getattr(request.state, "principal", None)
        if principal is None:
            return JSONResponse({"signed_in": False}, status_code=401)
        return {
            "signed_in": True,
            "name": principal.display_name or principal.name,
            "role": principal.role,
            "doctor_id": principal.doctor_id,
            "permissions": sorted(store.permissions_for(principal.role)),
        }

    @app.post("/api/v1/logout")
    async def logout(request: Request) -> JSONResponse:
        cookie = request.cookies.get(AUTH_COOKIE)
        if cookie:
            staff.sign_out(cookie)
        signed_in = getattr(request.state, "principal", None) is not None
        response = JSONResponse({"signed_in": False}, status_code=200 if signed_in else 401)
        response.delete_cookie(AUTH_COOKIE)
        return response

    @app.post("/api/v1/login")
    async def api_login(request: Request, body: LoginBody | None = None) -> JSONResponse:
        from shefa.utils.compliance import audit_log

        secret = body.token if body else None
        if body and body.username and body.password:
            secret = staff.sign_in(body.username, body.password)
        principal = store.authenticate(secret)
        client = request.client.host if request.client else "unknown"
        if principal is None:
            audit_log(
                "staff_sign_in_failed",
                user=(body.username if body and body.username else None),
                details={"client": client},
            )
            return error_response("authentication_required")
        audit_log("staff_signed_in", user=principal.name, details={"client": client})
        response = JSONResponse({"name": principal.name, "role": principal.role})
        response.set_cookie(
            AUTH_COOKIE,
            secret or "",
            httponly=True,
            samesite="lax",
            secure=settings.auth.dev_mode is False,
            max_age=12 * 60 * 60,
        )
        return response

    @app.websocket("/ws/call")
    async def ws_call(websocket: WebSocket, uuid: str = "", phone: str = "") -> None:
        """Talk to the agent from the browser. Same permission as placing a call."""
        token = _bearer_token(websocket.headers.get("authorization"), dict(websocket.cookies))
        principal = store.authenticate(token)
        if not store.authorizes(principal, "calls:place"):
            await websocket.close(code=4401)
            return
        import uuid as uuid_module

        from shefa.telephony.browser import handle_browser_call

        await handle_browser_call(websocket, uuid or str(uuid_module.uuid4()), phone)

    @app.post("/api/v1/calls/ring")
    async def ring_console(body: RingBody) -> dict:
        """Make the agent call the console, opening with `message` (or a default line)."""
        from shefa.telephony.browser import start_test_ring

        message = body.message or (
            "আসসালামু আলাইকুম, শেফা ক্লিনিক থেকে বলছি। এটি একটি পরীক্ষামূলক কল। "
            "আমি কীভাবে সাহায্য করতে পারি?"
            if settings.languages.primary == "bn"
            else "Hello, this is SHEFA clinic calling to test the line. How can I help?"
        )
        return {"call_uuid": start_test_ring(message, body.phone)}

    @app.get("/api/v1/calls/ringing")
    async def calls_ringing() -> list[dict]:
        from shefa.telephony.browser import ringing_now

        return ringing_now()

    @app.get("/api/v1/calls/{call_sid}", response_model=None)
    async def call_detail(call_sid: str, request: Request) -> dict | JSONResponse:
        """One call with every turn: heard, how sure, what the agent did, what it said."""
        from shefa.call_log import default_calls_store

        calls = default_calls_store()
        row = calls.get_call(call_sid)
        if row is None or row.get("deleted_at"):
            return error_response("call_not_found")
        keys = (
            "call_sid", "direction", "status", "disposition", "duration_seconds", "started_at",
            "summary",
        )  # fmt: skip
        _audit(request, "transcript_viewed", call_sid=call_sid)
        earlier = (
            calls.previous_calls(row["patient_id"], limit=3, before=row.get("started_at"))
            if row.get("patient_id") and row.get("started_at")
            else []
        )
        return {
            **{k: row.get(k) for k in keys},
            "turns": calls.turns_for(call_sid),
            "earlier_calls": earlier,
        }

    @app.post("/api/v1/calls/ringing/{call_uuid}/decline")
    async def decline_ring(call_uuid: str) -> dict:
        from shefa.telephony.browser import decline
        from shefa.telephony.call_context import discard_context

        discard_context(call_uuid)
        return {"declined": decline(call_uuid)}

    @app.get("/api/v1/directory")
    async def directory() -> list[dict]:
        """Departments with their doctors, weekly schedules and next free slot."""
        from shefa.clinic import default_clinic_store
        from shefa.integrations.ehr import _doctor_card

        clinic = default_clinic_store()
        return [
            {
                "name": d["name_en"],
                "name_bn": d["name_bn"],
                "doctors": [_doctor_card(doc) for doc in clinic.doctors(department_id=d["id"])],
            }
            for d in clinic.departments()
        ]

    @app.post("/api/v1/appointments/{appointment_id}/status")
    async def set_appointment_status(
        appointment_id: str, body: StatusBody, request: Request
    ) -> dict:
        from shefa.clinic import ClinicError, default_clinic_store

        try:
            updated = default_clinic_store().mark_status(appointment_id, body.status)
        except ClinicError as exc:
            raise HTTPException(
                status_code=422, detail={"code": "validation", "message": str(exc)}
            ) from exc
        _audit(
            request,
            "appointment_status_changed",
            appointment_id=updated["appointment_id"],
            status=updated["status"],
            by="desk",
        )
        return {"appointment_id": updated["appointment_id"], "status": updated["status"]}

    @app.get("/api/v1/staff")
    async def list_staff() -> list[dict]:
        """The clinic's staff accounts (never their passwords or sessions)."""
        return staff.users()

    @app.get("/api/v1/staff/doctors")
    async def staff_doctor_choices() -> list[dict]:
        """Doctors a doctor account can be tied to (id and names only)."""
        from shefa.clinic import default_clinic_store

        return [
            {"id": d["id"], "name": d["name_en"], "name_bn": d["name_bn"]}
            for d in default_clinic_store().doctors()
        ]

    @app.post("/api/v1/staff", response_model=None)
    async def add_staff(body: StaffBody, request: Request) -> dict | JSONResponse:
        from shefa.store.staff import StaffError

        try:
            staff.add_user(
                body.username,
                body.password,
                body.role,
                display_name=body.display_name,
                doctor_id=body.doctor_id,
            )
        except StaffError as exc:
            return error_response("validation", str(exc))
        _audit(request, "staff_created", username=body.username.strip(), role=body.role)
        return {"username": body.username.strip(), "role": body.role}

    @app.post("/api/v1/staff/{username}/password", response_model=None)
    async def reset_staff_password(
        username: str, body: PasswordBody, request: Request
    ) -> dict | JSONResponse:
        from shefa.auth import TokenError
        from shefa.store.staff import StaffError

        try:
            staff.set_password(username, body.password)
        except (StaffError, TokenError) as exc:
            return error_response("validation", str(exc))
        _audit(request, "staff_password_reset", username=username)
        return {"username": username, "password_changed": True}

    @app.post("/api/v1/staff/{username}/active", response_model=None)
    async def set_staff_active(
        username: str, body: ActiveBody, request: Request
    ) -> dict | JSONResponse:
        from shefa.store.staff import StaffError

        who = getattr(request.state, "principal", None)
        if not body.active:
            if who is not None and who.name == username:
                return error_response("validation", "You cannot disable your own account.")
            others = [
                u
                for u in staff.users()
                if u["role"] == "owner" and u["active"] and u["username"] != username
            ]
            target = next((u for u in staff.users() if u["username"] == username), None)
            if target and target["role"] == "owner" and not others:
                return error_response("validation", "Keep at least one active owner account.")
        try:
            staff.set_active(username, body.active)
        except StaffError as exc:
            return error_response("validation", str(exc))
        _audit(request, "staff_enabled" if body.active else "staff_disabled", username=username)
        return {"username": username, "active": body.active}

    @app.get("/api/v1/export/appointments", response_model=None)
    async def export_appointments(
        request: Request,
        start: str = "",
        end: str = "",
        updated_since: float = 0.0,
        format: str = "json",  # noqa: A002 - the query parameter is part of the public contract
    ) -> JSONResponse | Response:
        """Appointments with full patient details, for a hospital system to import.

        Needs ``records:export`` (the owner role, or a token you mint for the integration). Every
        call is written to the audit trail. ``updated_since`` (a Unix time) makes it incremental:
        poll with the largest ``updated_at`` you have seen.
        """
        from datetime import date as _date
        from datetime import datetime, timedelta

        from shefa.clinic import default_clinic_store
        from shefa.clinic.store import CLINIC_TZ
        from shefa.export import EXPORT_FIELDS, appointments_csv, export_row

        today = datetime.now(CLINIC_TZ).date()
        try:
            first = _date.fromisoformat(start) if start else today
            last = _date.fromisoformat(end) if end else first + timedelta(days=30)
        except ValueError:
            return error_response("validation", "start and end must be dates like 2026-11-09.")
        if last < first or (last - first).days > MAX_EXPORT_DAYS:
            return error_response(
                "validation", f"Ask for at most {MAX_EXPORT_DAYS} days, start before end."
            )
        if format not in {"json", "csv"}:
            return error_response("validation", "format must be json or csv.")
        rows = [
            export_row(a)
            for a in default_clinic_store().appointments_between(
                first.isoformat(), last.isoformat(), updated_since=updated_since
            )
        ]
        _audit(
            request,
            "appointments_exported",
            start=first.isoformat(),
            end=last.isoformat(),
            count=len(rows),
            format=format,
        )
        if format == "csv":
            return Response(
                appointments_csv(rows),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="appointments.csv"'},
            )
        return JSONResponse({"fields": list(EXPORT_FIELDS), "appointments": rows})

    @app.post("/api/v1/appointments/{appointment_id}/confirm")
    async def confirm_appointment(appointment_id: str, request: Request) -> dict:
        """The desk has checked a web booking with the patient."""
        from shefa.clinic import ClinicError, default_clinic_store

        try:
            updated = default_clinic_store().confirm(appointment_id)
        except ClinicError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "validation", "message": str(exc)}
            ) from exc
        _audit(request, "appointment_confirmed", appointment_id=updated["appointment_id"])
        sms: dict[str, Any] | None = None
        if settings.integrations.notifications.sms.send_on_confirm:
            # The patient hears from the clinic once a person has checked the booking. A
            # sending problem never undoes the confirmation; the desk sees what happened.
            from shefa.integrations.notifications import send_booking_sms

            sms = await asyncio.to_thread(send_booking_sms, updated["appointment_id"])
        return {"appointment_id": updated["appointment_id"], "confirmed": True, "sms": sms}

    @app.post("/api/v1/reminders/run")
    async def run_reminders_now() -> dict:
        """Place every reminder/follow-up call that is due right now."""
        from datetime import datetime

        from shefa.clinic import default_clinic_store
        from shefa.clinic.store import CLINIC_TZ
        from shefa.reminders import run_reminder_cycle

        cfg = settings.reminders
        placed = await run_reminder_cycle(
            default_clinic_store(),
            place_call,
            datetime.now(CLINIC_TZ),
            language=cfg.language,
            kinds=tuple(cfg.kinds),
            quiet_start=cfg.quiet_start,
            quiet_end=cfg.quiet_end,
        )
        return {"placed": len(placed), "calls": placed}

    @app.post("/api/v1/chat")
    async def text_chat(message: str = "", call_sid: str = "text-chat", phone: str = "") -> dict:
        """A typed conversation with the agent: the same router, tools, templates and
        emergency handoff as a call, without audio. `phone` identifies the patient on the
        chat's first message, as the console's call does."""
        if not message.strip():
            raise_http_error("required_param", "message is required")
        try:
            turn = await text_pipeline().handle_text(call_sid, message.strip(), phone.strip())
        except Exception as error:  # noqa: BLE001 - one envelope for any model fault
            logger.warning("chat_reply_failed", error=type(error).__name__, detail=str(error))
            raise_http_error(
                "model_unavailable",
                f"The language model did not answer ({type(error).__name__}). "
                "Check it with: shefa doctor",
            )
        return {**turn, "session_id": call_sid}

    @app.get("/api/v1/config")
    async def get_config() -> dict:
        return {
            "pipeline": {
                "stt": {
                    "provider": settings.pipeline.stt.provider,
                    "model": settings.pipeline.stt.model,
                },
                "tts": {
                    "provider": settings.pipeline.tts.provider,
                    "model": settings.pipeline.tts.model,
                },
                "llm": {
                    "provider": settings.pipeline.llm.provider,
                    "model": settings.pipeline.llm.model,
                },
            },
            "languages": {
                "primary": settings.languages.primary,
                "supported": settings.languages.supported,
                "code_switching": settings.languages.code_switching,
            },
            "session": {
                "backend": settings.session.backend,
                "ttl_seconds": settings.session.ttl_seconds,
            },
            "compliance": {
                "hipaa_enabled": settings.compliance.hipaa_enabled,
                "audit_log_enabled": settings.compliance.audit_log_enabled,
            },
        }

    @app.get("/api/v1/tools")
    async def list_tools() -> list[dict]:
        tools = get_tool_definitions()
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in tools
        ]

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "shefa.main:app",
        # Loopback by default: a TTS/HIPAA box reachable on every interface is
        # the failure this whole task exists to prevent.
        host=settings.auth.bind_host,
        port=8000,
        reload=settings.monitoring.logging.level == "DEBUG",
    )
