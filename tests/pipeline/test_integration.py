"""Integration tests for the pipeline module.

Uses real EventBus (A3) and real Ledger (A4) implementations with
SQLite-backed persistence to verify end-to-end pipeline behaviour.
"""

import asyncio

import pytest

from terrarium.bus.bus import EventBus
from terrarium.bus.config import BusConfig
from terrarium.core.context import ActionContext, ResponseProposal, StepResult
from terrarium.core.events import Event
from terrarium.core.types import (
    ActorId,
    ServiceId,
    SideEffect,
    StepVerdict,
    Timestamp,
)
from terrarium.ledger.config import LedgerConfig
from terrarium.ledger.entries import PipelineStepEntry
from terrarium.ledger.ledger import Ledger
from terrarium.ledger.query import LedgerQuery
from terrarium.persistence.sqlite import SQLiteDatabase
from terrarium.pipeline.dag import PipelineDAG
from terrarium.pipeline.side_effects import SideEffectProcessor

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockStep:
    """Configurable mock pipeline step."""

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


class MockResponderStep:
    """Mock responder that produces side effects."""

    def __init__(self, side_effects=None, max_produces=None):
        self._side_effects = side_effects or []
        self._max_produces = max_produces
        self.call_count = 0

    @property
    def step_name(self):
        return "responder"

    async def execute(self, ctx):
        self.call_count += 1
        if self._max_produces is None or self.call_count <= self._max_produces:
            ctx.response_proposal = ResponseProposal(
                proposed_side_effects=self._side_effects,
            )
        else:
            ctx.response_proposal = ResponseProposal()
        return StepResult(step_name="responder", verdict=StepVerdict.ALLOW)


def _make_ctx(**kwargs):
    defaults = dict(
        request_id="req_1",
        actor_id=ActorId("agent"),
        service_id=ServiceId("test"),
        action="test_action",
    )
    defaults.update(kwargs)
    return ActionContext(**defaults)


def _make_timestamp():
    now = datetime.now(timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_with_real_bus(tmp_path):
    """Events reach bus subscribers via _publish_step_event."""
    db = SQLiteDatabase(str(tmp_path / "bus.db"))
    await db.connect()
    try:
        bus = EventBus(config=BusConfig(persistence_enabled=True), db=db)
        await bus.initialize()

        received = []

        async def capture(evt):
            received.append(evt)

        await bus.subscribe("test_event", capture)

        test_event = Event(event_type="test_event", timestamp=_make_timestamp())
        # Directly test event publishing through the DAG
        dag = PipelineDAG(steps=[MockStep("a")], bus=bus)
        await dag._publish_step_event(test_event)

        await asyncio.sleep(0.15)

        assert len(received) >= 1
        assert received[0].event_type == "test_event"

        await bus.shutdown()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_pipeline_with_real_ledger(tmp_path):
    """PipelineStepEntry in ledger after execution."""
    db = SQLiteDatabase(str(tmp_path / "ledger.db"))
    await db.connect()
    try:
        ledger = Ledger(config=LedgerConfig(), db=db)
        await ledger.initialize()

        steps = [MockStep("permission"), MockStep("policy"), MockStep("budget")]
        dag = PipelineDAG(steps=steps, ledger=ledger)

        ctx = _make_ctx()
        await dag.execute(ctx)

        count = await ledger.get_count("pipeline_step")
        assert count == 3

        entries = await ledger.query(LedgerQuery(entry_type="pipeline_step"))
        assert len(entries) == 3
        names = [e.step_name for e in entries]
        assert names == ["permission", "policy", "budget"]
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_pipeline_bus_and_ledger(tmp_path):
    """Both bus and ledger work together."""
    db = SQLiteDatabase(str(tmp_path / "both.db"))
    await db.connect()
    try:
        bus = EventBus(config=BusConfig(persistence_enabled=True), db=db)
        await bus.initialize()

        ledger = Ledger(config=LedgerConfig(), db=db)
        await ledger.initialize()

        received = []

        async def capture(evt):
            received.append(evt)

        await bus.subscribe("test_event", capture)

        steps = [MockStep("permission"), MockStep("policy")]
        dag = PipelineDAG(steps=steps, bus=bus, ledger=ledger)

        ctx = _make_ctx()
        await dag.execute(ctx)

        # Also publish an event through the bus via DAG
        test_event = Event(event_type="test_event", timestamp=_make_timestamp())
        await dag._publish_step_event(test_event)

        await asyncio.sleep(0.15)

        # Bus received event
        assert len(received) >= 1

        # Ledger recorded both steps
        count = await ledger.get_count("pipeline_step")
        assert count == 2

        await bus.shutdown()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_side_effect_full_cycle(tmp_path):
    """SE re-enters pipeline; ledger records both main + SE."""
    db = SQLiteDatabase(str(tmp_path / "se.db"))
    await db.connect()
    try:
        ledger = Ledger(config=LedgerConfig(), db=db)
        await ledger.initialize()

        nested_se = SideEffect(
            effect_type="notify",
            target_service=ServiceId("notifier"),
            parameters={"msg": "hello"},
        )
        responder = MockResponderStep(side_effects=[nested_se], max_produces=1)
        dag = PipelineDAG(steps=[responder], ledger=ledger)

        # Execute main pipeline
        ctx = _make_ctx()
        await dag.execute(ctx)

        # Process side effects
        proc = SideEffectProcessor(dag, max_depth=5)
        for se in ctx.response_proposal.proposed_side_effects:
            await proc.enqueue(se, ctx)
        se_count = await proc.process_all()

        assert se_count >= 1

        # Ledger has entries for main pipeline + side effect pipelines
        total = await ledger.get_count("pipeline_step")
        assert total >= 2  # At least main + 1 SE execution
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_all_verdict_types(tmp_path):
    """ALLOW, DENY, HOLD, ERROR all record correctly to ledger."""
    db = SQLiteDatabase(str(tmp_path / "verdicts.db"))
    await db.connect()
    try:
        ledger = Ledger(config=LedgerConfig(), db=db)
        await ledger.initialize()

        verdicts_to_test = [
            StepVerdict.ALLOW,
            StepVerdict.DENY,
            StepVerdict.HOLD,
            StepVerdict.ERROR,
        ]

        for verdict in verdicts_to_test:
            step = MockStep("permission", verdict=verdict)
            dag = PipelineDAG(steps=[step], ledger=ledger)
            ctx = _make_ctx()
            await dag.execute(ctx)

        entries = await ledger.query(LedgerQuery(entry_type="pipeline_step"))
        assert len(entries) == 4

        recorded_verdicts = [e.verdict for e in entries]
        assert recorded_verdicts == ["allow", "deny", "hold", "error"]
    finally:
        await db.close()
