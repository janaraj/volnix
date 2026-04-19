"""Queued event carried in a dormant NPC's wait-queue (PMF Plan Phase 4A).

When ``CohortConfig.inactive_event_policies`` resolves an event
targeting a dormant NPC to ``"defer"``, the engine wraps the event
in a :class:`QueuedEvent` and appends it to
``CohortManager._queues[actor_id]``. On the NPC's next promotion,
:meth:`AgencyEngine._drain_promoted_cohort_queues` pops the list and
re-fires each event through :meth:`AgencyEngine.activate_for_event`,
replaying the deferred reactions in order.

Queue entries are immutable — once enqueued, the event, the tick it
was queued at, and the reason are permanent. The list itself is
mutated (append/pop) on the cohort manager's dict.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from volnix.core.events import Event


class QueuedEvent(BaseModel):
    """An event deferred until its target NPC re-enters the active cohort."""

    model_config = ConfigDict(frozen=True)

    event: Event
    queued_tick: int
    reason: str  # e.g. "defer_inactive", "promote_budget_exhausted"

    @property
    def event_type(self) -> str:
        """Proxy for convenience — avoids reaching into ``.event.event_type``
        at every call site."""
        return self.event.event_type
