"""Tests for SessionManager in-memory and Redis-backed paths."""

import sys
import types

from sefa.config.settings import settings
from sefa.session.manager import CallSession, SessionManager


def _set_backend(monkeypatch, backend: str) -> None:
    monkeypatch.setattr(settings.session, "backend", backend)


def _install_fake_redis(monkeypatch, from_url=None, client=None):
    redis_mod = types.ModuleType("redis")
    asyncio_mod = types.ModuleType("redis.asyncio")

    if from_url is None:
        async def from_url(url, **kwargs):
            return client

    asyncio_mod.from_url = from_url
    redis_mod.asyncio = asyncio_mod
    monkeypatch.setitem(sys.modules, "redis", redis_mod)
    monkeypatch.setitem(sys.modules, "redis.asyncio", asyncio_mod)


class _FakeRedisClient:
    def __init__(self, get_result=None, get_error=None, setex_error=None):
        self.get_result = get_result
        self.get_error = get_error
        self.setex_error = setex_error
        self.saved = None

    async def get(self, key):
        if self.get_error:
            raise self.get_error
        return self.get_result

    async def setex(self, key, ttl, value):
        if self.setex_error:
            raise self.setex_error
        self.saved = (key, ttl, value)

    async def delete(self, key):
        return 1


async def test_memory_backend_skips_redis(monkeypatch):
    _set_backend(monkeypatch, "memory")
    manager = SessionManager()

    assert await manager._get_redis() is None


async def test_redis_backend_returns_redis_client(monkeypatch):
    _set_backend(monkeypatch, "redis")
    client = _FakeRedisClient()
    _install_fake_redis(monkeypatch, client=client)
    manager = SessionManager()

    redis = await manager._get_redis()
    assert redis is client
    assert manager._redis_failed is False


async def test_memory_get_or_create_save_get_delete(monkeypatch):
    _set_backend(monkeypatch, "memory")
    manager = SessionManager()

    session = await manager.get_or_create("CA1")
    assert session.call_sid == "CA1"
    assert await manager.get("CA1") is session

    session.add_turn("user", "hello")
    await manager.save(session)
    loaded = await manager.get("CA1")
    assert loaded is session
    assert len(loaded.history) == 1

    await manager.delete("CA1")
    assert await manager.get("CA1") is None


async def test_redis_persists_and_loads(monkeypatch):
    _set_backend(monkeypatch, "redis")
    client = _FakeRedisClient()
    _install_fake_redis(monkeypatch, client=client)
    manager = SessionManager()

    session = CallSession(call_sid="CA2", patient_name="Maria")
    await manager.save(session)
    assert client.saved is not None
    assert client.saved[0] == "session:CA2"

    client.get_result = client.saved[2]
    fresh = SessionManager()
    got = await fresh.get("CA2")
    assert got is not None
    assert got.patient_name == "Maria"


async def test_redis_read_failure_falls_back_and_caches(monkeypatch):
    _set_backend(monkeypatch, "redis")
    client = _FakeRedisClient(get_error=RuntimeError("redis down"))
    _install_fake_redis(monkeypatch, client=client)
    manager = SessionManager()

    session = CallSession(call_sid="CA3")
    await manager.save(session)
    assert "CA3" in manager._sessions

    got = await manager.get("CA3")
    assert got is session
    assert manager._redis_failed is True
    assert await manager._get_redis() is None


async def test_redis_write_failure_falls_back_to_memory(monkeypatch):
    _set_backend(monkeypatch, "redis")
    client = _FakeRedisClient(setex_error=RuntimeError("redis down"))
    _install_fake_redis(monkeypatch, client=client)
    manager = SessionManager()

    session = CallSession(call_sid="CA4")
    await manager.save(session)
    assert "CA4" in manager._sessions
    assert manager._redis_failed is True
    assert await manager._get_redis() is None


async def test_redis_connect_failure_is_cached(monkeypatch):
    _set_backend(monkeypatch, "redis")

    def _boom(url, **kwargs):
        raise ConnectionError("no redis")

    _install_fake_redis(monkeypatch, from_url=_boom)
    manager = SessionManager()

    assert await manager._get_redis() is None
    assert manager._redis_failed is True
    assert await manager._get_redis() is None