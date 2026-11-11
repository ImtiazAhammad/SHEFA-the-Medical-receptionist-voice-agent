"""The public demo page: talk (or type) to SHEFA with no sign-in, on a sample clinic.

Mounted only when ``demo.enabled`` is true. It exists so a hospital executive can try the agent
in a minute from a link. The limits are the whole security story, so they are strict: calls are
short, few at a time, rate-limited per address, same-origin only, and a typed chat is capped.
Run it on a separate server loaded with the sample clinic: bookings made here are real rows in
that server's database.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from shefa.booking import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter()
_limiter = RateLimiter()
_live: set[str] = set()
_chat_counts: dict[str, int] = {}
_SESSION = re.compile(r"^[a-z0-9-]{8,40}$")
CLOSE_TOO_LONG = 4408
CLOSE_BUSY = 4429
CLOSE_FORBIDDEN = 4403
TIME_SCALE = 1.0  # tests shrink call length; production leaves it at 1


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=400)
    session: str = Field(max_length=40)


def _address(connection: Request | WebSocket) -> str:
    from shefa.config.settings import settings

    if settings.booking.trust_forwarded_for:
        forwarded = connection.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return connection.client.host if connection.client else "unknown"


def _same_origin(websocket: WebSocket) -> bool:
    """A browser page on another site must not be able to open calls on our GPU."""
    origin = websocket.headers.get("origin", "")
    host = websocket.headers.get("host", "")
    return bool(origin) and origin.split("://", 1)[-1].split("/", 1)[0] == host


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@router.get("/api/v1/public/demo", response_model=None)
async def demo_info() -> dict[str, Any]:
    from shefa.config.settings import settings

    return {
        "enabled": True,
        "max_call_seconds": settings.demo.max_call_seconds,
        "busy": len(_live) >= settings.demo.max_concurrent_calls,
    }


@router.post("/api/v1/public/demo/chat", response_model=None)
async def demo_chat(request: Request, body: ChatBody) -> Any:
    from shefa.config.settings import settings
    from shefa.main import text_pipeline

    cfg = settings.demo
    if not _SESSION.match(body.session):
        return _error("bad_session", "Reload the page to start a new chat.", 400)
    if not _limiter.allow(f"chat:{_address(request)}", cfg.chat_messages_per_ip_per_minute, 60):
        return _error("rate_limited", "Too many messages. Please wait a moment.", 429)
    count = _chat_counts.get(body.session, 0)
    if count >= cfg.max_messages_per_chat:
        return _error("chat_limit", "This demo chat is full. Reload to start again.", 429)
    if len(_chat_counts) > 5000:
        _chat_counts.clear()
    _chat_counts[body.session] = count + 1
    try:
        turn = await text_pipeline().handle_text(f"demo-{body.session}", body.message.strip(), "")
    except Exception as error:  # noqa: BLE001 - one envelope for any model fault
        logger.warning("demo_chat_failed: %s", type(error).__name__)
        return _error("model_unavailable", "The assistant is not available right now.", 503)
    return {"reply": turn.get("reply", ""), "state": turn.get("state")}


@router.websocket("/ws/demo-call")
async def demo_call(websocket: WebSocket) -> None:
    from shefa.config.settings import settings
    from shefa.telephony.browser import handle_browser_call

    cfg = settings.demo
    if not _same_origin(websocket):
        await websocket.close(code=CLOSE_FORBIDDEN)
        return
    if not _limiter.allow(f"call:{_address(websocket)}", cfg.calls_per_ip_per_hour, 3600):
        await websocket.close(code=CLOSE_BUSY)
        return
    call_id = f"demo-{uuid.uuid4()}"
    if len(_live) >= cfg.max_concurrent_calls:
        await websocket.close(code=CLOSE_BUSY)
        return
    _live.add(call_id)
    try:
        await asyncio.wait_for(
            handle_browser_call(websocket, call_id, ""), cfg.max_call_seconds * TIME_SCALE
        )
    except TimeoutError:
        with_close = websocket.application_state.name == "CONNECTED"
        if with_close:
            await websocket.close(code=CLOSE_TOO_LONG)
    finally:
        _live.discard(call_id)


@router.get("/demo", response_class=HTMLResponse)
@router.get("/demo/{path:path}", response_class=HTMLResponse)
async def demo_page(path: str = "") -> HTMLResponse:
    from shefa.main import APP_DIR

    index = APP_DIR / "index.html"
    if not index.is_file():
        return HTMLResponse("<h1>The demo page is not built</h1>", status_code=503)
    return HTMLResponse(index.read_text(encoding="utf-8"))
