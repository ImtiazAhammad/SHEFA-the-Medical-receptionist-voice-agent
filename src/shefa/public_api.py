"""Routes of the public patient booking page (`/book` and `/api/v1/public/*`).

These are the only routes a stranger can reach that read or write clinic data. All of
the rules (limits, validation, what may be shown) live in `shefa.booking`; this file only
turns HTTP into calls to it and errors into the shared error envelope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from shefa.booking import BookingError, PublicBooking, RateLimiter, clean_name, clean_phone

if TYPE_CHECKING:
    from collections.abc import Callable

router = APIRouter()
_limiter = RateLimiter()


class BookBody(BaseModel):
    doctor_id: int
    date: str = Field(max_length=10)
    time: str = Field(max_length=5)
    name: str = Field(max_length=120)
    phone: str = Field(max_length=32)
    reason: str = Field(default="", max_length=400)
    confirm_by_call: bool = False
    website: str = Field(default="", max_length=200)  # honeypot: people never see this field


class ReferenceBody(BaseModel):
    reference: str = Field(max_length=32)
    phone: str = Field(max_length=32)


class CallbackBody(BaseModel):
    name: str = Field(max_length=120)
    phone: str = Field(max_length=32)
    reason: str = Field(default="", max_length=400)
    language: str = Field(default="bn", max_length=8)
    website: str = Field(default="", max_length=200)


def _client(request: Request) -> str:
    from shefa.config.settings import settings

    if settings.booking.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()  # the address our own proxy saw
    return request.client.host if request.client else "unknown"


def _service() -> PublicBooking:
    from shefa.clinic import default_clinic_store
    from shefa.config.settings import settings

    if not settings.booking.enabled:
        raise BookingError("booking_closed", "Online booking is not available.", 404)
    return PublicBooking(default_clinic_store(), settings.booking, _limiter)


def _guarded(action: Callable[[], Any]) -> Any:
    from shefa.main import error_response

    try:
        return action()
    except BookingError as exc:
        headers = {"Retry-After": "60"} if exc.status == 429 else None
        return error_response(exc.code, exc.message, headers=headers)


@router.get("/api/v1/public/clinic", response_model=None)
async def public_clinic(request: Request) -> Any:
    def go() -> dict:
        service = _service()
        service.check_read(_client(request))
        return service.overview()

    return _guarded(go)


@router.get("/api/v1/public/slots", response_model=None)
async def public_slots(request: Request, doctor_id: int) -> Any:
    def go() -> list:
        service = _service()
        service.check_read(_client(request))
        return service.slots(doctor_id)

    return _guarded(go)


@router.post("/api/v1/public/appointments", response_model=None)
async def public_book(request: Request, body: BookBody) -> Any:
    def go() -> JSONResponse:
        service = _service()
        client = _client(request)
        service.check_write(client)
        phone = clean_phone(body.phone)
        clean_name(body.name)
        service.check_phone(phone)
        if body.website.strip():
            # A bot filled the hidden field: look like success, change nothing.
            return JSONResponse({"reference": "APT-0000", "status": "booked"}, status_code=201)
        receipt = service.book(
            doctor_id=body.doctor_id,
            day=body.date,
            start_time=body.time,
            name=body.name,
            phone=phone,
            reason=body.reason,
        )
        if body.confirm_by_call and service.config.callback_enabled:
            _queue_callback(
                phone, "bn", f"Confirm web booking {receipt['reference']} ({body.name})"
            )
        return JSONResponse(receipt, status_code=201)

    return _guarded(go)


@router.post("/api/v1/public/appointments/lookup", response_model=None)
async def public_lookup(request: Request, body: ReferenceBody) -> Any:
    def go() -> dict:
        service = _service()
        service.check_write(_client(request))
        return service.lookup(body.reference, body.phone)

    return _guarded(go)


@router.post("/api/v1/public/appointments/cancel", response_model=None)
async def public_cancel(request: Request, body: ReferenceBody) -> Any:
    def go() -> dict:
        service = _service()
        service.check_write(_client(request))
        return service.cancel(body.reference, body.phone)

    return _guarded(go)


@router.post("/api/v1/public/callback-requests", response_model=None)
async def public_callback(request: Request, body: CallbackBody) -> Any:
    def go() -> JSONResponse:
        service = _service()
        if not service.config.callback_enabled:
            raise BookingError("booking_closed", "Call-back requests are not available.", 404)
        client = _client(request)
        service.check_write(client)
        phone, name = clean_phone(body.phone), clean_name(body.name)
        service.check_phone(phone)
        if not body.website.strip():
            reason = " ".join(body.reason.split())[:200]
            _queue_callback(
                phone,
                body.language if body.language in ("bn", "en") else "bn",
                f"Asked on the booking page: {name}" + (f" - {reason}" if reason else ""),
            )
        return JSONResponse({"status": "received"}, status_code=201)

    return _guarded(go)


def _queue_callback(phone: str, language: str, reason: str) -> None:
    from shefa.call_log import default_calls_store

    default_calls_store().add_callback(None, phone, language, reason)


@router.get("/book", response_class=HTMLResponse)
@router.get("/book/{path:path}", response_class=HTMLResponse)
async def patient_page(path: str = "") -> HTMLResponse:
    """The patient page: the same built app, which shows the booking screens at /book."""
    from shefa.main import APP_DIR

    index = APP_DIR / "index.html"
    if not index.is_file():
        return HTMLResponse("<h1>The booking page is not built</h1>", status_code=503)
    return HTMLResponse(index.read_text(encoding="utf-8"))
