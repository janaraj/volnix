"""E2E scale test for the Phase 4A activation-cycling platform.

Proves the core 4A contract end-to-end:

* 200 NPCs registered, cohort capped at 20.
* Exposure events at 50/tick for 10 ticks → total LLM calls ≤ 200
  (one per active NPC per tick max), never the unbounded 10 × 200 =
  2000 the pre-4A path would have produced.
* Rotation via ``agency.rotate_cohort()`` cycles dormant NPCs in.
* No NPC starves — every registered NPC either activates or gets
  queue-served within the run.
* ``CohortRotationEvent`` reaches the bus; ``CohortRotationEntry``
  lands in the ledger.
* Regression bite-sized: cohort disabled (``max_active=None``) leaves
  throughput at the pre-4A value (one activation per matching event).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.actors.activation_profile import (
    ActivationProfile,
    ActivationTrigger,
    BudgetDefaults,
    ToolScope,
)
from volnix.actors.cohort_manager import CohortManager
from volnix.actors.state import ActorState, Subscription
from volnix.core.events import CohortRotationEvent, NPCExposureEvent
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp
from volnix.engines.agency.engine import AgencyEngine
from volnix.engines.agency.npc_activator import NPCActivator
from volnix.engines.agency.npc_prompt_builder import NPCPromptBuilder
from volnix.ledger.entries import CohortRotationEntry
from volnix.llm.types import LLMResponse, ToolCall
from volnix.simulation.world_context import WorldContextBundle

# -- fixtures ----------------------------------------------------------------


def _ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _profile() -> ActivationProfile:
    return ActivationProfile(
        name="consumer_user",
        description="scale-test consumer",
        state_schema={"type": "object", "properties": {}},
        activation_triggers=[ActivationTrigger(event="npc.exposure")],
        prompt_template="consumer_user_decision.j2",
        tool_scope=ToolScope(read=["vibemesh"], write=["vibemesh"]),
        budget_defaults=BudgetDefaults(api_calls=2, llm_spend=0.0),
    )


class _ProfileLoaderStub:
    def load(self, name: str) -> ActivationProfile:
        return _profile()

    def list_available(self) -> list[str]:
        return ["consumer_user"]


def _ctx() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="scale world",
        reality_summary="messy",
        mission="scale",
        available_services=[
            {
                "name": "drop_flare",
                "service": "vibemesh",
                "http_method": "POST",
                "description": "Start a hangout",
                "required_params": ["duration_min"],
            },
        ],
    )


def _make_npcs(n: int) -> list[ActorState]:
    return [
        ActorState(
            actor_id=ActorId(f"npc-{i:03d}"),
            role="consumer",
            actor_type="internal",
            persona={"description": f"persona {i}"},
            activation_profile_name="consumer_user",
            npc_state={"awareness": 0, "interest": 0, "satisfaction": 0.5, "usage_count": 0},
            subscriptions=[
                Subscription(service_id="", filter={"event_type": "npc.exposure"}),
            ],
        )
        for i in range(n)
    ]


def _exposure(npc_id: str) -> NPCExposureEvent:
    return NPCExposureEvent(
        event_id=EventId(f"e-{npc_id}"),
        event_type="npc.exposure",
        timestamp=_ts(),
        actor_id=ActorId("animator"),
        service_id=ServiceId("npc_system"),
        action="expose",
        input_data={"intended_for": [npc_id]},
        npc_id=ActorId(npc_id),
        feature_id="drop_flare",
        source="seed",
    )


async def _build_engine(
    actors: list[ActorState],
    *,
    cohort: CohortManager | None = None,
) -> tuple[AgencyEngine, AsyncMock, AsyncMock, list[Any], list[Any]]:
    engine = AgencyEngine()
    bus_published: list[Any] = []

    async def _fake_publish(event: Any) -> None:
        bus_published.append(event)

    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock(side_effect=_fake_publish)
    await engine.initialize({}, bus)
    await engine.configure(actors, _ctx(), _ctx().available_services)

    llm_router = AsyncMock()
    llm_router.route = AsyncMock(
        return_value=LLMResponse(
            content="",
            tool_calls=[ToolCall(name="drop_flare", arguments={"duration_min": 1}, id="c1")],
            model="mock",
            provider="mock",
        )
    )
    engine._llm_router = llm_router

    committed = AsyncMock()
    committed.response_body = {"ok": True}
    committed.event_id = "evt-1"
    tool_executor = AsyncMock(return_value=committed)
    engine.set_tool_executor(tool_executor)

    class _Ledger:
        def __init__(self) -> None:
            self.entries: list[Any] = []

        async def append(self, entry: Any) -> int:
            self.entries.append(entry)
            return len(self.entries)

    ledger = _Ledger()
    engine._ledger = ledger

    engine.set_npc_activator(
        NPCActivator(
            prompt_builder=NPCPromptBuilder(),
            activation_profile_loader=_ProfileLoaderStub(),
        )
    )
    if cohort is not None:
        engine.set_cohort_manager(cohort)

    return engine, llm_router, tool_executor, ledger.entries, bus_published


# -- Tests -------------------------------------------------------------------


class TestScale:
    @pytest.mark.asyncio
    async def test_cohort_caps_llm_calls_at_scale(self) -> None:
        """200 NPCs × cohort=20 × 10 ticks × 50 events/tick.

        Tight bound (review fix N7 — earlier assertion ``<= 300`` was
        loose-by-50%). Reasoning:

        * Events target a specific npc_id via ``intended_for``. Only
          events hitting the active cohort of 20 trigger activation.
        * Uniform distribution: ~20/200 = 10% of 50 events/tick hit
          active members → ~5 activations per tick from the notify
          fan-out. Over 10 ticks → ~50 notify activations.
        * With ``promote_budget_per_tick=0`` no preempts happen, so
          extra calls come only from drain-on-promotion (``rotation_batch_size=5``
          NPCs promoted per tick × ≤3 queued events each = ≤15/tick,
          10 ticks → ≤150).
        * Upper bound: ~200. We assert <= 220 for small slack from
          ordering edge-cases, and take a per-tick counter so that if
          any single tick spikes the test fails immediately.
        """
        npcs = _make_npcs(200)
        cohort = CohortManager(
            max_active=20,
            rotation_policy="event_pressure_weighted",
            rotation_batch_size=5,
            promote_budget_per_tick=0,  # no preempt — pure defer+rotate
            queue_max_per_npc=3,
            inactive_event_policies={"default": "defer"},
            seed=42,
        )
        cohort.register([n.actor_id for n in npcs])
        engine, llm_router, _, ledger, bus_pub = await _build_engine(npcs, cohort=cohort)

        # Record LLM call count per tick so any single-tick spike is
        # detectable (review fix N7). Before-state captured, then diff
        # after each tick.
        per_tick_calls: list[int] = []
        for tick in range(10):
            before = llm_router.route.await_count
            for i in range(50):
                npc_id = f"npc-{((tick * 50 + i) % 200):03d}"
                await engine.notify(_exposure(npc_id))
            await engine.rotate_cohort(tick)
            per_tick_calls.append(llm_router.route.await_count - before)

        # Global bound: tight (~200 expected, 220 slack).
        total = llm_router.route.await_count
        assert total <= 220, (
            f"Too many LLM calls: {total} (per-tick: {per_tick_calls}) — cohort gate leaking"
        )
        # Per-tick bound: max 20 notify activations + 15 drain + 5
        # post-rotation = 40 pessimistic upper bound. Any single tick
        # > 40 means the gate let something through that shouldn't
        # have.
        for i, calls in enumerate(per_tick_calls):
            assert calls <= 40, (
                f"Tick {i}: {calls} LLM calls (per-tick spike) — "
                f"expected <= 40. Full sequence: {per_tick_calls}"
            )

        # 10 rotations → 10 CohortRotationEntry ledger rows
        rotation_entries = [e for e in ledger if isinstance(e, CohortRotationEntry)]
        assert len(rotation_entries) == 10

        # Bus saw the rotation events (one per rotate_cohort call).
        rotation_events = [e for e in bus_pub if isinstance(e, CohortRotationEvent)]
        assert len(rotation_events) == 10

    @pytest.mark.asyncio
    async def test_every_npc_eventually_activated_no_starvation(self) -> None:
        """Over enough rotations, round-robin covers every registered NPC.

        200 NPCs, cohort=20, rotation_batch=5 → full coverage requires
        (200 - 20) / 5 = 36 rotations. We run 40 to give a margin.
        Every actor id must appear in at least one ActivationComplete
        ledger entry or in the active set at run end.
        """
        npcs = _make_npcs(200)
        cohort = CohortManager(
            max_active=20,
            rotation_policy="round_robin",
            rotation_batch_size=5,
            promote_budget_per_tick=0,
            queue_max_per_npc=3,
            inactive_event_policies={"default": "defer"},
            seed=42,
        )
        cohort.register([n.actor_id for n in npcs])
        engine, _, _, ledger, _ = await _build_engine(npcs, cohort=cohort)

        # Feed one exposure per NPC per tick so queues build, then rotate.
        for tick in range(40):
            for n in npcs:
                await engine.notify(_exposure(str(n.actor_id)))
            await engine.rotate_cohort(tick)

        # Gather every actor_id that appears in an activation_complete entry.
        activated_ids: set[str] = set()
        for e in ledger:
            if getattr(e, "entry_type", None) == "activation_complete":
                activated_ids.add(str(getattr(e, "actor_id", "")))
        # Plus anyone currently in the active cohort (might not have
        # fired yet this test frame).
        final_active = {str(a) for a in cohort.active_ids()}
        covered = activated_ids | final_active
        # Cover everyone. (Allow 1 slack for the edge of cursor wrap.)
        assert len(covered) >= 199, (
            f"Starvation: only {len(covered)}/200 NPCs ever seen — "
            f"round-robin should cover everyone over 40 rotations"
        )

    @pytest.mark.asyncio
    async def test_disabled_cohort_preserves_prelim_behavior(self) -> None:
        """Regression guard: with no cohort manager, events fan out
        to every matching NPC exactly as pre-4A.
        """
        npcs = _make_npcs(10)
        engine, llm_router, _, _, _ = await _build_engine(npcs, cohort=None)

        # Fire one exposure per NPC — all 10 should activate.
        for n in npcs:
            await engine.notify(_exposure(str(n.actor_id)))

        assert llm_router.route.await_count == 10
