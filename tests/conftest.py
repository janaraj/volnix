"""Shared test fixtures for Terrarium test suite."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Import core types
from terrarium.core.types import (
    EntityId, ActorId, ServiceId, EventId, ToolName, RunId,
    FidelityTier, StepVerdict, ActionCost, StateDelta,
)
from terrarium.core.events import Event, WorldEvent
from terrarium.core.context import ActionContext, StepResult, ResponseProposal


@pytest.fixture
def mock_event_bus():
    """Mock EventBus that captures published events in a list."""
    ...


@pytest.fixture
def mock_ledger():
    """Mock Ledger that captures entries in a list."""
    ...


@pytest.fixture
def stub_state_engine():
    """Stub StateEngine that returns canned entity data."""
    ...


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider returning deterministic responses."""
    ...


@pytest.fixture
def test_config():
    """Minimal valid TerrariumConfig for testing."""
    ...


@pytest.fixture
def make_action_context():
    """Factory fixture for creating ActionContext with sensible defaults."""
    def _make(**kwargs):
        ...
    return _make


@pytest.fixture
def make_world_event():
    """Factory fixture for creating WorldEvent with sensible defaults."""
    def _make(**kwargs):
        ...
    return _make


@pytest.fixture
async def temp_sqlite_db(tmp_path):
    """Create a temporary SQLite database for integration tests."""
    from terrarium.persistence.sqlite import SQLiteDatabase

    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.connect()
    yield db
    await db.close()
