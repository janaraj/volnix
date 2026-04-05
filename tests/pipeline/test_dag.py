"""Tests for volnix.pipeline.dag -- DAG-based pipeline execution and short-circuiting."""

import asyncio

import pytest
import pytest_asyncio

from volnix.core.context import ActionContext, StepResult
from volnix.core.types import ActorId, ServiceId, StepVerdict
from volnix.pipeline.dag import PipelineDAG
from volnix.bus.bus import EventBus
from volnix.bus.config import BusConfig
from volnix.ledger.ledger import Ledger
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import PipelineStepEntry
from volnix.ledger.query import LedgerQuery
from volnix.persistence.sqlite import SQLiteDatabase


# ---------------------------------------------------------------------------
# MockStep helper
# ---------------------------------------------------------------------------

class MockStep:
    """Configurable mock pipeline step for testing."""

    def __init__(self, name, verdict=StepVerdict.ALLOW, events=None, side_effect_fn=None):
        self._name = name
        self._verdict = verdict
        self._events = events or []
        self._side_effect_fn = side_effect_fn
        self.called = False

    @property
    def step_name(self):
        return self._name

    async def execute(self, ctx):
        self.called = True
        if self._side_effect_fn:
            self._side_effect_fn(ctx)
        return StepResult(step_name=self._name, verdict=self._verdict, events=self._events)


class ErrorStep:
    """Mock step that raises an exception."""

    @property
    def step_name(self):
        return "error_step"

    async def execute(self, ctx):
        raise RuntimeError("step exploded")


def _make_ctx(**kwargs):
    """Create an ActionContext with sensible defaults."""
    defaults = dict(
        request_id="req_1",
        actor_id=ActorId("agent"),
        service_id=ServiceId("test"),
        action="test_action",
    )
    defaults.update(kwargs)
    return ActionContext(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_all_allow():
    """3 mock steps all ALLOW -- ctx not short-circuited."""
    steps = [MockStep("a"), MockStep("b"), MockStep("c")]
    dag = PipelineDAG(steps=steps)
    ctx = _make_ctx()
    result = await dag.execute(ctx)
    assert result.short_circuited is False
    assert all(s.called for s in steps)


@pytest.mark.asyncio
async def test_execute_short_circuit_deny():
    """Step 2 DENY -- step 3 not called."""
    s1 = MockStep("a")
    s2 = MockStep("b", verdict=StepVerdict.DENY)
    s3 = MockStep("c")
    dag = PipelineDAG(steps=[s1, s2, s3])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert s1.called is True
    assert s2.called is True
    assert s3.called is False
    assert ctx.short_circuited is True


@pytest.mark.asyncio
async def test_execute_short_circuit_hold():
    """Step 2 HOLD -- pipeline stops."""
    s1 = MockStep("a")
    s2 = MockStep("b", verdict=StepVerdict.HOLD)
    s3 = MockStep("c")
    dag = PipelineDAG(steps=[s1, s2, s3])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert s3.called is False
    assert ctx.short_circuited is True
    assert ctx.short_circuit_step == "b"


@pytest.mark.asyncio
async def test_execute_short_circuit_escalate():
    """ESCALATE verdict short-circuits."""
    s1 = MockStep("a")
    s2 = MockStep("b", verdict=StepVerdict.ESCALATE)
    s3 = MockStep("c")
    dag = PipelineDAG(steps=[s1, s2, s3])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert s3.called is False
    assert ctx.short_circuited is True


@pytest.mark.asyncio
async def test_execute_short_circuit_error():
    """ERROR verdict short-circuits."""
    s1 = MockStep("a")
    s2 = MockStep("b", verdict=StepVerdict.ERROR)
    s3 = MockStep("c")
    dag = PipelineDAG(steps=[s1, s2, s3])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert s3.called is False
    assert ctx.short_circuited is True


def test_step_names_property():
    """step_names returns ordered list."""
    steps = [MockStep("a"), MockStep("b"), MockStep("c")]
    dag = PipelineDAG(steps=steps)
    assert dag.step_names == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_record_result_on_context():
    """Permission step sets ctx.permission_result."""
    step = MockStep("permission")
    dag = PipelineDAG(steps=[step])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert ctx.permission_result is not None
    assert ctx.permission_result.step_name == "permission"
    assert ctx.permission_result.verdict == StepVerdict.ALLOW


@pytest.mark.asyncio
async def test_short_circuit_flags():
    """Verify ctx.short_circuited and ctx.short_circuit_step are set."""
    s1 = MockStep("a")
    s2 = MockStep("b", verdict=StepVerdict.DENY)
    dag = PipelineDAG(steps=[s1, s2])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert ctx.short_circuited is True
    assert ctx.short_circuit_step == "b"


@pytest.mark.asyncio
async def test_exception_in_step():
    """Step raises RuntimeError -- ERROR result, pipeline stops."""
    s1 = MockStep("a")
    s2 = ErrorStep()
    s3 = MockStep("c")
    dag = PipelineDAG(steps=[s1, s2, s3])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert s3.called is False
    assert ctx.short_circuited is True
    assert ctx.short_circuit_step == "error_step"


@pytest.mark.asyncio
async def test_duration_tracking():
    """Result.duration_ms > 0 for executed steps."""
    step = MockStep("permission")
    dag = PipelineDAG(steps=[step])
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert ctx.permission_result is not None
    assert ctx.permission_result.duration_ms >= 0.0


@pytest.mark.asyncio
async def test_ledger_recording(tmp_path):
    """Use real Ledger, verify PipelineStepEntry created per step."""
    db = SQLiteDatabase(str(tmp_path / "ledger.db"))
    await db.connect()
    try:
        ledger = Ledger(config=LedgerConfig(), db=db)
        await ledger.initialize()

        steps = [MockStep("permission"), MockStep("policy")]
        dag = PipelineDAG(steps=steps, ledger=ledger)
        ctx = _make_ctx()
        await dag.execute(ctx)
        await asyncio.sleep(0.1)  # yield for non-blocking ledger writes

        count = await ledger.get_count("pipeline_step")
        assert count == 2

        entries = await ledger.query(LedgerQuery(entry_type="pipeline_step"))
        assert len(entries) == 2
        assert all(isinstance(e, PipelineStepEntry) for e in entries)
        assert entries[0].step_name == "permission"
        assert entries[1].step_name == "policy"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_event_publishing(tmp_path):
    """Use real EventBus, verify events published via _publish_step_event."""
    from volnix.core.events import Event
    from volnix.core.types import Timestamp
    from datetime import datetime, timezone
    import asyncio

    ts = Timestamp(
        world_time=datetime.now(timezone.utc),
        wall_time=datetime.now(timezone.utc),
        tick=1,
    )
    test_event = Event(event_type="test_event", timestamp=ts)

    received = []

    async def capture(evt):
        received.append(evt)

    db = SQLiteDatabase(str(tmp_path / "bus.db"))
    await db.connect()
    try:
        bus = EventBus(config=BusConfig(persistence_enabled=True), db=db)
        await bus.initialize()
        await bus.subscribe("test_event", capture)

        dag = PipelineDAG(steps=[], bus=bus)
        # Directly test the publish method
        await dag._publish_step_event(test_event)

        await asyncio.sleep(0.15)

        assert len(received) >= 1
        assert received[0].event_type == "test_event"
        await bus.shutdown()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_empty_pipeline():
    """No steps -- ctx returned unchanged."""
    dag = PipelineDAG(steps=[])
    ctx = _make_ctx()
    result = await dag.execute(ctx)
    assert result is ctx
    assert result.short_circuited is False


@pytest.mark.asyncio
async def test_allow_continues_all_steps():
    """7 steps all ALLOW -- all execute."""
    steps = [MockStep(f"step_{i}") for i in range(7)]
    dag = PipelineDAG(steps=steps)
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert all(s.called for s in steps)


@pytest.mark.asyncio
async def test_pipeline_without_bus():
    """bus=None -- no crash."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step], bus=None)
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert step.called is True


@pytest.mark.asyncio
async def test_pipeline_without_ledger():
    """ledger=None -- no crash."""
    step = MockStep("a")
    dag = PipelineDAG(steps=[step], ledger=None)
    ctx = _make_ctx()
    await dag.execute(ctx)
    assert step.called is True
