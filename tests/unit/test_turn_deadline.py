"""A turn that stalls fails after a deadline instead of leaving the caller in silence."""

from __future__ import annotations

import asyncio

import pytest

from shefa.config.settings import settings
from shefa.pipeline.voice_pipeline import VoicePipeline


async def test_a_stalled_turn_is_cut_off(monkeypatch):
    monkeypatch.setattr(settings.pipeline, "turn_deadline_s", 0.05)

    async def stalls():
        await asyncio.sleep(5)

    with pytest.raises(TimeoutError):
        await VoicePipeline._within_deadline(stalls())


async def test_a_normal_turn_passes_through(monkeypatch):
    monkeypatch.setattr(settings.pipeline, "turn_deadline_s", 1.0)

    async def quick():
        return "reply"

    assert await VoicePipeline._within_deadline(quick()) == "reply"


def test_the_default_deadline_is_longer_than_a_model_request_but_not_endless():
    assert settings.pipeline.llm.timeout_s < settings.pipeline.turn_deadline_s <= 30
