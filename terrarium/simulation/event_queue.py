"""EventQueue -- priority queue ordering all actions by logical time.

The single entry point for all actions in the world. External agents,
AgencyEngine, and Animator all submit ActionEnvelopes here.

Tie-breaking: (logical_time, priority, actor_id, envelope_id)
"""

from __future__ import annotations

import heapq
import logging

from terrarium.core.envelope import ActionEnvelope

logger = logging.getLogger(__name__)


class EventQueue:
    """Priority queue with logical time ordering for all world actions."""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, str, str, ActionEnvelope]] = []
        self._current_time: float = 0.0
        self._counter: int = 0  # monotonic insertion counter for stable sort

    def submit(self, envelope: ActionEnvelope) -> None:
        """Add an action to the queue for immediate processing."""
        entry = (
            envelope.logical_time,
            envelope.priority.value,
            str(envelope.actor_id),
            str(envelope.envelope_id),
            envelope,
        )
        heapq.heappush(self._heap, entry)
        self._counter += 1

    def schedule(self, envelope: ActionEnvelope, delay: float) -> None:
        """Schedule an action for future logical time."""
        future_time = self._current_time + delay
        updated = envelope.model_copy(update={"logical_time": future_time})
        self.submit(updated)

    def pop_next(self) -> ActionEnvelope | None:
        """Dequeue the next envelope (lowest logical_time). Returns None if empty."""
        if not self._heap:
            return None
        _, _, _, _, envelope = heapq.heappop(self._heap)
        self._current_time = max(self._current_time, envelope.logical_time)
        return envelope

    def has_pending(self) -> bool:
        """Check if queue has actions to process."""
        return len(self._heap) > 0

    def peek_time(self) -> float | None:
        """Return the logical_time of the next envelope without popping."""
        if not self._heap:
            return None
        return self._heap[0][0]

    @property
    def current_time(self) -> float:
        """Current logical time (advances as events are processed)."""
        return self._current_time

    @current_time.setter
    def current_time(self, value: float) -> None:
        self._current_time = value

    @property
    def size(self) -> int:
        """Number of envelopes in the queue."""
        return len(self._heap)
