"""Shared test fixtures."""

import pytest


@pytest.fixture
def sample_config():
    from sefa.config.settings import AppConfig

    return AppConfig()


@pytest.fixture(autouse=True)
def reset_shared_registry():
    """Clear the process-wide `registry` between tests (D-ENG22).

    `sefa.models.registry.registry` is a module-level singleton, so an adapter
    cached by one test is still cached by the next. The registry now keeps its
    adapters as instance attrs, but the singleton's own state is still shared
    state, so it has to be reset explicitly to keep the suite
    order-independent.
    """
    from sefa.models.registry import registry

    registry._stt = None
    registry._tts = None
    registry._llm = None
    yield
    registry._stt = None
    registry._tts = None
    registry._llm = None
