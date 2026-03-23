"""Contract guardrails for published backend behaviors."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from terrarium.core.context import ResponseProposal, StepResult
from terrarium.core.events import Event, WorldEvent
from terrarium.core.types import (
    ActorId,
    EntityId,
    ServiceId,
    StateDelta,
    StepVerdict,
    Timestamp,
)
from terrarium.packs.base import ServicePack
from terrarium.packs.registry import PackRegistry
from terrarium.packs.runtime import PackRuntime
from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.snapshot import SnapshotStore
from terrarium.persistence.sqlite import SQLiteDatabase
from tests.helpers.guardrails import staged_guardrail

pytestmark = [pytest.mark.architecture, pytest.mark.contract]


def _timestamp() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=1)


def test_step_result_events_accept_event_objects():
    event = Event(event_type="test.event", timestamp=_timestamp())
    result = StepResult(step_name="demo", verdict=StepVerdict.ALLOW, events=[event])
    assert result.events == [event]


@staged_guardrail(reason="ResponseProposal.proposed_events still rejects concrete Event objects")
def test_response_proposal_accepts_concrete_events():
    event = WorldEvent(
        event_type="world.synthetic",
        timestamp=_timestamp(),
        actor_id=ActorId("actor-test"),
        service_id=ServiceId("email"),
        action="email_send",
        input_data={},
    )
    proposal = ResponseProposal(response_body={}, proposed_events=[event])
    assert proposal.proposed_events == [event]


@staged_guardrail(reason="State commit path still ignores responder-proposed events")
@pytest.mark.asyncio
async def test_commit_step_honors_proposed_events(app, make_action_context):
    state = app.registry.get("state")
    extra_event = WorldEvent(
        event_type="world.synthetic",
        timestamp=_timestamp(),
        actor_id=ActorId("actor-test"),
        service_id=ServiceId("email"),
        action="email_send",
        input_data={"source": "proposal"},
    )
    proposal = ResponseProposal.model_construct(
        response_body={},
        proposed_events=[extra_event],
        proposed_state_deltas=[],
        proposed_side_effects=[],
        fidelity=None,
        fidelity_warning=None,
    )
    ctx = make_action_context(service_id=ServiceId("email"), action="email_send")
    ctx.response_proposal = proposal

    result = await state.execute(ctx)
    timeline = await state.get_timeline()

    assert any(event.event_type == "world.synthetic" for event in result.events)
    assert any(event.event_type == "world.synthetic" for event in timeline)


@staged_guardrail(reason="Snapshot labels are not yet confined to the snapshots directory")
@pytest.mark.asyncio
async def test_snapshot_labels_preserve_path_containment(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path / "data"))
    store = SnapshotStore(config)
    db = SQLiteDatabase(str(tmp_path / "source.db"))
    await db.connect()
    try:
        await db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        await db.execute("INSERT INTO items (name) VALUES (?)", ("alpha",))
        snapshot_id = await store.save_snapshot("run-1", "../../escape", db)

        snapshots_dir = (tmp_path / "data" / "snapshots").resolve()
        db_path = (tmp_path / "data" / "snapshots" / f"{snapshot_id}.db").resolve()
        meta_path = (tmp_path / "data" / "snapshots" / f"{snapshot_id}.json").resolve()

        assert db_path.is_relative_to(snapshots_dir)
        assert meta_path.is_relative_to(snapshots_dir)
    finally:
        await db.close()


class ConstraintUpdatePack(ServicePack):
    """Pack that exposes update-schema constraints the runtime should enforce."""

    pack_name = "constraint_update"
    category = "test"
    fidelity_tier = 1

    def get_tools(self):
        return [
            {
                "name": "constraint_update",
                "description": "Update entity with constrained fields",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }
        ]

    def get_entity_schemas(self):
        return {
            "ticket": {
                "type": "object",
                "required": ["status", "priority"],
                "properties": {
                    "status": {"type": "string", "enum": ["draft", "sent"]},
                    "priority": {"type": "integer", "minimum": 0, "maximum": 3},
                },
            }
        }

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        return ResponseProposal(
            response_body={"status": "updated"},
            proposed_state_deltas=[
                StateDelta(
                    entity_type="ticket",
                    entity_id=EntityId("ticket-1"),
                    operation="update",
                    fields={"status": "broken", "priority": -1},
                    previous_fields={"status": "draft", "priority": 1},
                )
            ],
        )


@staged_guardrail(reason="PackRuntime update validation still skips enum/min/max constraints")
@pytest.mark.asyncio
async def test_pack_runtime_enforces_update_schema_constraints():
    registry = PackRegistry()
    registry.register(ConstraintUpdatePack())
    runtime = PackRuntime(registry)

    from terrarium.core.errors import ValidationError

    with pytest.raises(ValidationError):
        await runtime.execute("constraint_update", {})
