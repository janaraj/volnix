"""Fixtures for architecture tests that need a running app."""
from __future__ import annotations

import pytest

from terrarium.app import TerrariumApp
from terrarium.config.schema import TerrariumConfig
from terrarium.engines.state.config import StateConfig
from terrarium.persistence.config import PersistenceConfig


@pytest.fixture
async def app(tmp_path):
    """Minimal TerrariumApp for architecture contract tests."""
    config = TerrariumConfig()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })
    terrarium_app = TerrariumApp(config)
    await terrarium_app.start()
    yield terrarium_app
    await terrarium_app.stop()
