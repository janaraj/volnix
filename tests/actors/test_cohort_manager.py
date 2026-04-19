"""Unit tests for :class:`volnix.actors.cohort_manager.CohortManager`.

Pure-logic tests — no engines, no bus, no LLM. Every test pins the
Phase 4A contract (per-event-type policies, determinism, LRU
eviction, queue overflow behavior, budget caps, rotation fairness).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volnix.actors.cohort_manager import CohortManager, CohortStats
from volnix.actors.queued_event import QueuedEvent
from volnix.core.events import NPCExposureEvent
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp

# -- helpers -----------------------------------------------------------------


def _ids(n: int, prefix: str = "npc") -> list[ActorId]:
    return [ActorId(f"{prefix}-{i:03d}") for i in range(n)]


def _ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _exposure(npc: str, feature: str = "drop_flare") -> NPCExposureEvent:
    return NPCExposureEvent(
        event_id=EventId(f"e-{npc}-{feature}"),
        event_type="npc.exposure",
        timestamp=_ts(),
        actor_id=ActorId("animator"),
        service_id=ServiceId("npc_system"),
        action="expose",
        npc_id=ActorId(npc),
        feature_id=feature,
        source="seed",
    )


def _queued(npc: str, tick: int = 0, feature: str = "drop_flare") -> QueuedEvent:
    return QueuedEvent(event=_exposure(npc, feature), queued_tick=tick, reason="test")


def _make_mgr(
    *,
    max_active: int = 3,
    rotation_policy: str = "event_pressure_weighted",
    rotation_batch_size: int = 2,
    promote_budget_per_tick: int = 5,
    queue_max_per_npc: int = 3,
    policies: dict | None = None,
    seed: int = 42,
    registered: int = 10,
) -> CohortManager:
    mgr = CohortManager(
        max_active=max_active,
        rotation_policy=rotation_policy,  # type: ignore[arg-type]
        rotation_batch_size=rotation_batch_size,
        promote_budget_per_tick=promote_budget_per_tick,
        queue_max_per_npc=queue_max_per_npc,
        inactive_event_policies=policies  # type: ignore[arg-type]
        or {"default": "defer", "npc.interview_probe": "promote"},
        seed=seed,
    )
    mgr.register(_ids(registered))
    return mgr


# -- construction + validation ----------------------------------------------


class TestConstruction:
    def test_max_active_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_active must be > 0"):
            CohortManager(
                max_active=0,
                rotation_policy="round_robin",
                rotation_batch_size=1,
                promote_budget_per_tick=1,
                queue_max_per_npc=1,
                inactive_event_policies={"default": "defer"},
                seed=1,
            )

    def test_missing_default_policy_raises(self) -> None:
        with pytest.raises(ValueError, match="must contain a 'default' key"):
            CohortManager(
                max_active=1,
                rotation_policy="round_robin",
                rotation_batch_size=1,
                promote_budget_per_tick=1,
                queue_max_per_npc=1,
                inactive_event_policies={"npc.exposure": "defer"},
                seed=1,
            )

    def test_zero_queue_cap_raises(self) -> None:
        with pytest.raises(ValueError, match="queue_max_per_npc must be > 0"):
            CohortManager(
                max_active=1,
                rotation_policy="round_robin",
                rotation_batch_size=1,
                promote_budget_per_tick=1,
                queue_max_per_npc=0,
                inactive_event_policies={"default": "defer"},
                seed=1,
            )


# -- registry + enabled ------------------------------------------------------


class TestRegistry:
    def test_disabled_before_register(self) -> None:
        mgr = _make_mgr(registered=0)
        assert mgr.enabled is False
        # never registered → is_active False for anyone
        assert mgr.is_active(ActorId("npc-000")) is False

    def test_enabled_after_register(self) -> None:
        mgr = _make_mgr(max_active=3, registered=5)
        assert mgr.enabled is True
        assert len(mgr.active_ids()) == 3

    def test_initial_cohort_is_first_max_active_registered(self) -> None:
        mgr = _make_mgr(max_active=3, registered=10)
        active = mgr.active_ids()
        # First 3 in registration order → npc-000, npc-001, npc-002
        for i in range(3):
            assert ActorId(f"npc-{i:03d}") in active
        for i in range(3, 10):
            assert ActorId(f"npc-{i:03d}") not in active

    def test_registered_ids_returns_copy(self) -> None:
        mgr = _make_mgr(registered=3)
        ids = mgr.registered_ids()
        ids.clear()
        # Original still intact
        assert len(mgr.registered_ids()) == 3

    def test_re_register_resets_state(self) -> None:
        mgr = _make_mgr(registered=5)
        mgr.enqueue(ActorId("npc-004"), _queued("npc-004"))
        mgr.record_activation(ActorId("npc-000"), tick=3)
        # Re-register — per-run state must clear
        mgr.register(_ids(5, prefix="reset"))
        assert mgr.queue_depth(ActorId("npc-004")) == 0
        assert mgr.stats().queue_total_depth == 0


# -- policy resolution -------------------------------------------------------


class TestPolicyResolution:
    def test_default_fallback(self) -> None:
        mgr = _make_mgr(policies={"default": "defer"})
        assert mgr.policy_for("npc.exposure") == "defer"
        assert mgr.policy_for("some.unknown.event") == "defer"

    def test_explicit_override(self) -> None:
        mgr = _make_mgr(
            policies={
                "default": "defer",
                "npc.interview_probe": "promote",
            }
        )
        assert mgr.policy_for("npc.interview_probe") == "promote"
        assert mgr.policy_for("npc.exposure") == "defer"


# -- enqueue + drain + overflow ---------------------------------------------


class TestQueue:
    def test_enqueue_appends(self) -> None:
        mgr = _make_mgr(queue_max_per_npc=3)
        npc = ActorId("npc-005")
        assert mgr.enqueue(npc, _queued("npc-005", 1)) is True
        assert mgr.enqueue(npc, _queued("npc-005", 2)) is True
        assert mgr.queue_depth(npc) == 2

    def test_overflow_drops_oldest(self) -> None:
        mgr = _make_mgr(queue_max_per_npc=2)
        npc = ActorId("npc-005")
        mgr.enqueue(npc, _queued("npc-005", 1))
        mgr.enqueue(npc, _queued("npc-005", 2))
        # Third exceeds cap; returns False → overflow occurred
        assert mgr.enqueue(npc, _queued("npc-005", 3)) is False
        assert mgr.queue_depth(npc) == 2
        drained = mgr.drain_queue(npc)
        # Oldest (tick=1) was dropped; tick=2 + tick=3 remain.
        assert [q.queued_tick for q in drained] == [2, 3]

    def test_drain_returns_fifo_and_empties(self) -> None:
        mgr = _make_mgr()
        npc = ActorId("npc-005")
        for t in range(3):
            mgr.enqueue(npc, _queued("npc-005", t))
        drained = mgr.drain_queue(npc)
        assert [q.queued_tick for q in drained] == [0, 1, 2]
        # Queue gone from dict — not just empty
        assert mgr.queue_depth(npc) == 0
        assert mgr.stats().queue_total_depth == 0

    def test_drain_missing_returns_empty_list(self) -> None:
        mgr = _make_mgr()
        assert mgr.drain_queue(ActorId("never-queued")) == []


# -- promotion ---------------------------------------------------------------


class TestPromotion:
    def test_try_promote_already_active_is_noop(self) -> None:
        mgr = _make_mgr(max_active=3, registered=5)
        active_id = next(iter(mgr.active_ids()))
        promoted, evicted = mgr.try_promote(active_id)
        assert promoted is True
        assert evicted is None
        # No budget consumed
        assert mgr.stats().promote_budget_remaining == 5

    def test_try_promote_evicts_LRU_active(self) -> None:
        mgr = _make_mgr(max_active=3, registered=5, promote_budget_per_tick=5)
        # npc-000, npc-001, npc-002 initially active
        # Activate npc-001 at tick 10 (most recent), npc-002 at tick 5
        # → npc-000 has no record → oldest → evicted first
        mgr.record_activation(ActorId("npc-002"), tick=5)
        mgr.record_activation(ActorId("npc-001"), tick=10)
        promoted, evicted = mgr.try_promote(ActorId("npc-003"))
        assert promoted is True
        assert evicted == ActorId("npc-000")
        assert mgr.is_active(ActorId("npc-003"))
        assert not mgr.is_active(ActorId("npc-000"))

    def test_promote_budget_exhausted(self) -> None:
        mgr = _make_mgr(max_active=2, registered=10, promote_budget_per_tick=2)
        for i in range(2, 4):
            promoted, _ = mgr.try_promote(ActorId(f"npc-{i:03d}"))
            assert promoted is True
        # Third within budget window → budget exhausted
        promoted, evicted = mgr.try_promote(ActorId("npc-005"))
        assert promoted is False
        assert evicted is None
        assert mgr.stats().promote_budget_remaining == 0

    def test_promote_budget_resets_on_rotate(self) -> None:
        mgr = _make_mgr(max_active=2, registered=10, promote_budget_per_tick=1)
        mgr.try_promote(ActorId("npc-002"))
        assert mgr.stats().promote_budget_remaining == 0
        mgr.rotate(tick=1)
        assert mgr.stats().promote_budget_remaining == 1


# -- rotation ----------------------------------------------------------------


class TestRotation:
    def test_no_rotation_when_all_fit(self) -> None:
        mgr = _make_mgr(max_active=10, registered=5)
        demoted, promoted = mgr.rotate(tick=1)
        assert demoted == []
        assert promoted == []

    def test_round_robin_is_fair(self) -> None:
        mgr = _make_mgr(
            max_active=3,
            registered=9,
            rotation_batch_size=3,
            rotation_policy="round_robin",
        )
        seen: set[ActorId] = set(mgr.active_ids())
        # 9 registered / batch=3 → 3 rotations should cover everyone.
        for i in range(3):
            _, promoted = mgr.rotate(tick=i + 1)
            seen.update(promoted)
        assert len(seen) == 9

    def test_event_pressure_prioritizes_highest_queue(self) -> None:
        mgr = _make_mgr(
            max_active=3,
            registered=10,
            rotation_batch_size=2,
            rotation_policy="event_pressure_weighted",
        )
        # Queue 3 events on npc-008 (dormant), 1 on npc-005
        for t in range(3):
            mgr.enqueue(ActorId("npc-008"), _queued("npc-008", t))
        mgr.enqueue(ActorId("npc-005"), _queued("npc-005", 0))
        _, promoted = mgr.rotate(tick=1)
        # Highest queue first → npc-008 must be in the promoted batch
        assert ActorId("npc-008") in promoted
        # npc-005 (1 queued) before any 0-queued dormant
        assert ActorId("npc-005") in promoted

    def test_recency_prefers_oldest_activation(self) -> None:
        mgr = _make_mgr(
            max_active=3,
            registered=10,
            rotation_batch_size=2,
            rotation_policy="recency",
            seed=42,
        )
        # Give some dormant NPCs activation history
        mgr.record_activation(ActorId("npc-005"), tick=5)
        mgr.record_activation(ActorId("npc-006"), tick=50)
        # npc-007 has no record — counts as -1, even older than npc-005
        _, promoted = mgr.rotate(tick=100)
        # npc-007 (never activated) and npc-005 (older) come before npc-006
        assert ActorId("npc-006") not in promoted

    def test_rotation_maintains_active_size(self) -> None:
        mgr = _make_mgr(max_active=3, registered=10, rotation_batch_size=2)
        demoted, promoted = mgr.rotate(tick=1)
        # Demoted count never exceeds promoted count — active size stays ≤ cap
        assert len(demoted) == len(promoted)
        assert len(mgr.active_ids()) == 3


# -- determinism -------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_rotation_history(self) -> None:
        """Two managers with identical inputs produce byte-identical
        rotation histories over a 10-cycle sequence."""
        history_a: list[tuple[list[ActorId], list[ActorId]]] = []
        history_b: list[tuple[list[ActorId], list[ActorId]]] = []

        for history in (history_a, history_b):
            mgr = _make_mgr(
                max_active=3,
                registered=15,
                rotation_batch_size=2,
                rotation_policy="event_pressure_weighted",
                seed=42,
            )
            # Same event load on both instances
            for t in range(5):
                for i in range(t, t + 3):
                    mgr.enqueue(ActorId(f"npc-{i:03d}"), _queued(f"npc-{i:03d}", t))
                history.append(mgr.rotate(tick=t + 1))

        assert history_a == history_b


# -- stats -------------------------------------------------------------------


class TestStats:
    def test_stats_snapshot_shape(self) -> None:
        mgr = _make_mgr(
            max_active=3,
            registered=10,
            promote_budget_per_tick=5,
            rotation_batch_size=2,
        )
        mgr.enqueue(ActorId("npc-005"), _queued("npc-005"))
        mgr.try_promote(ActorId("npc-004"))
        s = mgr.stats()
        assert isinstance(s, CohortStats)
        assert s.active_count == 3
        assert s.registered_count == 10
        assert s.queue_total_depth == 1
        assert s.promote_budget_remaining == 4
        # Review fix D4: rotation_policy on stats, not via
        # ``getattr(_rotation_policy, "unknown")``.
        assert s.rotation_policy == "event_pressure_weighted"
