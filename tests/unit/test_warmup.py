"""Warm-up loads the models once and never takes the server down."""

import asyncio

import httpx
import pytest

from shefa import warmup
from shefa.config.settings import settings


class _Stt:
    def __init__(self):
        self.heard = []

    async def transcribe(self, audio):
        self.heard.append(len(audio))


class _Tts:
    async def synthesize_stream(self, text, language="bn"):
        yield b"x"


class _Registry:
    def __init__(self, stt, tts):
        self._stt, self._tts = stt, tts

    async def get_stt(self):
        return self._stt

    async def get_tts(self):
        return self._tts

    async def get_llm(self):
        return object()


def _stub_router(monkeypatch):
    calls = []

    async def fake_extract(llm, session):
        calls.append(session.history[-1].content)

    monkeypatch.setattr("shefa.pipeline.actions.extract_action", fake_extract)
    return calls


@pytest.fixture
def pings(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.content))
        return httpx.Response(200, json={})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        warmup.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    return seen


async def test_ping_asks_ollama_to_keep_the_model(pings):
    await warmup.ping_llm()
    url, body = pings[0]
    assert url.endswith("/api/generate")
    assert b"keep_alive" in body and b"30m" in body


async def test_ping_skips_a_hosted_provider(pings, monkeypatch):
    monkeypatch.setattr(settings.pipeline.llm, "provider", "openai")
    await warmup.ping_llm()
    assert pings == []


async def test_warm_models_loads_each_stage(pings, monkeypatch):
    stt = _Stt()
    monkeypatch.setattr(warmup, "registry", _Registry(stt, _Tts()))
    routed = _stub_router(monkeypatch)
    timings = await warmup.warm_models()
    assert set(timings) == {"stt", "tts", "llm"}
    assert routed  # the router prompt is exercised, not just the model loaded
    assert stt.heard == [16000]


async def test_a_failed_stage_is_skipped_not_raised(pings, monkeypatch):
    class Broken(_Registry):
        async def get_stt(self):
            raise RuntimeError("no gpu")

    _stub_router(monkeypatch)
    monkeypatch.setattr(warmup, "registry", Broken(None, _Tts()))
    timings = await warmup.warm_models()
    assert set(timings) == {"tts", "llm"}


async def test_run_forever_pings_again(pings, monkeypatch):
    _stub_router(monkeypatch)
    monkeypatch.setattr(warmup, "registry", _Registry(_Stt(), _Tts()))
    monkeypatch.setattr(warmup, "PING_INTERVAL_S", 0.01)
    task = asyncio.create_task(warmup.run_forever())
    await asyncio.sleep(0.15)
    task.cancel()
    assert len(pings) >= 3


def test_warmup_is_off_under_tests():
    assert warmup.warmup_enabled() is False
