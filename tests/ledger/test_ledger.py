"""Tests for volnix.ledger.ledger -- append-only audit ledger."""
import pytest
from datetime import datetime, timedelta, timezone

from volnix.core.types import ActorId, EntityId, SnapshotId, RunId
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import (
    EngineLifecycleEntry,
    GatewayRequestEntry,
    LLMCallEntry,
    PipelineStepEntry,
    SnapshotEntry,
    StateMutationEntry,
    ValidationEntry,
)
from volnix.ledger.ledger import Ledger
from volnix.ledger.query import LedgerQuery
from volnix.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def db(tmp_path):
    """Create a temporary SQLite database."""
    database = SQLiteDatabase(str(tmp_path / "ledger_test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def ledger(db):
    """Create and initialize a Ledger with default config."""
    config = LedgerConfig()
    led = Ledger(config, db)
    await led.initialize()
    return led


def _make_pipeline_entry(**kwargs):
    defaults = {
        "step_name": "auth_check",
        "request_id": "req-1",
        "actor_id": ActorId("actor-1"),
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


def _make_engine_entry(**kwargs):
    defaults = {
        "engine_name": "reasoning",
        "event_type": "start",
    }
    defaults.update(kwargs)
    return EngineLifecycleEntry(**defaults)


async def test_ledger_initialize(db):
    """initialize() should create the ledger_log table and indices."""
    config = LedgerConfig()
    led = Ledger(config, db)
    assert await db.table_exists("ledger_log") is False
    await led.initialize()
    assert await db.table_exists("ledger_log") is True


async def test_ledger_append(ledger):
    """append() should store an entry and return a positive sequence ID."""
    entry = _make_pipeline_entry()
    seq = await ledger.append(entry)
    assert seq >= 1


async def test_ledger_append_multiple_types(ledger):
    """append() should handle different entry types."""
    e1 = _make_pipeline_entry()
    e2 = _make_llm_entry()
    e3 = _make_engine_entry()

    s1 = await ledger.append(e1)
    s2 = await ledger.append(e2)
    s3 = await ledger.append(e3)

    assert s1 >= 1
    assert s2 > s1
    assert s3 > s2


async def test_ledger_query_all(ledger):
    """query() with no filters should return all entries in order."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())
    await ledger.append(_make_engine_entry())

    results = await ledger.query(LedgerQuery())
    assert len(results) == 3


async def test_ledger_query_by_type(ledger):
    """query() with entry_type filter should only return matching entries."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())
    await ledger.append(_make_pipeline_entry())

    results = await ledger.query(LedgerQuery(entry_type="pipeline_step"))
    assert len(results) == 2
    assert all(e.entry_type == "pipeline_step" for e in results)


async def test_ledger_query_by_actor(ledger):
    """query() with actor_id filter should only return matching entries."""
    await ledger.append(_make_pipeline_entry(actor_id=ActorId("alice")))
    await ledger.append(_make_pipeline_entry(actor_id=ActorId("bob")))
    await ledger.append(_make_pipeline_entry(actor_id=ActorId("alice")))

    results = await ledger.query(LedgerQuery(actor_id=ActorId("alice")))
    assert len(results) == 2


async def test_ledger_query_with_limit_offset(ledger):
    """query() with limit and offset should paginate results."""
    for i in range(5):
        await ledger.append(_make_pipeline_entry(step_name=f"step_{i}"))

    # Limit only
    results = await ledger.query(LedgerQuery(limit=3))
    assert len(results) == 3

    # Offset
    results_offset = await ledger.query(LedgerQuery(limit=10, offset=2))
    assert len(results_offset) == 3


async def test_ledger_get_count(ledger):
    """get_count() should return the total number of entries."""
    assert await ledger.get_count() == 0
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())
    assert await ledger.get_count() == 2


async def test_ledger_get_count_by_type(ledger):
    """get_count(entry_type=...) should count only matching entries."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())
    await ledger.append(_make_pipeline_entry())

    assert await ledger.get_count("pipeline_step") == 2
    assert await ledger.get_count("llm_call") == 1
    assert await ledger.get_count("engine_lifecycle") == 0


async def test_ledger_typed_deserialization(ledger):
    """query() should return correctly typed subclasses, not base LedgerEntry."""
    await ledger.append(_make_pipeline_entry())
    await ledger.append(_make_llm_entry())
    await ledger.append(_make_engine_entry())

    results = await ledger.query(LedgerQuery())
    assert isinstance(results[0], PipelineStepEntry)
    assert isinstance(results[1], LLMCallEntry)
    assert isinstance(results[2], EngineLifecycleEntry)


async def test_ledger_entry_type_filtering(db):
    """When entry_types_enabled is set, disabled types should return -1."""
    config = LedgerConfig(entry_types_enabled=["pipeline_step", "llm_call"])
    led = Ledger(config, db)
    await led.initialize()

    # Enabled type should work
    seq = await led.append(_make_pipeline_entry())
    assert seq >= 1

    # Disabled type should return -1
    seq = await led.append(_make_engine_entry())
    assert seq == -1

    # Only 1 entry should be stored
    assert await led.get_count() == 1


async def test_ledger_query_by_time_range(ledger):
    """query() with start_time/end_time should filter by timestamp."""
    now = datetime.now(timezone.utc)
    past = now - timedelta(hours=2)
    future = now + timedelta(hours=2)

    # Create entries with specific timestamps
    entry_old = PipelineStepEntry(
        step_name="old",
        request_id="r1",
        actor_id=ActorId("a1"),
        action="read",
        verdict="allow",
        timestamp=past,
    )
    entry_now = PipelineStepEntry(
        step_name="now",
        request_id="r2",
        actor_id=ActorId("a1"),
        action="read",
        verdict="allow",
        timestamp=now,
    )
    entry_future = PipelineStepEntry(
        step_name="future",
        request_id="r3",
        actor_id=ActorId("a1"),
        action="read",
        verdict="allow",
        timestamp=future,
    )

    await ledger.append(entry_old)
    await ledger.append(entry_now)
    await ledger.append(entry_future)

    # Query with start_time only
    results = await ledger.query(LedgerQuery(
        start_time=now - timedelta(minutes=1),
    ))
    assert len(results) == 2  # entry_now and entry_future

    # Query with end_time only
    results = await ledger.query(LedgerQuery(
        end_time=now + timedelta(minutes=1),
    ))
    assert len(results) == 2  # entry_old and entry_now

    # Query with both
    results = await ledger.query(LedgerQuery(
        start_time=now - timedelta(minutes=1),
        end_time=now + timedelta(minutes=1),
    ))
    assert len(results) == 1  # only entry_now


async def test_ledger_shutdown_is_noop(ledger):
    """shutdown() should be a no-op -- database remains usable."""
    await ledger.append(_make_pipeline_entry())
    await ledger.shutdown()
    # Database should still be usable after shutdown
    count = await ledger.get_count()
    assert count == 1
