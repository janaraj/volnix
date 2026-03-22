"""Shared fixtures for integration tests.

Bootstraps a full TerrariumApp with temporary databases so that E2E
tests exercise the real pipeline, real packs, real state engine, and
real bus/ledger -- no mocks.
"""
from __future__ import annotations

import pytest

from terrarium.config.schema import TerrariumConfig
from terrarium.persistence.config import PersistenceConfig
from terrarium.engines.state.config import StateConfig


@pytest.fixture
async def app(tmp_path):
    """Fully bootstrapped TerrariumApp with tmp databases.

    Overrides persistence base_dir and state db_path so every test run
    uses isolated temporary storage.  Yields the running app and shuts
    it down on teardown.
    """
    from terrarium.app import TerrariumApp

    config = TerrariumConfig()
    # TerrariumConfig is frozen -- use model_copy to override fields
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


# ── Helpers ──────────────────────────────────────────────────────────

def email_send_payload(
    from_addr: str = "alice@test.com",
    to_addr: str = "bob@test.com",
    subject: str = "Hello",
    body: str = "World",
) -> dict:
    """Convenience builder for email_send input_data."""
    return {
        "from_addr": from_addr,
        "to_addr": to_addr,
        "subject": subject,
        "body": body,
    }
