"""Shared scheduling framework for time-based event management.

Any engine can register events with the WorldScheduler.
The Animator tick loop calls get_due_events() each tick to fire them.
"""

from volnix.scheduling.scheduler import (
    RecurringEvent,
    ScheduledEvent,
    TriggerEvent,
    WorldScheduler,
)

__all__ = [
    "WorldScheduler",
    "ScheduledEvent",
    "RecurringEvent",
    "TriggerEvent",
]
