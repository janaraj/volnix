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
    BaseEngine,
    EntityId,
    Event,
    EventId,
    PipelineStep,
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
        """Create an immutable point-in-time snapshot of the world state."""
        from terrarium.core.types import RunId

        run_id = RunId(self._config.get("run_id", "default"))
        return await self._snapshot_store.save_snapshot(run_id, label, self._db)

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
