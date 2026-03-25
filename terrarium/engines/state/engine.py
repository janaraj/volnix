"""State engine implementation.

The state engine is the root dependency for all other engines. It owns
the entity store, the append-only event log, the causal graph, and
snapshot/fork/diff operations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    EntityId,
    Event,
    EventId,
    PipelineStep,
    ServiceId,
    SnapshotId,
    StateDelta,
    StepResult,
    StepVerdict,
    Timestamp,
    WorldEvent,
    WorldId,
)
from terrarium.core.errors import EntityNotFoundError

logger = logging.getLogger(__name__)


class StateEngine(BaseEngine):
    """Authoritative world-state store and event ledger.

    Also acts as the ``commit`` pipeline step, persisting approved
    mutations at the end of the governance pipeline.
    """

    engine_name: ClassVar[str] = "state"
    subscriptions: ClassVar[list[str]] = []  # C1: no inbound event processing yet (Phase C3+)
    dependencies: ClassVar[list[str]] = []

    def __init__(self) -> None:
        super().__init__()
        self._db: Any = None
        self._store: Any = None
        self._event_log: Any = None
        self._causal_graph: Any = None
        self._snapshot_store: Any = None
        self._ledger: Any = None

    # -- BaseEngine hooks ------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Set up the database, apply migrations, and wire sub-components."""
        from terrarium.engines.state.migrations import STATE_MIGRATIONS
        from terrarium.engines.state.store import EntityStore
        from terrarium.engines.state.event_log import EventLog
        from terrarium.engines.state.causal_graph import CausalGraph
        from terrarium.persistence.migrations import MigrationRunner
        from terrarium.persistence.sqlite import SQLiteDatabase
        from terrarium.persistence.snapshot import SnapshotStore
        from terrarium.engines.state.config import StateConfig

        # Parse config through typed model (no hardcoded defaults in engine)
        config = StateConfig(**{k: v for k, v in self._config.items() if not k.startswith("_")})
        Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._db = SQLiteDatabase(config.db_path, wal_mode=True)
        try:
            await self._db.connect()

            # Apply migrations (centralised schema management)
            runner = MigrationRunner(self._db)
            for migration in STATE_MIGRATIONS:
                runner.register(migration)
            await runner.migrate_up()

            # Initialise business-logic components (NO table creation here)
            self._store = EntityStore(self._db)
            self._event_log = EventLog(self._db)
            self._causal_graph = CausalGraph(self._db)

            # Snapshot support
            from terrarium.persistence.config import PersistenceConfig
            self._snapshot_store = SnapshotStore(PersistenceConfig(base_dir=config.snapshot_dir))
        except Exception:
            if self._db is not None:
                await self._db.close()
                self._db = None
            raise

    async def _on_stop(self) -> None:
        """Close the backing database."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        logger.debug("StateEngine received event %s (%s)", event.event_id, event.event_type)

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "commit"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the commit pipeline step.

        Applies proposed state deltas inside a transaction, persists the
        world event and causal edges, records to ledger, and publishes to
        the bus.
        """
        proposal = ctx.response_proposal
        if proposal is None:
            return StepResult(
                step_name="commit",
                verdict=StepVerdict.ERROR,
                message="No response proposal",
            )

        async with self._db.transaction():
            # 1. Apply state deltas (capture previous_fields for retractability)
            applied_deltas: list[StateDelta] = []
            for delta in proposal.proposed_state_deltas or []:
                if delta.operation == "create":
                    await self._store.create(delta.entity_type, delta.entity_id, delta.fields)
                    applied_deltas.append(delta)
                elif delta.operation == "update":
                    previous = await self._store.update(
                        delta.entity_type, delta.entity_id, delta.fields
                    )
                    applied_deltas.append(
                        StateDelta(
                            entity_type=delta.entity_type,
                            entity_id=delta.entity_id,
                            operation="update",
                            fields=delta.fields,
                            previous_fields=previous,
                        )
                    )
                elif delta.operation == "delete":
                    previous = await self._store.delete(delta.entity_type, delta.entity_id)
                    if previous is None:
                        logger.warning("Delete of non-existent entity %s/%s — skipping ledger entry",
                                       delta.entity_type, delta.entity_id)
                        continue
                    applied_deltas.append(
                        StateDelta(
                            entity_type=delta.entity_type,
                            entity_id=delta.entity_id,
                            operation="delete",
                            fields={},
                            previous_fields=previous,
                        )
                    )

            # 2. Create and persist the world event
            wall_now = datetime.now(timezone.utc)
            if ctx.world_time is None:
                logger.warning("ActionContext missing world_time — using wall clock (breaks replay determinism)")

            # Derive outcome from pipeline verdicts
            outcome = "success"
            if ctx.short_circuited:
                step = ctx.short_circuit_step or ""
                if step == "policy":
                    verdict = ctx.policy_result.verdict if ctx.policy_result else None
                    if verdict == StepVerdict.DENY:
                        outcome = "blocked"
                    elif verdict == StepVerdict.HOLD:
                        outcome = "held"
                    elif verdict == StepVerdict.ESCALATE:
                        outcome = "escalated"
                    else:
                        outcome = "policy_hit"
                elif step == "permission":
                    outcome = "denied"
                elif step == "budget":
                    outcome = "budget_exhausted"
                else:
                    outcome = "error"

            # Serialize applied state deltas
            delta_dicts = [
                {
                    "entity_type": d.entity_type,
                    "entity_id": str(d.entity_id),
                    "operation": d.operation,
                    "fields": d.fields,
                    "previous_fields": d.previous_fields,
                }
                for d in applied_deltas
            ]

            # Extract cost and response body from ActionContext
            cost_dict = None
            if ctx.computed_cost is not None:
                cost_dict = ctx.computed_cost.model_dump(mode="json")

            response_body = None
            if proposal is not None:
                response_body = proposal.response_body

            event = WorldEvent(
                event_type=f"world.{ctx.action}",
                timestamp=Timestamp(
                    world_time=ctx.world_time if ctx.world_time is not None else wall_now,
                    wall_time=ctx.wall_time if ctx.wall_time is not None else wall_now,
                    tick=ctx.tick if ctx.tick is not None else 0,
                ),
                actor_id=ctx.actor_id,
                service_id=ctx.service_id,
                action=ctx.action,
                # Use explicit target or infer from first delta
                target_entity=ctx.target_entity or (applied_deltas[0].entity_id if applied_deltas else None),
                input_data=ctx.input_data or {},
                response_body=response_body,
                outcome=outcome,
                state_deltas=delta_dicts,
                cost=cost_dict,
                run_id=ctx.run_id if ctx.run_id else None,
            )
            await self._event_log.append(event)

            # 3. Record causal edges
            if event.caused_by:
                await self._causal_graph.add_edge(event.caused_by, event.event_id)
            for cause_id in event.causes:
                await self._causal_graph.add_edge(cause_id, event.event_id)

        # 4. Record to ledger (OUTSIDE transaction -- ledger is a separate DB)
        if self._ledger is not None:
            from terrarium.ledger.entries import StateMutationEntry

            for delta in applied_deltas:
                entry = StateMutationEntry(
                    entity_type=delta.entity_type,
                    entity_id=delta.entity_id,
                    operation=delta.operation,
                    before=delta.previous_fields,
                    after=delta.fields if delta.operation != "delete" else None,
                    event_id=event.event_id,
                )
                await self._ledger.append(entry)

        # 5. Event is returned in StepResult.events so the DAG publishes it
        #    once via _publish_step_event(). No self.publish() here to avoid
        #    duplicate delivery.

        return StepResult(
            step_name="commit",
            verdict=StepVerdict.ALLOW,
            events=[event],
            metadata={"event_id": str(event.event_id), "deltas": len(applied_deltas)},
        )

    # -- State operations ------------------------------------------------------

    async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict[str, Any]:
        """Retrieve a single entity by type and id."""
        result = await self._store.read(entity_type, entity_id)
        if result is None:
            raise EntityNotFoundError(f"Entity not found: {entity_type}/{entity_id}")
        return result

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Query entities of a given type with optional filters."""
        return await self._store.query(entity_type, filters)

    async def populate_entities(
        self, entities: dict[str, list[dict[str, Any]]]
    ) -> int:
        """Bulk-create entities for world generation.

        Creates entities in EntityStore AND records each creation to:
        - Event Log (WorldEvent per entity — full audit trail)
        - Ledger (StateMutationEntry per entity — queryable history)
        - EventBus (published for subscribers)

        This ensures world generation is fully traceable, just like
        pipeline-driven entity creation via execute().

        Parameters
        ----------
        entities:
            Dict mapping entity_type -> list of entity dicts.
            Each entity dict MUST have an "id" field.

        Returns
        -------
        int:
            Total number of entities created.
        """
        count = 0
        created_events: list[WorldEvent] = []
        now = datetime.now(timezone.utc)

        async with self._db.transaction():
            for entity_type, entity_list in entities.items():
                for entity in entity_list:
                    entity_id = EntityId(
                        entity.get("id", f"{entity_type}_{count}")
                    )
                    fields = {
                        k: v
                        for k, v in entity.items()
                        if not k.startswith("_")
                    }
                    await self._store.create(entity_type, entity_id, fields)
                    count += 1

                    # Create WorldEvent for traceability
                    event = WorldEvent(
                        event_type=f"world.populate.{entity_type}",
                        timestamp=Timestamp(
                            world_time=now, wall_time=now, tick=0
                        ),
                        actor_id=ActorId("world_compiler"),
                        service_id=ServiceId("world_compiler"),
                        action="populate",
                        target_entity=entity_id,
                        input_data=fields,
                        state_deltas=[{
                            "entity_type": entity_type,
                            "entity_id": str(entity_id),
                            "operation": "create",
                            "fields": fields,
                            "previous_fields": None,
                        }],
                        outcome="success",
                    )
                    await self._event_log.append(event)
                    created_events.append(event)

        # Record to ledger (outside transaction — ledger is separate DB)
        if self._ledger is not None:
            from terrarium.ledger.entries import StateMutationEntry

            for event in created_events:
                entry = StateMutationEntry(
                    entity_type=event.event_type.rsplit(".", 1)[-1],
                    entity_id=event.target_entity or EntityId(""),
                    operation="create",
                    before=None,
                    after=event.input_data,
                    event_id=event.event_id,
                )
                await self._ledger.append(entry)

        # Publish to bus for subscribers
        for event in created_events:
            await self.publish(event)

        logger.info(
            "Populated %d entities across %d types (traced: %d events)",
            count,
            len(entities),
            len(created_events),
        )
        return count

    async def propose_mutation(self, deltas: list[StateDelta]) -> list[StateDelta]:
        """Validate proposed state mutations (dry run).

        Currently returns the deltas as-is; future versions may perform
        domain-specific validation.
        """
        return deltas

    async def commit_event(self, event: Event) -> EventId:
        """Persist an event and record its causal edges atomically."""
        async with self._db.transaction():
            event_id = await self._event_log.append(event)
            caused_by = getattr(event, "caused_by", None)
            causes = getattr(event, "causes", [])
            if caused_by:
                await self._causal_graph.add_edge(caused_by, event.event_id)
            for cause_id in causes:
                await self._causal_graph.add_edge(cause_id, event.event_id)
        return event_id

    async def snapshot(self, label: str) -> SnapshotId:
        """Create an immutable point-in-time snapshot of the world state.

        Records to Ledger (SnapshotEntry) and publishes to EventBus.
        """
        from terrarium.core.types import RunId

        run_id = RunId(self._config.get("run_id", "default"))
        snapshot_id = await self._snapshot_store.save_snapshot(
            run_id, label, self._db
        )

        # Record to ledger (SnapshotEntry exists but was never used — now it is)
        if self._ledger is not None:
            from terrarium.ledger.entries import SnapshotEntry

            entity_count = await self._get_total_entity_count()
            entry = SnapshotEntry(
                snapshot_id=snapshot_id,
                run_id=run_id,
                tick=0,
                entity_count=entity_count,
            )
            await self._ledger.append(entry)

        logger.info(
            "Snapshot '%s' created: %s", label, snapshot_id
        )
        return snapshot_id

    async def _get_total_entity_count(self) -> int:
        """Count all entities across all types for snapshot metadata."""
        row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM entities"
        )
        return row["cnt"] if row else 0

    async def fork(self, snapshot_id: SnapshotId) -> WorldId:
        """Fork a new world from an existing snapshot.

        Raises NotImplementedError — full fork requires a new StateEngine
        instance backed by the snapshot. Deferred to Phase F5.
        """
        raise NotImplementedError("World forking is deferred to Phase F5")

    async def diff(
        self, snapshot_a: SnapshotId, snapshot_b: SnapshotId
    ) -> list[StateDelta] | dict[str, Any]:
        """Compute the set of deltas between two snapshots.

        Raises NotImplementedError — structural diff requires loading and
        comparing two databases. Deferred to Phase F5.
        """
        raise NotImplementedError("Snapshot diff is deferred to Phase F5")

    async def get_causal_chain(
        self, event_id: EventId, direction: str = "backward"
    ) -> list[WorldEvent]:
        """Walk the causal ancestry or descendants of an event."""
        chain_ids = await self._causal_graph.get_chain(event_id, direction)
        events: list[WorldEvent] = []
        for eid in chain_ids:
            evt = await self._event_log.get(eid)
            if evt is not None and isinstance(evt, WorldEvent):
                events.append(evt)
        return events

    async def get_timeline(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        entity_id: EntityId | None = None,
    ) -> list[Event]:
        """Return the ordered event timeline, optionally filtered by entity and time range."""
        events = await self._event_log.query(start=start, end=end, entity_id=entity_id)
        return events
