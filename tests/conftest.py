"""Shared test fixtures for Terrarium test suite."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

# Import core types
from terrarium.core.types import (
    EntityId, ActorId, ServiceId, EventId, ToolName, RunId,
    FidelityTier, StepVerdict, ActionCost, StateDelta, Timestamp,
)
from terrarium.core.events import Event, WorldEvent
from terrarium.core.context import ActionContext, StepResult, ResponseProposal


@pytest.fixture
def mock_event_bus():
    """Mock EventBus that captures published events in a list."""
    bus = AsyncMock()
    bus.published = []

    async def _publish(event):
        bus.published.append(event)

    bus.publish = AsyncMock(side_effect=_publish)
    bus.subscribe = MagicMock()
    return bus


@pytest.fixture
def mock_ledger():
    """Mock Ledger that captures entries in a list."""
    ledger = AsyncMock()
    ledger.entries = []
    ledger._seq = 0

    async def _append(entry):
        ledger._seq += 1
        ledger.entries.append(entry)
        return ledger._seq

    ledger.append = AsyncMock(side_effect=_append)
    ledger.query = AsyncMock(return_value=[])
    return ledger


@pytest.fixture
def stub_state_engine():
    """Stub StateEngine that returns canned entity data."""
    engine = AsyncMock()
    engine._entities: dict = {}

    async def _get_entity(entity_type, entity_id):
        key = (entity_type, str(entity_id))
        if key not in engine._entities:
            from terrarium.core.errors import EntityNotFoundError
            raise EntityNotFoundError(f"{entity_type}/{entity_id}")
        return engine._entities[key]

    async def _query(entity_type, filters=None):
        return [
            v for k, v in engine._entities.items()
            if k[0] == entity_type
        ]

    engine.get_entity = AsyncMock(side_effect=_get_entity)
    engine.query_entities = AsyncMock(side_effect=_query)
    engine.propose_mutation = AsyncMock(side_effect=lambda d: d)
    engine.snapshot = AsyncMock(return_value="snap_test")
    return engine


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider returning deterministic responses."""
    from terrarium.llm.types import LLMResponse

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(
        content='{"result": "mock"}',
        provider="mock",
        model="mock-model",
        latency_ms=0,
    ))
    return provider


@pytest.fixture
def test_config():
    """Minimal valid TerrariumConfig for testing."""
    from terrarium.config.schema import TerrariumConfig
    return TerrariumConfig()


@pytest.fixture
def make_action_context():
    """Factory fixture for creating ActionContext with sensible defaults."""
    def _make(**kwargs):
        now = datetime.now(timezone.utc)
        defaults = {
            "request_id": "req-test-001",
            "actor_id": ActorId("actor-test"),
            "service_id": ServiceId("email"),
            "action": "email_send",
            "input_data": {"from_addr": "a@b.com", "to_addr": "c@d.com",
                           "subject": "test", "body": "hello"},
            "world_time": now,
            "wall_time": now,
            "tick": 1,
        }
        defaults.update(kwargs)
        return ActionContext(**defaults)
    return _make


@pytest.fixture
def make_world_event():
    """Factory fixture for creating WorldEvent with sensible defaults."""
    def _make(**kwargs):
        now = datetime.now(timezone.utc)
        defaults = {
            "event_type": "world.email_send",
            "timestamp": Timestamp(world_time=now, wall_time=now, tick=1),
            "actor_id": ActorId("actor-test"),
            "service_id": ServiceId("email"),
            "action": "email_send",
            "input_data": {},
        }
        defaults.update(kwargs)
        return WorldEvent(**defaults)
    return _make


@pytest.fixture
async def temp_sqlite_db(tmp_path):
    """Create a temporary SQLite database for integration tests."""
    from terrarium.persistence.sqlite import SQLiteDatabase

    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.connect()
    yield db
    await db.close()
