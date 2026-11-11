import asyncio
import logging
import re
from datetime import datetime
from typing import Any

from supabase import AsyncClient, create_async_client

from agent.config import get_settings
from agent.constants import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

EXCLUSION_VIOLATION_CODE = "23P01"
UNIQUE_VIOLATION_CODE = "23505"

_RANGE_PATTERN = re.compile(r'^[\[(]"?([^",]+)"?,"?([^",]+)"?[\])]$')

_client: AsyncClient | None = None
_client_lock = asyncio.Lock()


class DatabaseUnavailableError(RuntimeError):
    pass


class SlotTakenError(RuntimeError):
    pass


async def get_database() -> AsyncClient:
    global _client
    async with _client_lock:
        if _client is None:
            settings = get_settings()
            if not settings.supabase_url or not settings.supabase_service_role_key:
                raise DatabaseUnavailableError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
            _client = await create_async_client(settings.supabase_url, settings.supabase_service_role_key)
            logger.debug("supabase client created")
        return _client


def format_time_range(starts_at: datetime, ends_at: datetime) -> str:
    return f"[{starts_at.isoformat()},{ends_at.isoformat()})"


def parse_time_range(value: str) -> tuple[datetime, datetime]:
    match = _RANGE_PATTERN.match(value.strip())
    if not match:
        raise ValueError(f"Unrecognised tstzrange: {value}")
    return _parse_timestamp(match[1]), _parse_timestamp(match[2])


def _parse_timestamp(value: str) -> datetime:
    normalised = value.strip().replace(" ", "T")
    if re.search(r"[+-]\d{2}$", normalised):
        normalised = f"{normalised}:00"
    return datetime.fromisoformat(normalised)


def rows_of(response: object) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]
