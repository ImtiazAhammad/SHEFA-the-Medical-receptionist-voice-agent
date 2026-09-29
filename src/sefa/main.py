"""sefa Receptionist - Main application entry point."""

from __future__ import annotations

from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sefa.auth import AuthStore, Principal, TokenError
from sefa.config.settings import settings
from sefa.session.manager import SessionManager
from sefa.telephony.twilio import app as telephony_app
from sefa.tools.definitions import get_tool_definitions
from sefa.utils.logging import setup_logging

# The configured structlog pipeline is the ONLY server logger. Its PHI
# masking lives behind `monitoring.logging.phi_masking`, so every event in
# the process shares the same gate — no parallel renderer can unmask a
# number that this one already redacted.
setup_logging(
    level=settings.monitoring.logging.level,
    phi_masking=settings.monitoring.logging.phi_masking,
)

logger = structlog.get_logger("sefa")

session_manager = SessionManager()

STATIC_DIR = Path(__file__).parent / "static"

# The permission each route requires, keyed by (method, path).
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
}

# Any telephony route, whatever the provider mounts. Matched by prefix so a new
# webhook cannot escape authorization by living under a different path.
TELEPHONY_PREFIX = "/api/v1/telephony"
TELEPHONY_PERMISSION = "calls:place"

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


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
        from sefa.auth import _parse_record

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


def _bearer_token(header: str | None) -> str | None:
    """Pull a bearer token out of an Authorization header, or None."""
    if not header:
        return None
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = credentials.strip()
    return token or None


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
            return JSONResponse(
                status_code=403,
                content={"error": "This route is not authorized."},
            )

        principal: Principal | None = store.authenticate(
            _bearer_token(request.headers.get("Authorization"))
        )
        if principal is None:
            # One body for "no token" and "wrong token" — a difference between
            # them is an oracle for guessing valid credentials.
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not store.authorizes(principal, permission):
            return JSONResponse(
                status_code=403,
                content={"error": "Insufficient role for this resource."},
            )

        request.state.principal = principal
        return await call_next(request)

    if not store.is_configured:
        logger.error(
            "no auth principals configured; every request will be refused. "
            "Run `sefa token mint` and add the result to auth.principals."
        )


def _telephony_router_allowed() -> bool:
    """The telephony router is dev-only and loopback-only.

    Mounting live telephony routes on a routable interface is the plan's
    explicit red line: the webhooks take unauthenticated POSTs, so a public
    mount is an unauthenticated way to inject calls and read transcripts.
    """
    if settings.telephony.provider != "twilio":
        return False
    if not settings.auth.dev_mode:
        return False
    return settings.auth.bind_host in LOOPBACK_HOSTS



def create_app(auth_store: AuthStore | None = None) -> FastAPI:
    """Create and configure the main FastAPI application.

    `auth_store` is injectable so tests can supply their own principals instead
    of depending on whatever the config happens to contain.
    """
    store = auth_store if auth_store is not None else build_auth_store()
    app = FastAPI(
        title="sefa Receptionist",
        version="0.1.0",
        description="HIPAA-compliant bilingual voice AI medical receptionist",
    )

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


    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "version": "0.1.0"}

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": "sefa Receptionist",
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
            return {"error": "Session not found"}
        return session.to_dict()

    @app.post("/api/v1/calls/outbound")
    async def initiate_outbound(to_number: str = "") -> dict:
        if not to_number:
            return {"error": "to_number is required"}
        sid = settings.telephony.twilio.account_sid
        if not sid:
            return {"error": "Twilio not configured"}
        from sefa.telephony.twilio import initiate_outbound_call as _call
        return await _call(to_number)

    @app.post("/api/v1/calls/call-me")
    async def call_me() -> dict:
        """Outbound call to the operator's own verified number.

        The number is never defaulted: T7 requires a dialable number to come
        only from configuration or the environment, never from source.
        """
        import os

        verified = os.environ.get("VERIFIED_NUMBER") or settings.telephony.twilio.phone_number
        if not verified:
            return {"error": "No verified number configured. Set VERIFIED_NUMBER."}
        sid = settings.telephony.twilio.account_sid
        if not sid:
            return {"error": "Twilio not configured. Set TWILIO_ACCOUNT_SID in .env"}
        from sefa.telephony.twilio import initiate_outbound_call as _call

        return await _call(verified)

    @app.post("/api/v1/chat")
    async def text_chat(message: str = "", call_sid: str = "text-chat") -> dict:
        """Text-only chat endpoint — no voice, just text in/out. Free to test."""
        if not message:
            return {"error": "message is required"}
        session = await session_manager.get_or_create(call_sid)
        session.add_turn("user", message)
        from sefa.models.registry import registry
        from sefa.pipeline.voice_pipeline import SYSTEM_PROMPT_TEMPLATE
        from sefa.tools.definitions import get_tool_definitions
        system = SYSTEM_PROMPT_TEMPLATE.format(
            language=session.language.value,
            patient_name=session.patient_name or "Unknown",
        )
        messages = [{"role": "system", "content": system}]
        for turn in session.history:
            messages.append({"role": turn.role, "content": turn.content})
        llm = await registry.get_llm()
        llm_result = await llm.generate(messages, tools=get_tool_definitions())
        session.add_turn("assistant", llm_result.text, llm_result.language)
        await session_manager.save(session)
        return {
            "reply": llm_result.text,
            "language": llm_result.language.value,
            "session_id": call_sid,
        }

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
        "sefa.main:app",
        # Loopback by default: a TTS/HIPAA box reachable on every interface is
        # the failure this whole task exists to prevent.
        host=settings.auth.bind_host,
        port=8000,
        reload=settings.monitoring.logging.level == "DEBUG",
    )
