"""Fixtures for architecture tests that need a running app."""
from __future__ import annotations

import pytest

from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.engines.state.config import StateConfig
from volnix.persistence.config import PersistenceConfig


@pytest.fixture
async def app(tmp_path):
    """Minimal VolnixApp for architecture contract tests."""
    config = VolnixConfig()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })
    volnix_app = VolnixApp(config)
    await volnix_app.start()
    yield volnix_app
    await volnix_app.stop()
