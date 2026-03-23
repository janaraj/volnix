"""Shared test fixtures for Terrarium test suite."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from terrarium.core.context import ActionContext
from terrarium.core.events import WorldEvent

# Import core types
from terrarium.core.types import (
    ActorId,
    ServiceId,
    Timestamp,
)


def pytest_addoption(parser):
    """Add a switch for fail-closed architecture guardrails."""
    parser.addoption(
        "--guardrails-strict",
        action="store_true",
        default=False,
        help="Run staged architecture/contract guardrails as ordinary tests.",
    )


def _guardrails_strict(config: pytest.Config) -> bool:
    """Return True when staged guardrails should fail closed."""
    if config.getoption("--guardrails-strict"):
        return True

    value = os.environ.get("TERRARIUM_GUARDRAILS_STRICT", "")
    return value.lower() not in {"", "0", "false", "no"}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Stage known guardrails behind a single strictness switch."""
    if _guardrails_strict(config):
        return

    for item in items:
        marker = item.get_closest_marker("staged_guardrail")
        if marker is None:
            continue
        reason = marker.kwargs.get("reason", "Known staged guardrail")
        item.add_marker(pytest.mark.xfail(reason=reason, strict=True))


@pytest.fixture
def guardrails_strict(pytestconfig: pytest.Config) -> bool:
    """Expose the staged-guardrail mode to tests when needed."""
    return _guardrails_strict(pytestconfig)


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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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
