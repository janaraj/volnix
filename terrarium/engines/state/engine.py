"""State engine implementation.

The state engine is the root dependency for all other engines. It owns
the entity store, the append-only event log, the causal graph, and
snapshot/fork/diff operations.
"""

from __future__ import annotations

from datetime import datetime
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
    WorldEvent,
    WorldId,
)


class StateEngine(BaseEngine):
    """Authoritative world-state store and event ledger.

    Also acts as the ``commit`` pipeline step, persisting approved
    mutations at the end of the governance pipeline.
    """

    engine_name: ClassVar[str] = "state"
    subscriptions: ClassVar[list[str]] = ["world", "simulation"]
    dependencies: ClassVar[list[str]] = []

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "commit"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the commit pipeline step."""
        ...

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- State operations ------------------------------------------------------

    async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict[str, Any]:
        """Retrieve a single entity by type and id."""
        ...

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Query entities of a given type with optional filters."""
        ...

    async def propose_mutation(self, deltas: list[StateDelta]) -> list[StateDelta]:
        """Validate proposed state mutations (dry run)."""
        ...

    async def commit_event(self, event: WorldEvent) -> EventId:
        """Persist an event and apply its state deltas atomically."""
        ...

    async def snapshot(self, label: str) -> SnapshotId:
        """Create an immutable point-in-time snapshot of the world state."""
        ...

    async def fork(self, snapshot_id: SnapshotId) -> WorldId:
        """Fork a new world from an existing snapshot."""
        ...

    async def diff(self, world_a: WorldId, world_b: WorldId) -> dict[str, Any]:
        """Compute the set of deltas between two worlds."""
        ...

    async def get_causal_chain(
        self, event_id: EventId, direction: str
    ) -> list[WorldEvent]:
        """Walk the causal ancestry or descendants of an event."""
        ...

    async def get_timeline(
        self, start: datetime, end: datetime
    ) -> list[WorldEvent]:
        """Return the ordered event timeline for a time range."""
        ...
