"""sefa Receptionist - Main application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from sefa.config.settings import settings
from sefa.session.manager import SessionManager
from sefa.telephony.twilio import app as telephony_app
from sefa.tools.definitions import get_tool_definitions

logging.basicConfig(
    level=getattr(logging, settings.monitoring.logging.level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sefa")

session_manager = SessionManager()

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure the main FastAPI application."""
    app = FastAPI(
        title="sefa Receptionist",
        version="0.1.0",
        description="HIPAA-compliant bilingual voice AI medical receptionist",
    )

    app.include_router(telephony_app.router, prefix="/api/v1/telephony", tags=["telephony"])

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
        host="0.0.0.0",
        port=8000,
        reload=settings.monitoring.logging.level == "DEBUG",
    )
