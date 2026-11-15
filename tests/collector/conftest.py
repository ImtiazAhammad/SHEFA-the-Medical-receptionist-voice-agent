# ruff: noqa: E501, N812, TC001, TC003
import io
import uuid
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from shefa.collector.api import Ctx, create_private_app, create_public_app
from shefa.collector.config import CollectorConfig


def make_wav(seconds=1.6, amp=0.3, noise=0.002, clip=False, seed=0, rate=16000) -> bytes:
    """Speech-like: loud bursts with quiet gaps, so the speech check passes."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * rate)) / rate
    burst = (
        np.sin(2 * np.pi * (180 + 40 * (seed % 20)) * t) * (np.sin(2 * np.pi * 3 * t) > 0)
    ) * amp
    x = burst + rng.standard_normal(t.size) * noise
    if clip:
        x = np.clip(x * 20, -1, 1)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


@pytest.fixture
def config(tmp_path):
    return CollectorConfig(
        data_dir=tmp_path / "collector", min_free_disk_mb=1, password_iterations=1000
    )


@pytest.fixture
def ctx(config):
    return Ctx(config)


@pytest.fixture
def pub(ctx, config):
    return TestClient(create_public_app(config, ctx))


@pytest.fixture
def priv(ctx, config):
    return TestClient(create_private_app(config, ctx))


class Person:
    """A contributor on a phone: starts a session, uploads clips."""

    def __init__(self, client, config):
        self.client, self.config = client, config
        reply = client.post(
            "/api/c/start",
            json={
                "consent": True,
                "consent_version": config.consent_version,
                "device": "test phone",
            },
        )
        assert reply.status_code == 200, reply.text
        self.info = reply.json()
        self.h = {
            "x-cid": self.info["contributor_id"],
            "x-secret": self.info["secret"],
            "x-speaker": self.info["speaker_id"],
        }
        self.n = 0

    def clip(self, data=None, clip_id=None, headers=None):
        self.n += 1
        cid = clip_id or uuid.uuid4().hex
        body = data if data is not None else make_wav(seed=int(uuid.uuid4().int % 10**9))
        return self.client.put(
            f"/api/c/clip/{cid}", content=body, headers={**self.h, **(headers or {})}
        )


@pytest.fixture
def person(pub, config):
    return Person(pub, config)
