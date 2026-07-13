"""sefa Receptionist - Main application entry point."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from sefa.config.settings import settings
from sefa.telephony.twilio import app as telephony_app

logging.basicConfig(
    level=getattr(logging, settings.monitoring.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sefa")


def create_app() -> FastAPI:
    """Create and configure the main FastAPI application."""
    app = FastAPI(
        title="sefa Receptionist",
        version="0.1.0",
        description="HIPAA-compliant bilingual voice AI medical receptionist",
    )

    app.include_router(telephony_app.router, prefix="/api/v1/telephony", tags=["telephony"])

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

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "sefa.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.monitoring.log_level == "DEBUG",
    )
