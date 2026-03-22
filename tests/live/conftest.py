"""Shared fixtures for live integration tests.

All tests in this directory require GOOGLE_API_KEY in the environment.
They make real LLM calls to gemini-3-flash-preview.
"""
from __future__ import annotations

import os

import pytest

from terrarium.app import TerrariumApp
from terrarium.config.loader import ConfigLoader
from terrarium.persistence.config import PersistenceConfig
from terrarium.engines.state.config import StateConfig


def pytest_collection_modifyitems(config, items):
    """Skip ALL tests in this directory if GOOGLE_API_KEY is not set."""
    if os.environ.get("GOOGLE_API_KEY"):
        return
    skip = pytest.mark.skip(reason="GOOGLE_API_KEY not set — live tests require real LLM")
    for item in items:
        if "tests/live" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture
async def live_app(tmp_path):
    """Fully bootstrapped TerrariumApp with REAL Gemini LLM.

    Loads config from terrarium.toml (picks up GOOGLE_API_KEY from env).
    Uses temporary databases for isolation.
    """
    loader = ConfigLoader()
    config = loader.load()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = TerrariumApp(config)
    await app.start()
    yield app
    await app.stop()
