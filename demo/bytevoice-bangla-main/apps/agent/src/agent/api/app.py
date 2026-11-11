import hmac
import logging
from typing import Annotated
from uuid import UUID

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.config import get_settings
from agent.constants import LOGGER_NAME
from agent.services.finalize import finalize_call

load_dotenv(".env.local")
load_dotenv(".env")

logger = logging.getLogger(LOGGER_NAME)


class HealthResponse(BaseModel):
    status: str
    voice_engine: str


class FinalizeResponse(BaseModel):
    call_id: UUID
    outcome: str | None


def require_internal_token(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().internal_api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Internal API token not configured"
        )
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="ByteVoice Bangla agent API", docs_url=None, redoc_url=None)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.get("/health")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", voice_engine=settings.voice_engine.value)

    async def _finalize(call_id: UUID) -> FinalizeResponse:
        try:
            outcome = await finalize_call(str(call_id))
        except Exception as error:
            logger.exception("reprocess failed", extra={"call_id": str(call_id)})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Reprocess failed"
            ) from error
        if outcome is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Call not found or could not be processed"
            )
        return FinalizeResponse(call_id=call_id, outcome=outcome)

    @application.post("/calls/{call_id}/finalize", dependencies=[Depends(require_internal_token)])
    async def finalize(call_id: UUID) -> FinalizeResponse:
        return await _finalize(call_id)

    @application.post("/calls/{call_id}/reprocess", dependencies=[Depends(require_internal_token)])
    async def reprocess(call_id: UUID) -> FinalizeResponse:
        return await _finalize(call_id)

    return application


app = create_app()
