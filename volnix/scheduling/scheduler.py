"""Shared time-based event scheduling framework.

Any engine can register events. The Animator tick loop calls
get_due_events() each tick to fire them.

Event types:
- One-shot: fire at a specific world_time, removed after firing
- Recurring: fire every N seconds, automatically rescheduled
- Trigger: fire when a condition on world state is met (uses ConditionEvaluator)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from volnix.engines.policy.evaluator import ConditionEvaluator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ScheduledEvent:
    """A one-shot event that fires at a specific world_time."""

    id: str
    fire_time: datetime
    event_def: dict[str, Any]
    source: str


@dataclass
class RecurringEvent:
    """A recurring event that fires every interval_seconds."""

    id: str
    interval_seconds: float
    next_fire: datetime
    event_def: dict[str, Any]
    source: str


@dataclass
class TriggerEvent:
    """A condition-based event that fires when a condition is met."""

    id: str
    condition: str
    event_def: dict[str, Any]
    source: str


# ---------------------------------------------------------------------------
# WorldScheduler
# ---------------------------------------------------------------------------


class WorldScheduler:
    """Shared time-based event scheduling framework.

    Any engine can register events. The Animator tick loop calls
    get_due_events() each tick to fire them.

    Event types:
    - One-shot: fire at a specific world_time
    - Recurring: fire every N seconds
    - Trigger: fire when a condition on world state is met
    """

    def __init__(self) -> None:
        self._one_shot: list[ScheduledEvent] = []  # sorted by fire_time
        self._recurring: list[RecurringEvent] = []
        self._triggers: list[TriggerEvent] = []
        self._evaluator = ConditionEvaluator()

    def register_event(
        self,
        fire_time: datetime,
        event_def: dict[str, Any],
        source: str = "unknown",
    ) -> str:
        """Register a one-shot event to fire at a specific time.

        Args:
            fire_time: When to fire the event.
            event_def: The event definition dict (actor_id, service_id, action, input_data).
            source: Who registered this event (for tracing).

        Returns:
            The unique event ID.
        """
        event_id = f"sched_{uuid4().hex[:8]}"
        self._one_shot.append(
            ScheduledEvent(
                id=event_id,
                fire_time=fire_time,
                event_def=event_def,
                source=source,
            )
        )
        self._one_shot.sort(key=lambda e: e.fire_time)
        return event_id

    def register_recurring(
        self,
        interval_seconds: float,
        event_def: dict[str, Any],
        source: str = "unknown",
        start_time: datetime | None = None,
    ) -> str:
        """Register a recurring event that fires every N seconds.

        Args:
            interval_seconds: How often to fire.
            event_def: The event definition dict.
            source: Who registered this event.
            start_time: When to start the first fire (defaults to now UTC).

        Returns:
            The unique event ID.
        """
        event_id = f"recur_{uuid4().hex[:8]}"
        next_fire = start_time or datetime.now(tz=UTC)
        self._recurring.append(
            RecurringEvent(
                id=event_id,
                interval_seconds=interval_seconds,
                next_fire=next_fire,
                event_def=event_def,
                source=source,
            )
        )
        return event_id

    def register_trigger(
        self,
        condition: str,
        event_def: dict[str, Any],
        source: str = "unknown",
    ) -> str:
        """Register a trigger-based event (fires when condition is met).

        Args:
            condition: A condition expression evaluated by ConditionEvaluator.
            event_def: The event definition dict.
            source: Who registered this event.

        Returns:
            The unique event ID.
        """
        event_id = f"trig_{uuid4().hex[:8]}"
        self._triggers.append(
            TriggerEvent(
                id=event_id,
                condition=condition,
                event_def=event_def,
                source=source,
            )
        )
        return event_id

    async def get_due_events(
        self,
        world_time: datetime,
        state_engine: Any = None,
    ) -> list[dict[str, Any]]:
        """Return all events due at or before world_time.

        One-shot events are removed after firing.
        Recurring events are rescheduled to their next interval.
        Trigger events check their condition against state_engine.

        Args:
            world_time: Current simulation time.
            state_engine: Optional state engine for trigger condition evaluation.

        Returns:
            List of event_def dicts that are due.
        """
        due: list[dict[str, Any]] = []

        # One-shot events: pop from front while fire_time <= world_time
        while self._one_shot and self._one_shot[0].fire_time <= world_time:
            event = self._one_shot.pop(0)
            due.append(event.event_def)
            logger.debug("One-shot event fired: %s (source=%s)", event.id, event.source)

        # Recurring events: fire if next_fire <= world_time, reschedule
        for recurring in self._recurring:
            if recurring.next_fire <= world_time:
                due.append(recurring.event_def)
                recurring.next_fire += timedelta(seconds=recurring.interval_seconds)
                logger.debug(
                    "Recurring event fired: %s (next=%s)",
                    recurring.id,
                    recurring.next_fire.isoformat(),
                )

        # Trigger-based events: evaluate conditions against state
        if state_engine:
            triggered_ids: list[str] = []
            for trigger in self._triggers:
                context = await self._build_trigger_context(state_engine)
                if self._evaluator.evaluate(trigger.condition, context):
                    due.append(trigger.event_def)
                    triggered_ids.append(trigger.id)
                    logger.debug(
                        "Trigger event fired: %s (condition=%s)",
                        trigger.id,
                        trigger.condition,
                    )
            # Remove fired triggers (one-shot triggers)
            self._triggers = [t for t in self._triggers if t.id not in triggered_ids]

        return due

    def cancel(self, event_id: str) -> bool:
        """Cancel a scheduled event by ID.

        Args:
            event_id: The ID of the event to cancel.

        Returns:
            True if the event was found and cancelled, False otherwise.
        """
        # Check one-shot
        for i, event in enumerate(self._one_shot):
            if event.id == event_id:
                self._one_shot.pop(i)
                return True

        # Check recurring
        for i, event in enumerate(self._recurring):
            if event.id == event_id:
                self._recurring.pop(i)
                return True

        # Check triggers
        for i, event in enumerate(self._triggers):
            if event.id == event_id:
                self._triggers.pop(i)
                return True

        return False

    @property
    def pending_count(self) -> int:
        """Total number of pending events across all types."""
        return len(self._one_shot) + len(self._recurring) + len(self._triggers)

    @property
    def next_fire_time(self) -> datetime | None:
        """Earliest fire time across one-shot and recurring events, or None.

        Triggers are condition-based (no known fire time) and are excluded.
        """
        candidates: list[datetime] = []
        if self._one_shot:
            candidates.append(self._one_shot[0].fire_time)  # already sorted
        for r in self._recurring:
            candidates.append(r.next_fire)
        return min(candidates) if candidates else None

    async def _build_trigger_context(self, state_engine: Any) -> dict[str, Any]:
        """Build a context dict for ConditionEvaluator from the state engine.

        Provides a 'state' key with common query results for trigger conditions.
        """
        context: dict[str, Any] = {"state": state_engine}
        return context
