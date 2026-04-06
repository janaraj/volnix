"""Shared fixtures for live integration tests.

All tests in this directory require a real LLM provider:
  - codex-acp (default, configured in volnix.toml)
  - OR GOOGLE_API_KEY for direct Gemini access
"""

from __future__ import annotations

import os

import pytest

from volnix.app import VolnixApp
from volnix.config.loader import ConfigLoader
from volnix.engines.state.config import StateConfig
from volnix.persistence.config import PersistenceConfig
from volnix.worlds.config import WorldsConfig


def _has_llm_provider() -> bool:
    """Check if live API tests are explicitly enabled."""
    # Require explicit opt-in to prevent accidental token spend
    if os.environ.get("VOLNIX_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes"):
        return True
    return False


def pytest_collection_modifyitems(config, items):
    """Skip ALL tests in this directory unless VOLNIX_RUN_REAL_API_TESTS=1."""
    if _has_llm_provider():
        return
    skip = pytest.mark.skip(reason="No LLM provider available (need codex-acp or GOOGLE_API_KEY)")
    for item in items:
        if "tests/live" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture
async def live_app(tmp_path):
    """Fully bootstrapped VolnixApp with real LLM provider.

    Uses codex-acp (default) or Gemini (if GOOGLE_API_KEY is set).
    Uses temporary databases for isolation.
    """
    loader = ConfigLoader()
    config = loader.load()
    config = config.model_copy(
        update={
            "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
            "state": StateConfig(
                db_path=str(tmp_path / "state.db"),
                snapshot_dir=str(tmp_path / "snapshots"),
            ),
            "worlds": WorldsConfig(data_dir=str(tmp_path / "worlds")),
        }
    )

    app = VolnixApp(config)
    await app.start()
    yield app
    await app.stop()
