"""Dependency health: is the database writable, and can we still reach Asterisk?"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def database_status() -> str:
    try:
        from shefa.clinic import default_clinic_store

        default_clinic_store().connection.execute("SELECT 1").fetchone()
    except Exception:
        logger.exception("Health: clinic database check failed")
        return "error"
    return "ok"


async def asterisk_status() -> str:
    """'n/a' unless Asterisk is the provider; otherwise whether ARI answers."""
    from shefa.config.settings import TelephonyProvider, settings

    if settings.telephony.provider != TelephonyProvider.ASTERISK:
        return "n/a"
    try:
        from shefa.telephony import asterisk

        async with asterisk.client_factory() as client:
            reply = await client.get("/asterisk/info")
            reply.raise_for_status()
    except Exception as exc:
        logger.warning("Health: Asterisk ARI unreachable: %s", exc)
        return "unreachable"
    return "ok"


async def health_report() -> dict[str, Any]:
    database, asterisk = database_status(), await asterisk_status()
    healthy = database == "ok" and asterisk in {"ok", "n/a"}
    return {
        "status": "healthy" if healthy else "degraded",
        "version": "0.1.0",
        "database": database,
        "asterisk": asterisk,
    }
