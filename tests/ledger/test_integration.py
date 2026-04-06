"""Integration tests for the ledger with real persistence infrastructure."""

from datetime import UTC, datetime

from volnix.bus.bus import EventBus
from volnix.bus.config import BusConfig
from volnix.core.events import Event
from volnix.core.types import ActorId, Timestamp
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import (
    EngineLifecycleEntry,
    LLMCallEntry,
    PipelineStepEntry,
)
from volnix.ledger.ledger import Ledger
from volnix.ledger.query import LedgerQuery
from volnix.persistence.config import PersistenceConfig
from volnix.persistence.manager import ConnectionManager
from volnix.persistence.sqlite import SQLiteDatabase


def _make_event(event_type: str = "test.event") -> Event:
    """Helper to create a test Event."""
    return Event(
        event_type=event_type,
        timestamp=Timestamp(
            world_time=datetime(2025, 1, 1, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=1,
        ),
    )


def _make_pipeline_entry(**kwargs):
    defaults = {
        "step_name": "check",
        "request_id": "r1",
        "actor_id": ActorId("a1"),
        "action": "read",
        "verdict": "allow",
    }
    defaults.update(kwargs)
    return PipelineStepEntry(**defaults)


def _make_llm_entry(**kwargs):
    defaults = {
        "provider": "openai",
        "model": "gpt-4",
        "engine_name": "reasoning",
    }
    defaults.update(kwargs)
    return LLMCallEntry(**defaults)


async def test_ledger_with_connection_manager(tmp_path):
    """Ledger should work with a database obtained from ConnectionManager."""
    config = PersistenceConfig(base_dir=str(tmp_path))
    mgr = ConnectionManager(config)
    await mgr.initialize()

    db = await mgr.get_connection("ledger")

    ledger_config = LedgerConfig()
    ledger = Ledger(ledger_config, db)
    await ledger.initialize()

    entry = _make_pipeline_entry()
    seq = await ledger.append(entry)
    assert seq >= 1

    results = await ledger.query(LedgerQuery())
    assert len(results) == 1
    assert isinstance(results[0], PipelineStepEntry)

    await ledger.shutdown()
    await mgr.shutdown()


async def test_ledger_append_query_cycle(tmp_path):
    """Full append -> query -> verify cycle with multiple entry types."""
    db = SQLiteDatabase(str(tmp_path / "cycle.db"))
    await db.connect()

    ledger_config = LedgerConfig()
    ledger = Ledger(ledger_config, db)
    await ledger.initialize()

    # Append mixed entries
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())
    await ledger.append(EngineLifecycleEntry(engine_name="core", event_type="init"))

    # Query all
    all_entries = await ledger.query(LedgerQuery())
    assert len(all_entries) == 3

    # Query by type
    pipeline_only = await ledger.query(LedgerQuery(entry_type="pipeline_step"))
    assert len(pipeline_only) == 1
    assert isinstance(pipeline_only[0], PipelineStepEntry)

    # Count
    assert await ledger.get_count() == 3
    assert await ledger.get_count("llm_call") == 1

    await db.close()


async def test_ledger_and_bus_coexist(tmp_path):
    """Ledger and EventBus should coexist on separate databases."""
    config = PersistenceConfig(base_dir=str(tmp_path))
    mgr = ConnectionManager(config)
    await mgr.initialize()

    # Get separate databases for bus and ledger
    bus_db = await mgr.get_connection("events")
    ledger_db = await mgr.get_connection("ledger")

    # Set up EventBus
    bus_config = BusConfig(persistence_enabled=True)
    bus = EventBus(bus_config, db=bus_db)
    await bus.initialize()

    # Set up Ledger
    ledger_config = LedgerConfig()
    ledger = Ledger(ledger_config, ledger_db)
    await ledger.initialize()

    # Publish an event to the bus
    event = _make_event("action.executed")
    await bus.publish(event)

    # Append an entry to the ledger
    entry = _make_pipeline_entry()
    await ledger.append(entry)

    # Verify bus has its event
    assert await bus.get_event_count() == 1

    # Verify ledger has its entry
    assert await ledger.get_count() == 1
    results = await ledger.query(LedgerQuery())
    assert isinstance(results[0], PipelineStepEntry)

    # Shutdown
    await bus.shutdown()
    await ledger.shutdown()
    await mgr.shutdown()


async def test_foundation_smoke(tmp_path):
    """Smoke test: all A1-A4 foundation components work together.

    Creates ConnectionManager, EventBus with persistence, and Ledger,
    all sharing the same ConnectionManager for database lifecycle.
    """
    # A1: Persistence layer
    config = PersistenceConfig(base_dir=str(tmp_path))
    mgr = ConnectionManager(config)
    await mgr.initialize()

    # A2/A3: EventBus with persistence
    bus_db = await mgr.get_connection("events")
    bus_config = BusConfig(persistence_enabled=True)
    bus = EventBus(bus_config, db=bus_db)
    await bus.initialize()

    # A4: Ledger
    ledger_db = await mgr.get_connection("ledger")
    ledger_config = LedgerConfig()
    ledger = Ledger(ledger_config, ledger_db)
    await ledger.initialize()

    # Publish events
    for i in range(3):
        await bus.publish(_make_event(f"test.event.{i}"))
    assert await bus.get_event_count() == 3

    # Append ledger entries
    await ledger.append(_make_pipeline_entry(step_name="step_a"))
    await ledger.append(_make_llm_entry(provider="anthropic"))
    await ledger.append(EngineLifecycleEntry(engine_name="core", event_type="init"))

    assert await ledger.get_count() == 3
    assert await ledger.get_count("pipeline_step") == 1
    assert await ledger.get_count("llm_call") == 1
    assert await ledger.get_count("engine_lifecycle") == 1

    # Typed deserialization
    results = await ledger.query(LedgerQuery())
    assert isinstance(results[0], PipelineStepEntry)
    assert isinstance(results[1], LLMCallEntry)
    assert isinstance(results[2], EngineLifecycleEntry)

    # Health check
    health = await mgr.health_check()
    assert health["count"] == 2  # events + ledger

    # Shutdown everything
    await bus.shutdown()
    await ledger.shutdown()
    await mgr.shutdown()
