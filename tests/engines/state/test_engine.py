"""Tests for volnix.engines.state.engine -- StateEngine orchestrator."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.core.context import ActionContext, ResponseProposal
from volnix.core.errors import EntityNotFoundError
from volnix.core.events import WorldEvent
from volnix.core.types import ActorId, EntityId, ServiceId, StateDelta, StepVerdict, Timestamp
from volnix.engines.state.engine import StateEngine


@pytest.fixture
async def engine(tmp_path):
    """Fully initialised StateEngine with a mock bus."""
    e = StateEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    config = {
        "db_path": str(tmp_path / "state.db"),
        "snapshot_dir": str(tmp_path / "snapshots"),
    }
    await e.initialize(config, bus)
    await e.start()
    yield e
    await e.stop()


def _make_ctx(action="create_user", deltas=None, **overrides):
    """Build an ActionContext with sensible defaults."""
    ctx = ActionContext(
        request_id="req-1",
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("user-svc"),
        action=action,
        input_data={"name": "Alice"},
        world_time=datetime(2026, 1, 15, tzinfo=UTC),
        wall_time=datetime.now(UTC),
        tick=1,
    )
    for k, v in overrides.items():
        setattr(ctx, k, v)
    if deltas is not None:
        ctx.response_proposal = ResponseProposal(
            response_body={"status": "ok"},
            proposed_state_deltas=deltas,
        )
    return ctx


# -- Initialisation -----------------------------------------------------------


async def test_on_initialize_migration(engine):
    """After initialisation, the required tables must exist."""
    db = engine._db
    assert await db.table_exists("entities")
    assert await db.table_exists("events")
    assert await db.table_exists("causal_edges")


# -- Execute (pipeline commit step) ------------------------------------------


async def test_execute_creates_entity(engine):
    """Execute with a 'create' StateDelta stores the entity."""
    delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice", "age": 30},
    )
    ctx = _make_ctx(deltas=[delta])
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ALLOW
    entity = await engine._store.read("user", EntityId("u-1"))
    assert entity is not None
    assert entity["name"] == "Alice"


async def test_execute_updates_entity(engine):
    """Execute with create then update delta merges fields and captures previous."""
    create = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice", "age": 30},
    )
    ctx1 = _make_ctx(deltas=[create])
    await engine.execute(ctx1)

    update = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="update",
        fields={"age": 31, "email": "a@b.com"},
    )
    ctx2 = _make_ctx(action="update_user", deltas=[update], request_id="req-2", tick=2)
    result = await engine.execute(ctx2)

    assert result.verdict == StepVerdict.ALLOW
    entity = await engine._store.read("user", EntityId("u-1"))
    assert entity["age"] == 31
    assert entity["email"] == "a@b.com"
    assert entity["name"] == "Alice"  # preserved


async def test_execute_deletes_entity(engine):
    """Execute with create then delete removes the entity."""
    create = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice"},
    )
    await engine.execute(_make_ctx(deltas=[create]))

    delete = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="delete",
        fields={},
    )
    ctx = _make_ctx(action="delete_user", deltas=[delete], request_id="req-2", tick=2)
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ALLOW
    entity = await engine._store.read("user", EntityId("u-1"))
    assert entity is None


async def test_execute_no_proposal_error(engine):
    """Execute with no response_proposal yields StepVerdict.ERROR."""
    ctx = _make_ctx()  # no deltas => no response_proposal
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ERROR


async def test_execute_publishes_to_bus(engine):
    """After a successful execute, StepResult.events contains a WorldEvent.

    The DAG (not the engine) is responsible for publishing events from
    StepResult.events to the bus, so the engine itself no longer calls
    bus.publish directly.  This test verifies the event is surfaced in
    the result for the DAG to publish.
    """
    delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice"},
    )
    ctx = _make_ctx(deltas=[delta])
    result = await engine.execute(ctx)

    # The WorldEvent should be present in result.events for DAG publishing
    assert len(result.events) == 1
    assert isinstance(result.events[0], WorldEvent)


async def test_execute_records_to_ledger(engine):
    """When a ledger is injected, StateMutationEntry is appended after execute."""
    mock_ledger = AsyncMock()
    mock_ledger.append = AsyncMock(return_value=1)
    engine._ledger = mock_ledger

    delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice"},
    )
    ctx = _make_ctx(deltas=[delta])
    await engine.execute(ctx)

    mock_ledger.append.assert_called()


# -- State query operations ---------------------------------------------------


async def test_get_entity_found(engine):
    """get_entity returns a stored entity."""
    delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice"},
    )
    await engine.execute(_make_ctx(deltas=[delta]))

    entity = await engine.get_entity("user", EntityId("u-1"))
    assert entity["name"] == "Alice"


async def test_get_entity_not_found(engine):
    """get_entity on missing entity raises EntityNotFoundError."""
    with pytest.raises(EntityNotFoundError):
        await engine.get_entity("user", EntityId("no-such"))


async def test_query_entities(engine):
    """query_entities returns correct entities matching the type."""
    for i in range(3):
        delta = StateDelta(
            entity_type="user",
            entity_id=EntityId(f"u-{i}"),
            operation="create",
            fields={"name": f"User {i}"},
        )
        await engine.execute(
            _make_ctx(
                deltas=[delta],
                request_id=f"req-{i}",
                tick=i + 1,
            )
        )

    users = await engine.query_entities("user")
    assert len(users) == 3


# -- Event operations ---------------------------------------------------------


async def test_commit_event_persists(engine):
    """commit_event persists a WorldEvent to the event log."""
    event = WorldEvent(
        event_type="world.test",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 15, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=1,
        ),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc-1"),
        action="test",
    )
    event_id = await engine.commit_event(event)
    assert event_id is not None

    retrieved = await engine._event_log.get(event_id)
    assert retrieved is not None
    assert retrieved.event_type == "world.test"


async def test_get_causal_chain(engine):
    """Two linked events have a retrievable causal chain."""
    event1 = WorldEvent(
        event_type="world.create",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 15, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=1,
        ),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc-1"),
        action="create",
    )
    await engine.commit_event(event1)

    event2 = WorldEvent(
        event_type="world.update",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 16, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=2,
        ),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc-1"),
        action="update",
        caused_by=event1.event_id,
    )
    await engine.commit_event(event2)

    chain = await engine.get_causal_chain(event2.event_id, "backward")
    # chain should contain at least event1
    [str(e.event_id) if hasattr(e, "event_id") else str(e) for e in chain]
    assert len(chain) >= 1


async def test_get_timeline(engine):
    """get_timeline returns events filtered by time range."""
    t1 = datetime(2026, 1, 10, tzinfo=UTC)
    t2 = datetime(2026, 1, 15, tzinfo=UTC)
    t3 = datetime(2026, 1, 20, tzinfo=UTC)

    for t, tick, action in [(t1, 1, "a1"), (t2, 2, "a2"), (t3, 3, "a3")]:
        event = WorldEvent(
            event_type=f"world.{action}",
            timestamp=Timestamp(
                world_time=t,
                wall_time=datetime.now(UTC),
                tick=tick,
            ),
            actor_id=ActorId("agent-1"),
            service_id=ServiceId("svc-1"),
            action=action,
        )
        await engine.commit_event(event)

    timeline = await engine.get_timeline(
        datetime(2026, 1, 12, tzinfo=UTC),
        datetime(2026, 1, 18, tzinfo=UTC),
    )
    assert len(timeline) == 1
    assert timeline[0].action == "a2"


async def test_on_stop_closes_db(engine):
    """After stop, the database connection is closed."""
    # Grab a reference to the db before stop() sets it to None
    db = engine._db
    assert db is not None

    await engine.stop()

    # The db was closed by _on_stop, so operations should fail
    with pytest.raises(RuntimeError, match="not connected"):
        await db.execute("SELECT 1")


@pytest.mark.asyncio
async def test_execute_transaction_rollback(tmp_path):
    """If a delta fails mid-commit, the entire transaction rolls back."""
    engine = StateEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    config = {"db_path": str(tmp_path / "state.db"), "snapshot_dir": str(tmp_path / "snap")}
    await engine.initialize(config, bus)
    await engine.start()

    try:
        # First: create an entity successfully
        ctx1 = _make_ctx(
            deltas=[
                StateDelta(
                    entity_type="user",
                    entity_id=EntityId("u1"),
                    operation="create",
                    fields={"name": "Alice"},
                ),
            ]
        )
        result1 = await engine.execute(ctx1)
        assert result1.verdict == StepVerdict.ALLOW

        # Second: try to create a DUPLICATE (should fail inside transaction)
        ctx2 = _make_ctx(
            deltas=[
                StateDelta(
                    entity_type="order",
                    entity_id=EntityId("o1"),
                    operation="create",
                    fields={"total": 100},
                ),
                StateDelta(
                    entity_type="user",
                    entity_id=EntityId("u1"),
                    operation="create",
                    fields={"name": "Dupe"},
                ),
            ]
        )
        with pytest.raises(Exception):
            await engine.execute(ctx2)

        # The order entity should NOT exist (transaction rolled back)
        from volnix.core.errors import EntityNotFoundError

        with pytest.raises(EntityNotFoundError):
            await engine.get_entity("order", EntityId("o1"))

        # The original user should still be Alice (untouched)
        user = await engine.get_entity("user", EntityId("u1"))
        assert user["name"] == "Alice"
    finally:
        await engine.stop()


@pytest.mark.asyncio
async def test_fork_raises_not_implemented(engine):
    """fork() raises NotImplementedError (deferred to Phase F5)."""
    from volnix.core.types import SnapshotId

    with pytest.raises(NotImplementedError):
        await engine.fork(SnapshotId("snap_1"))


@pytest.mark.asyncio
async def test_diff_raises_not_implemented(engine):
    """diff() raises NotImplementedError (deferred to Phase F5)."""
    from volnix.core.types import SnapshotId

    with pytest.raises(NotImplementedError):
        await engine.diff(SnapshotId("snap_a"), SnapshotId("snap_b"))
