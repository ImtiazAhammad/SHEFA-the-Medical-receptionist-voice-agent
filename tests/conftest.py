"""Shared test fixtures."""

import pytest


@pytest.fixture
def sample_config():
    from sefa.config.settings import AppConfig

    return AppConfig()
