"""Session management with Redis or in-memory fallback."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from sefa.config.settings import settings
from sefa.models.base import Language


@dataclass
class Turn:
    role: str
    content: str
    language: Language = Language.ENGLISH
    timestamp: float = 0.0
    tool_call_id: str | None = None
    tool_call_name: str | None = None


@dataclass
class CallSession:
    call_sid: str
    patient_id: str | None = None
    patient_name: str | None = None
    language: Language = Language.ENGLISH
    state: str = "greeting"
    history: list[Turn] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def add_turn(
        self,
        role: str,
        content: str,
        language: Language | None = None,
        **kwargs: Any,
    ) -> None:
        self.history.append(Turn(
            role=role,
            content=content,
            language=language or self.language,
            timestamp=time.time(),
            **kwargs,
        ))
        self.last_activity = time.time()
        if len(self.history) > settings.session.max_history_turns:
            self.history = self.history[-settings.session.max_history_turns:]

    def to_messages(self) -> list[dict[str, str]]:
        return [{"role": t.role, "content": t.content} for t in self.history]

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_sid": self.call_sid,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "language": self.language.value,
            "state": self.state,
            "history": [
                {
                    "role": t.role,
                    "content": t.content,
                    "language": t.language.value,
                    "timestamp": t.timestamp,
                }
                for t in self.history
            ],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallSession:
        history = [
            Turn(
                role=t["role"],
                content=t["content"],
                language=Language(t.get("language", "en")),
                timestamp=t.get("timestamp", 0),
            )
            for t in data.get("history", [])
        ]
        return cls(
            call_sid=data["call_sid"],
            patient_id=data.get("patient_id"),
            patient_name=data.get("patient_name"),
            language=Language(data.get("language", "en")),
            state=data.get("state", "greeting"),
            history=history,
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", 0),
            last_activity=data.get("last_activity", 0),
        )


class SessionManager:
    """Manages active call sessions. Redis-backed with in-memory fallback."""

    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}
        self._redis = None

    async def _get_redis(self):  # noqa: ANN202
        if self._redis is None:
            try:
                import os
                import redis.asyncio as aioredis
                redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
                self._redis = await aioredis.from_url(
                    redis_url,
                    decode_responses=True,
                )
            except Exception:
                return None
        return self._redis

    async def get_or_create(self, call_sid: str) -> CallSession:
        existing = await self.get(call_sid)
        if existing:
            return existing
        session = CallSession(call_sid=call_sid)
        await self.save(session)
        return session

    async def get(self, call_sid: str) -> CallSession | None:
        redis = await self._get_redis()
        if redis:
            data = await redis.get(f"session:{call_sid}")
            if data:
                return CallSession.from_dict(json.loads(data))
        return self._sessions.get(call_sid)

    async def save(self, session: CallSession) -> None:
        redis = await self._get_redis()
        if redis:
            ttl = settings.session.ttl_seconds
            await redis.setex(f"session:{session.call_sid}", ttl, json.dumps(session.to_dict()))
        self._sessions[session.call_sid] = session

    async def delete(self, call_sid: str) -> None:
        redis = await self._get_redis()
        if redis:
            await redis.delete(f"session:{call_sid}")
        self._sessions.pop(call_sid, None)
