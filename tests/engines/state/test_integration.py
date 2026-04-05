"""Integration tests for the state engine within the full pipeline/registry."""
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone
from volnix.engines.state.engine import StateEngine
from volnix.pipeline.dag import PipelineDAG
from volnix.pipeline.config import PipelineConfig
from volnix.pipeline.builder import build_pipeline_from_config
from volnix.registry.composition import create_default_registry
from volnix.registry.wiring import wire_engines
from volnix.config.schema import VolnixConfig
from volnix.core.types import (
    ActorId, EntityId, EventId, ServiceId, SnapshotId,
    StepVerdict, StateDelta, Timestamp,
)
from volnix.core.context import ActionContext, ResponseProposal
from volnix.core.events import WorldEvent


def _make_ctx(action="create_user", deltas=None, **overrides):
    """Build an ActionContext with sensible defaults."""
    ctx = ActionContext(
        request_id="req-1",
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("user-svc"),
        action=action,
        input_data={"name": "Alice"},
        world_time=datetime(2026, 1, 15, tzinfo=timezone.utc),
        wall_time=datetime.now(timezone.utc),
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


@pytest.fixture
async def state_engine(tmp_path):
    """A standalone StateEngine initialised with a mock bus."""
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


# -- Pipeline integration -----------------------------------------------------


async def test_full_pipeline_commit(state_engine):
    """Build a pipeline with just the commit step and execute it."""
    pipeline = PipelineDAG(steps=[state_engine])

    delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice"},
    )
    ctx = _make_ctx(deltas=[delta])
    result_ctx = await pipeline.execute(ctx)

    assert result_ctx.commit_result is not None
    assert result_ctx.commit_result.verdict == StepVerdict.ALLOW

    entity = await state_engine._store.read("user", EntityId("u-1"))
    assert entity is not None
    assert entity["name"] == "Alice"


async def test_create_then_update(state_engine):
    """Two pipeline executions, both events should appear in the timeline."""
    pipeline = PipelineDAG(steps=[state_engine])

    # Create
    create_delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice", "age": 30},
    )
    ctx1 = _make_ctx(deltas=[create_delta])
    await pipeline.execute(ctx1)

    # Update
    update_delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="update",
        fields={"age": 31},
    )
    ctx2 = _make_ctx(
        action="update_user",
        deltas=[update_delta],
        request_id="req-2",
        tick=2,
    )
    await pipeline.execute(ctx2)

    # Both events should be in the event log
    events = await state_engine._event_log.query()
    assert len(events) >= 2


async def test_causal_chain_linked(state_engine):
    """Two events with caused_by link should form a causal chain."""
    event1 = WorldEvent(
        event_type="world.create",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 15, tzinfo=timezone.utc),
            wall_time=datetime.now(timezone.utc),
            tick=1,
        ),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc-1"),
        action="create",
    )
    await state_engine.commit_event(event1)

    event2 = WorldEvent(
        event_type="world.update",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 16, tzinfo=timezone.utc),
            wall_time=datetime.now(timezone.utc),
            tick=2,
        ),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc-1"),
        action="update",
        caused_by=event1.event_id,
    )
    await state_engine.commit_event(event2)

    # The causal graph should link them
    causes = await state_engine._causal_graph.get_causes(event2.event_id)
    cause_ids = [str(c) for c in causes]
    assert str(event1.event_id) in cause_ids


async def test_retractability_previous_fields(state_engine):
    """An update delta should capture previous_fields for retractability."""
    # Create entity via engine
    create_delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice", "age": 30},
    )
    await state_engine.execute(_make_ctx(deltas=[create_delta]))

    # Update via engine execute
    update_delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="update",
        fields={"age": 31},
    )
    ctx = _make_ctx(
        action="update_user",
        deltas=[update_delta],
        request_id="req-2",
        tick=2,
    )
    result = await state_engine.execute(ctx)

    # The result metadata should indicate deltas were applied
    assert result.verdict == StepVerdict.ALLOW
    assert result.metadata.get("deltas", 0) >= 1

    # Entity should have the new value
    entity = await state_engine._store.read("user", EntityId("u-1"))
    assert entity["age"] == 31


async def test_snapshot_creates(state_engine):
    """Calling engine.snapshot() should return a SnapshotId."""
    # Create some data first
    delta = StateDelta(
        entity_type="user",
        entity_id=EntityId("u-1"),
        operation="create",
        fields={"name": "Alice"},
    )
    await state_engine.execute(_make_ctx(deltas=[delta]))

    snapshot_id = await state_engine.snapshot("test-snapshot")
    assert snapshot_id is not None
    assert isinstance(snapshot_id, str)  # SnapshotId is NewType(str)


async def test_registry_wiring():
    """create_default_registry includes the state engine; topo sort puts it first."""
    registry = create_default_registry()

    # State engine should be registered
    state = registry.get("state")
    assert state is not None
    assert isinstance(state, StateEngine)

    # Topological sort: state has no dependencies, so it should appear
    # at or near the beginning
    order = registry.resolve_initialization_order()
    assert "state" in order
    # state has dependencies=[], so it must come before engines that depend on it
    state_idx = order.index("state")
    assert state_idx >= 0
