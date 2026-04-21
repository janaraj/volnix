"""State engine implementation.

The state engine is the root dependency for all other engines. It owns
the entity store, the append-only event log, the causal graph, and
snapshot/fork/diff operations.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from volnix.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    EntityId,
    Event,
    EventId,
    ServiceId,
    SnapshotId,
    StateDelta,
    StepResult,
    StepVerdict,
    Timestamp,
    WorldEvent,
    WorldId,
)
from volnix.core.errors import EntityNotFoundError, TrajectoryFieldNotFound
from volnix.engines.state.trajectory import (
    _MISSING,
    TrajectoryPoint,
    _extract_dotted,
)

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
        from volnix.engines.state.causal_graph import CausalGraph
        from volnix.engines.state.config import StateConfig
        from volnix.engines.state.event_log import EventLog
        from volnix.engines.state.migrations import STATE_MIGRATIONS
        from volnix.engines.state.store import EntityStore
        from volnix.persistence.migrations import MigrationRunner
        from volnix.persistence.snapshot import SnapshotStore

        # Parse config through typed model (no hardcoded defaults in engine)
        config = StateConfig(**{k: v for k, v in self._config.items() if not k.startswith("_")})

        # Fix #8: Use persistence layer factory instead of constructing
        # SQLiteDatabase directly. This keeps DB construction confined
        # to the persistence module (source guard allowlist).
        injected_db = self._config.get("_db")
        if injected_db is not None:
            self._db = injected_db
        else:
            from volnix.persistence.manager import create_database

            Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await create_database(config.db_path)
        try:
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
            from volnix.persistence.config import PersistenceConfig

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

    async def reconfigure(self, db_path: str) -> None:
        """Switch the backing database to a new file path.

        Closes the current connection, opens a fresh DB at *db_path*,
        runs migrations, and reinitialises all sub-components including
        the snapshot store.

        Used by ``VolnixApp`` to switch between a world's state.db
        and a run's state.db during the world/run lifecycle.
        """
        from volnix.engines.state.causal_graph import CausalGraph
        from volnix.engines.state.event_log import EventLog
        from volnix.engines.state.migrations import STATE_MIGRATIONS
        from volnix.engines.state.store import EntityStore
        from volnix.persistence.config import PersistenceConfig
        from volnix.persistence.manager import create_database
        from volnix.persistence.migrations import MigrationRunner
        from volnix.persistence.snapshot import SnapshotStore

        # Close current DB
        if self._db is not None:
            await self._db.close()
            self._db = None

        # Open new DB at the requested path
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._db = await create_database(db_path)

            # Apply migrations on the new DB
            runner = MigrationRunner(self._db)
            for migration in STATE_MIGRATIONS:
                runner.register(migration)
            await runner.migrate_up()

            # Reinitialise sub-components on the new DB
            self._store = EntityStore(self._db)
            self._event_log = EventLog(self._db)
            self._causal_graph = CausalGraph(self._db)

            # Reinitialise snapshot store to use the same directory as the DB
            snapshot_dir = str(db_dir / "snapshots")
            self._snapshot_store = SnapshotStore(PersistenceConfig(base_dir=snapshot_dir))
        except Exception:
            if self._db is not None:
                await self._db.close()
                self._db = None
            raise

        logger.info("StateEngine reconfigured to %s", db_path)

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
                        logger.warning(
                            "Delete of non-existent entity %s/%s — skipping ledger entry",
                            delta.entity_type,
                            delta.entity_id,
                        )
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
            wall_now = datetime.now(UTC)
            if ctx.world_time is None:
                logger.warning(
                    "ActionContext missing world_time — using wall clock (breaks replay determinism)"
                )

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
                target_entity=ctx.target_entity
                or (applied_deltas[0].entity_id if applied_deltas else None),
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
            from volnix.ledger.entries import StateMutationEntry

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

        # 5. Include proposed_events from the responder (Fix #1)
        #    These are synthetic events the responder wants to emit alongside
        #    the main action event (e.g., side effects, notifications).
        all_events = [event]
        proposed_events = getattr(proposal, "proposed_events", None)
        if proposed_events:
            for pe in proposed_events:
                await self._event_log.append(pe)
            all_events.extend(proposed_events)

        # Events returned in StepResult so the DAG publishes them.
        # No self.publish() here to avoid duplicate delivery.
        return StepResult(
            step_name="commit",
            verdict=StepVerdict.ALLOW,
            events=all_events,
            metadata={
                "event_id": str(event.event_id),
                "deltas": len(applied_deltas),
            },
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

    async def list_entity_types(self) -> list[str]:
        """Return distinct entity types in the store."""
        return await self._store.list_entity_types()

    async def populate_entities(self, entities: dict[str, list[dict[str, Any]]]) -> int:
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
        now = datetime.now(UTC)

        async with self._db.transaction():
            for entity_type, entity_list in entities.items():
                for entity in entity_list:
                    entity_id = EntityId(entity.get("id", f"{entity_type}_{count}"))
                    fields = {k: v for k, v in entity.items() if not k.startswith("_")}
                    await self._store.create(entity_type, entity_id, fields)
                    count += 1

                    # Create WorldEvent for traceability
                    event = WorldEvent(
                        event_type=f"world.populate.{entity_type}",
                        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                        actor_id=ActorId("world_compiler"),
                        service_id=ServiceId("world_compiler"),
                        action="populate",
                        target_entity=entity_id,
                        input_data=fields,
                        state_deltas=[
                            {
                                "entity_type": entity_type,
                                "entity_id": str(entity_id),
                                "operation": "create",
                                "fields": fields,
                                "previous_fields": None,
                            }
                        ],
                        outcome="success",
                    )
                    await self._event_log.append(event)
                    created_events.append(event)

        # Record to ledger (outside transaction — ledger is separate DB)
        if self._ledger is not None:
            from volnix.ledger.entries import StateMutationEntry

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

    async def snapshot(self, label: str = "default", tick: int = 0) -> SnapshotId:
        """Create an immutable point-in-time snapshot of the world state.

        Records to Ledger (``SnapshotEntry``) and publishes to
        EventBus. The ``tick`` kwarg stamps the logical tick onto
        the ledger entry so consumers auditing snapshots know WHEN
        the snapshot was taken in simulation time, not just the
        label (PMF Plan Phase 4C Step 9). Defaults to ``0``
        preserving pre-Step-9 behaviour byte-identical.

        Args:
            label: Human-readable identifier for this snapshot.
            tick: Logical tick at snapshot capture. ``0`` when
                unknown / pre-simulation.
        """
        from volnix.core.types import RunId

        run_id = RunId(self._config.get("run_id", "default"))
        snapshot_id = await self._snapshot_store.save_snapshot(run_id, label, self._db)

        # Record to ledger (SnapshotEntry exists but was never used — now it is)
        if self._ledger is not None:
            from volnix.ledger.entries import SnapshotEntry

            entity_count = await self._get_total_entity_count()
            entry = SnapshotEntry(
                snapshot_id=snapshot_id,
                run_id=run_id,
                tick=tick,
                entity_count=entity_count,
            )
            await self._ledger.append(entry)

        logger.info("Snapshot '%s' created at tick %d: %s", label, tick, snapshot_id)
        return snapshot_id

    async def _get_total_entity_count(self) -> int:
        """Count all entities across all types for snapshot metadata."""
        row = await self._db.fetchone("SELECT COUNT(*) as cnt FROM entities")
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

    async def get_trajectory(
        self,
        entity_id: EntityId,
        field_path: str,
        tick_range: tuple[int, int] | None = None,
    ) -> list[TrajectoryPoint]:
        """Reconstruct the historical value sequence of one field
        on one entity from committed ``state_deltas`` (PMF Plan
        Phase 4C Step 9).

        Walks ``WorldEvent.state_deltas`` in tick order for every
        committed event within ``tick_range``; for each delta whose
        ``entity_id`` matches, extracts ``field_path`` from
        ``delta["fields"]`` via dotted-path navigation; yields one
        :class:`TrajectoryPoint` per mutation that set the field.

        Args:
            entity_id: The entity being tracked. Actors are entities
                in volnix — pass ``ActorId("npc-alice")`` directly
                if tracking an actor's own state field.
            field_path: Dotted path on ``delta["fields"]``
                (e.g., ``"budget.remaining_usd"``). Numeric segments
                / list indexing NOT supported — reserved for a later
                step (audit-fold M1).
            tick_range: Inclusive ``(start, end)`` tick bounds.
                ``None`` includes all ticks. ``start > end`` raises
                ``ValueError``.

        Returns:
            Ordered trajectory points. Empty list when no matching
            events / deltas / field-values exist — ALL data-absence
            cases return ``[]`` (never raise). Only malformed
            ``field_path`` (empty or containing empty segments from
            ``..``) raises :class:`TrajectoryFieldNotFound`.

        Raises:
            TrajectoryFieldNotFound: When ``field_path`` is empty,
                purely whitespace, or contains empty segments
                (e.g. ``".foo"`` or ``"a..b"``).
            ValueError: When ``tick_range`` has ``start > end``.
        """
        # Path-level validation — the ONLY case that raises
        # (audit-fold H1/M1). Data absence is empty-list, not exception.
        path = field_path.strip() if isinstance(field_path, str) else ""
        if not path:
            raise TrajectoryFieldNotFound("field_path must be a non-empty dotted string")
        segments = path.split(".")
        if any(not seg.strip() for seg in segments):
            raise TrajectoryFieldNotFound(
                f"field_path {field_path!r} contains empty segments — "
                f"reject before journal walk to avoid silent misreads"
            )

        start_tick: int | None = None
        end_tick: int | None = None
        if tick_range is not None:
            start_tick, end_tick = tick_range
            if start_tick > end_tick:
                raise ValueError(f"tick_range start ({start_tick}) must be <= end ({end_tick})")

        events = await self._event_log.query_by_tick_range(start_tick=start_tick, end_tick=end_tick)
        target = str(entity_id)
        results: list[TrajectoryPoint] = []
        for evt in events:
            # Only WorldEvent subclasses carry state_deltas. Plain
            # Event instances (permission / policy / etc.) don't.
            deltas = getattr(evt, "state_deltas", None) or []
            for delta in deltas:
                if str(delta.get("entity_id", "")) != target:
                    continue
                value = _extract_dotted(delta.get("fields") or {}, segments)
                if value is _MISSING:
                    continue
                results.append(
                    TrajectoryPoint(
                        tick=evt.timestamp.tick,
                        value=value,
                        event_id=evt.event_id,
                        entity_id=EntityId(target),
                        field_path=path,
                    )
                )
        return results
