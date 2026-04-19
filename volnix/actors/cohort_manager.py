"""Active cohort manager — caps LLM-consuming NPCs at any given tick.

PMF Plan Phase 4A (``internal_docs/pmf/phase-4a-activation-cycling.md``).

Registered NPCs stay forever in ``AgencyEngine._actor_states`` for the
life of a run; ``CohortManager`` gates which of them consume LLM
cycles, and queues events for the rest. The gate itself lives in
``AgencyEngine._activate_with_tool_loop`` — this module owns no
engines, opens no bus, makes no LLM calls. Every decision here is a
pure function of (state, config, seed).

Design principles this module enforces:

* **No hardcoded defaults** — every knob is a required constructor
  kwarg. The composition root wires in ``CohortConfig`` values;
  ``seed`` flows from ``WorldPlan.seed``.
* **Determinism** — all policy branches sort deterministically
  (registered-order tie-break + seeded RNG where needed). Two
  managers with the same inputs produce byte-identical rotation
  histories.
* **No cross-engine imports** — only ``volnix.core.*`` and
  ``volnix.actors.*``.
* **Single LRU eviction policy** — the only choice today; adding a
  second eviction policy would be a config knob, not an if-branch.
"""

from __future__ import annotations

import logging
import random
from typing import Literal

from pydantic import BaseModel, ConfigDict

from volnix.actors.queued_event import QueuedEvent
from volnix.core.types import ActorId

logger = logging.getLogger(__name__)


RotationPolicy = Literal["round_robin", "recency", "event_pressure_weighted"]
InactivePolicy = Literal["record_only", "defer", "promote"]


class CohortStats(BaseModel):
    """Snapshot of manager state — used on the ledger entry."""

    model_config = ConfigDict(frozen=True)

    active_count: int
    registered_count: int
    queue_total_depth: int
    promote_budget_remaining: int


class CohortManager:
    """Manages the active cohort and per-NPC event queues.

    Not a frozen value object — its sets/dicts mutate as ticks fire —
    but every *decision* is a pure function of state + config + seed.
    """

    def __init__(
        self,
        *,
        max_active: int,
        rotation_policy: RotationPolicy,
        rotation_batch_size: int,
        promote_budget_per_tick: int,
        queue_max_per_npc: int,
        inactive_event_policies: dict[str, InactivePolicy],
        seed: int,
    ) -> None:
        # All kwargs required — no class-level defaults. Every knob
        # flows from ``CohortConfig``; ``seed`` flows from the world
        # seed so reproducibility ties to the world, not this module.
        if max_active <= 0:
            raise ValueError(f"max_active must be > 0, got {max_active}")
        if rotation_batch_size <= 0:
            raise ValueError(f"rotation_batch_size must be > 0, got {rotation_batch_size}")
        if promote_budget_per_tick < 0:
            raise ValueError(f"promote_budget_per_tick must be >= 0, got {promote_budget_per_tick}")
        if queue_max_per_npc <= 0:
            raise ValueError(f"queue_max_per_npc must be > 0, got {queue_max_per_npc}")
        if "default" not in inactive_event_policies:
            raise ValueError("inactive_event_policies must contain a 'default' key")

        self._max_active = max_active
        self._rotation_policy = rotation_policy
        self._rotation_batch_size = rotation_batch_size
        self._promote_budget_per_tick = promote_budget_per_tick
        self._queue_max_per_npc = queue_max_per_npc
        self._policies = dict(inactive_event_policies)
        self._seed = seed

        # Full registered list — deterministic order; used for
        # round-robin cursor and tie-breaks.
        self._registered: list[ActorId] = []
        # Set for O(1) membership check on the active cohort.
        self._active: set[ActorId] = set()
        # Per-dormant-NPC event queue.
        self._queues: dict[ActorId, list[QueuedEvent]] = {}
        # Last activation tick per actor — used by ``recency`` policy
        # and by LRU eviction.
        self._last_activation: dict[ActorId, int] = {}
        # Round-robin cursor index into ``_registered``.
        self._rr_cursor: int = 0
        # Per-window preempt-promote counter; reset on ``rotate()``.
        self._promote_used_this_window: int = 0

    # -- registry --------------------------------------------------------

    def register(self, actor_ids: list[ActorId]) -> None:
        """Register NPCs up front. Bootstraps the initial active cohort.

        Deterministic order: assumes the caller passes ``actor_ids``
        in a stable order (the compiler's actor generation is
        deterministic at a given seed, so this holds).
        """
        self._registered = list(actor_ids)
        # Seed the first cohort: the first ``max_active`` registered.
        initial = self._registered[: self._max_active]
        self._active = set(initial)
        # Fresh registration resets all per-run state so two worlds
        # re-using the same manager instance don't leak queues.
        self._queues = {}
        self._last_activation = {}
        self._rr_cursor = 0
        self._promote_used_this_window = 0

    @property
    def enabled(self) -> bool:
        """True iff the manager has a cap AND is holding actors."""
        return self._max_active > 0 and len(self._registered) > 0

    def is_active(self, actor_id: ActorId) -> bool:
        return actor_id in self._active

    def registered_ids(self) -> list[ActorId]:
        """Read-only registered list (returns a copy)."""
        return list(self._registered)

    def active_ids(self) -> set[ActorId]:
        """Read-only active set (returns a copy)."""
        return set(self._active)

    # -- event handling -------------------------------------------------

    def policy_for(self, event_type: str) -> InactivePolicy:
        """Resolve the policy for an event_type with default fallback."""
        return self._policies.get(event_type, self._policies["default"])

    def enqueue(self, actor_id: ActorId, queued: QueuedEvent) -> bool:
        """Append a queued event, respecting the per-NPC cap.

        Returns ``True`` if queued, ``False`` if the queue was at
        capacity and the oldest entry was dropped to make room.
        """
        q = self._queues.setdefault(actor_id, [])
        overflowed = False
        if len(q) >= self._queue_max_per_npc:
            dropped = q.pop(0)
            overflowed = True
            logger.info(
                "CohortManager: queue full for %s, dropped oldest %s",
                actor_id,
                dropped.event_type,
            )
        q.append(queued)
        return not overflowed

    def drain_queue(self, actor_id: ActorId) -> list[QueuedEvent]:
        """Pop and return all queued events for ``actor_id``.

        Returns ``[]`` if nothing is queued. Guarantees the queue is
        removed from the backing dict, not just emptied, so memory
        doesn't leak over long runs.
        """
        return self._queues.pop(actor_id, [])

    def queue_depth(self, actor_id: ActorId) -> int:
        return len(self._queues.get(actor_id, []))

    # -- promotion ------------------------------------------------------

    def try_promote(self, actor_id: ActorId) -> tuple[bool, ActorId | None]:
        """Preempt-promote a dormant NPC. Returns ``(promoted, evicted_id)``.

        Enforces ``promote_budget_per_tick``; bursts beyond the budget
        return ``(False, None)`` and the caller must fall back to
        ``defer`` (or drop). Already-active actors are a no-op.
        """
        if actor_id in self._active:
            return True, None
        if self._promote_used_this_window >= self._promote_budget_per_tick:
            return False, None
        evicted = self._pick_eviction_victim()
        if evicted is not None:
            self._active.discard(evicted)
        self._active.add(actor_id)
        self._promote_used_this_window += 1
        logger.info("Cohort promote: %s (evicted %s)", actor_id, evicted)
        return True, evicted

    def _pick_eviction_victim(self) -> ActorId | None:
        """LRU-active: NPC least-recently activated wins.

        Never-activated (missing from ``_last_activation``) counts as
        ``-1`` — they're immediate-eligible victims. Ties broken by
        registered-order stability for determinism.
        """
        if not self._active:
            return None

        def score(aid: ActorId) -> tuple[int, int]:
            return (
                self._last_activation.get(aid, -1),
                self._registered.index(aid) if aid in self._registered else 0,
            )

        return min(self._active, key=score)

    # -- rotation -------------------------------------------------------

    def rotate(self, tick: int) -> tuple[list[ActorId], list[ActorId]]:
        """Run one rotation cycle. Returns ``(demoted, promoted)``.

        Called by ``AgencyEngine`` when a ``cohort.rotate_tick``
        scheduler event fires. Resets the per-window promote budget
        so ``try_promote`` has fresh headroom in the next window.
        """
        # Reset budget first — even if nothing rotates, the next
        # window should start fresh.
        self._promote_used_this_window = 0

        if len(self._registered) <= self._max_active:
            # Everyone already fits; nothing to do.
            return [], []

        dormant = [a for a in self._registered if a not in self._active]
        if not dormant:
            return [], []

        if self._rotation_policy == "round_robin":
            promoted = self._rotate_round_robin()
        elif self._rotation_policy == "recency":
            promoted = self._rotate_recency(dormant)
        else:  # event_pressure_weighted — the default per CohortConfig
            promoted = self._rotate_event_pressure(dormant)

        # Demote exactly as many as we promote — net active size
        # constant. Never demote more than promoted to avoid shrinking.
        batch = min(self._rotation_batch_size, len(promoted))
        promoted = promoted[:batch]
        demoted = self._pick_demote_batch(batch=batch)

        for aid in demoted:
            self._active.discard(aid)
        for aid in promoted:
            self._active.add(aid)

        logger.info(
            "Cohort rotate tick=%d policy=%s: -%s +%s",
            tick,
            self._rotation_policy,
            [str(a) for a in demoted],
            [str(a) for a in promoted],
        )
        return demoted, promoted

    def _rotate_round_robin(self) -> list[ActorId]:
        """Advance cursor through registered list, picking dormant actors.

        Deterministic: given the same cursor position + same active
        set, same result.
        """
        batch: list[ActorId] = []
        n = len(self._registered)
        if n == 0:
            return batch
        for _ in range(self._rotation_batch_size):
            # Walk at most ``n`` positions looking for a dormant NPC
            # not already in the batch. If we wrap fully, break.
            for _attempt in range(n):
                candidate = self._registered[self._rr_cursor % n]
                self._rr_cursor = (self._rr_cursor + 1) % n
                if candidate not in self._active and candidate not in batch:
                    batch.append(candidate)
                    break
            else:
                break
        return batch

    def _rotate_recency(self, dormant: list[ActorId]) -> list[ActorId]:
        """Oldest activation first; seeded RNG tie-break for determinism."""
        rng = random.Random(self._seed)

        def score(aid: ActorId) -> tuple[int, float]:
            return (self._last_activation.get(aid, -1), rng.random())

        return sorted(dormant, key=score)[: self._rotation_batch_size]

    def _rotate_event_pressure(self, dormant: list[ActorId]) -> list[ActorId]:
        """Highest queue-depth first; ties by registered-order stability."""

        def score(aid: ActorId) -> tuple[int, int]:
            return (
                -self.queue_depth(aid),
                self._registered.index(aid),
            )

        return sorted(dormant, key=score)[: self._rotation_batch_size]

    def _pick_demote_batch(self, batch: int) -> list[ActorId]:
        """LRU-active: least-recently activated N members leave first."""

        def score(aid: ActorId) -> tuple[int, int]:
            return (
                self._last_activation.get(aid, -1),
                self._registered.index(aid) if aid in self._registered else 0,
            )

        return sorted(self._active, key=score)[:batch]

    # -- accounting -----------------------------------------------------

    def record_activation(self, actor_id: ActorId, tick: int) -> None:
        """Log an activation. Used by ``recency`` policy + LRU eviction.

        Called from ``NPCActivator`` after every successful NPC
        activation. Safe to call for non-active actors (no-op effect
        on membership).
        """
        self._last_activation[actor_id] = tick

    def stats(self) -> CohortStats:
        """Snapshot for ``CohortRotationEntry`` ledger writes."""
        return CohortStats(
            active_count=len(self._active),
            registered_count=len(self._registered),
            queue_total_depth=sum(len(q) for q in self._queues.values()),
            promote_budget_remaining=max(
                0,
                self._promote_budget_per_tick - self._promote_used_this_window,
            ),
        )
