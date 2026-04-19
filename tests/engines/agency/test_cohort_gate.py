"""Integration tests for the cohort-gate in ``_activate_with_tool_loop``.

Tests every policy path (``record_only`` / ``defer`` / ``promote`` /
``promote_budget_exhausted`` fallback / agents-exempt) and verifies
zero-regression when the cohort manager is absent. This is the core
Phase 4A gate contract — these tests fail if someone accidentally
gates the agent path or the default-off guarantee breaks.
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
from volnix.core.events import NPCExposureEvent, NPCInterviewProbeEvent
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp
from volnix.engines.agency.engine import AgencyEngine
from volnix.engines.agency.npc_activator import NPCActivator
from volnix.engines.agency.npc_prompt_builder import NPCPromptBuilder
from volnix.llm.types import LLMResponse, ToolCall
from volnix.simulation.world_context import WorldContextBundle

# -- fixtures ----------------------------------------------------------------


def _ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _profile() -> ActivationProfile:
    return ActivationProfile(
        name="consumer_user",
        description="cohort gate test",
        state_schema={"type": "object", "properties": {}},
        activation_triggers=[
            ActivationTrigger(event="npc.exposure"),
            ActivationTrigger(event="npc.interview_probe"),
        ],
        prompt_template="consumer_user_decision.j2",
        tool_scope=ToolScope(read=["vibemesh"], write=["vibemesh"]),
        budget_defaults=BudgetDefaults(api_calls=2, llm_spend=0.0),
    )


class _ProfileLoaderStub:
    def load(self, name: str) -> ActivationProfile:
        if name == "consumer_user":
            return _profile()
        raise FileNotFoundError(name)

    def list_available(self) -> list[str]:
        return ["consumer_user"]


def _ctx() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="cohort test world",
        reality_summary="Messy.",
        mission="test cohort gating",
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


def _exposure(npc_id: str) -> NPCExposureEvent:
    return NPCExposureEvent(
        event_id=EventId(f"e-{npc_id}-exp"),
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


def _interview(researcher_id: str, npc_id: str) -> NPCInterviewProbeEvent:
    return NPCInterviewProbeEvent(
        event_id=EventId(f"probe-{npc_id}"),
        event_type="npc.interview_probe",
        timestamp=_ts(),
        actor_id=ActorId(researcher_id),
        service_id=ServiceId("research_tools"),
        action="interview",
        input_data={"intended_for": [npc_id]},
        researcher_id=ActorId(researcher_id),
        npc_id=ActorId(npc_id),
        prompt="how do you feel about this?",
    )


def _active_npc(
    actor_id: str,
    *,
    event_types: tuple[str, ...] = ("npc.exposure", "npc.interview_probe"),
) -> ActorState:
    return ActorState(
        actor_id=ActorId(actor_id),
        role="consumer",
        actor_type="internal",
        persona={"description": "Test consumer"},
        activation_profile_name="consumer_user",
        npc_state={"awareness": 0, "interest": 0, "satisfaction": 0.5, "usage_count": 0},
        subscriptions=[
            Subscription(service_id="", filter={"event_type": et}) for et in event_types
        ],
    )


def _passive_agent(actor_id: str) -> ActorState:
    """Non-NPC agent: no ``activation_profile_name``. Cohort must never gate."""
    return ActorState(
        actor_id=ActorId(actor_id),
        role="supervisor",
        actor_type="internal",
        persona={"description": "Research lead"},
        # activation_profile_name defaults None → agent path.
    )


async def _build_engine(
    actors: list[ActorState],
    *,
    cohort: CohortManager | None = None,
) -> tuple[AgencyEngine, AsyncMock, AsyncMock, Any]:
    engine = AgencyEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    await engine.initialize({}, bus)
    await engine.configure(actors, _ctx(), _ctx().available_services)

    llm_router = AsyncMock()
    llm_router.route = AsyncMock(
        return_value=LLMResponse(
            content="",
            tool_calls=[ToolCall(name="drop_flare", arguments={"duration_min": 5}, id="c1")],
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

    return engine, llm_router, tool_executor, ledger


def _make_cohort(
    active_ids: list[str],
    dormant_ids: list[str],
    *,
    policies: dict | None = None,
    max_active: int | None = None,
    promote_budget: int = 5,
) -> CohortManager:
    """Build a cohort with an explicit split: first N registered are active."""
    all_ids = active_ids + dormant_ids
    cap = max_active if max_active is not None else len(active_ids)
    mgr = CohortManager(
        max_active=cap,
        rotation_policy="event_pressure_weighted",
        rotation_batch_size=2,
        promote_budget_per_tick=promote_budget,
        queue_max_per_npc=5,
        inactive_event_policies=policies or {"default": "defer", "npc.interview_probe": "promote"},
        seed=42,
    )
    mgr.register([ActorId(i) for i in all_ids])
    return mgr


# -- Tests -------------------------------------------------------------------


class TestDefaultOff:
    """Without a cohort manager, behavior is byte-identical to pre-4A."""

    @pytest.mark.asyncio
    async def test_no_cohort_active_npc_activates_normally(self) -> None:
        npc = _active_npc("npc-1")
        engine, router, executor, _ = await _build_engine([npc])
        # No set_cohort_manager call — _cohort_manager stays None
        assert engine._cohort_manager is None
        envelopes = await engine.notify(_exposure("npc-1"))
        # LLM fired once, pipeline called, envelope produced
        assert router.route.await_count == 1
        assert executor.await_count == 1
        assert len(envelopes) == 1


class TestDeferPolicy:
    """Dormant NPC + defer policy: queue the event, no LLM call."""

    @pytest.mark.asyncio
    async def test_defer_queues_and_blocks_llm(self) -> None:
        npc = _active_npc("npc-5")  # will be registered as dormant
        cohort = _make_cohort(
            active_ids=["npc-0", "npc-1", "npc-2"],
            dormant_ids=["npc-3", "npc-4", "npc-5"],
        )
        engine, router, executor, _ = await _build_engine([npc], cohort=cohort)

        envelopes = await engine.notify(_exposure("npc-5"))

        assert router.route.await_count == 0  # no LLM
        assert executor.await_count == 0  # no pipeline
        assert envelopes == []
        # Event queued for later drain
        assert cohort.queue_depth(ActorId("npc-5")) == 1


class TestPromotePolicy:
    """Interview probes preempt-promote dormant NPCs."""

    @pytest.mark.asyncio
    async def test_interview_promotes_dormant_and_activates(self) -> None:
        npc = _active_npc("npc-5")
        cohort = _make_cohort(
            active_ids=["npc-0"],
            dormant_ids=["npc-1", "npc-2", "npc-5"],
            max_active=1,
            promote_budget=3,
        )
        engine, router, executor, _ = await _build_engine([npc], cohort=cohort)

        # First confirm npc-5 is dormant
        assert not cohort.is_active(ActorId("npc-5"))

        envelopes = await engine.notify(_interview("researcher-1", "npc-5"))

        # LLM fired → npc-5 promoted and activated
        assert router.route.await_count == 1
        assert executor.await_count == 1
        assert len(envelopes) == 1
        assert cohort.is_active(ActorId("npc-5"))

    @pytest.mark.asyncio
    async def test_promote_budget_exhausted_falls_back_to_defer(self) -> None:
        """When the promote budget is used up, further probes queue instead."""
        # Register 4 dormant NPCs we'll receive probes for.
        npcs = [_active_npc(f"npc-{i}") for i in range(2, 6)]
        cohort = _make_cohort(
            active_ids=["npc-0"],
            dormant_ids=["npc-1", "npc-2", "npc-3", "npc-4", "npc-5"],
            max_active=1,
            promote_budget=2,  # only 2 preempts allowed per window
        )
        engine, router, _, _ = await _build_engine(npcs, cohort=cohort)

        # 4 probes — first 2 preempt, last 2 fall back to defer
        for i in range(2, 6):
            await engine.notify(_interview("researcher", f"npc-{i}"))

        assert router.route.await_count == 2  # only 2 LLM calls — budget cap hit
        # The non-promoted ones were queued with exhausted-budget reason
        deferred_queues = [(i, cohort.queue_depth(ActorId(f"npc-{i}"))) for i in range(2, 6)]
        queued_total = sum(depth for _, depth in deferred_queues)
        assert queued_total == 2  # 2 fell back to defer


class TestAgentsExempt:
    """Agents (no activation_profile_name) never enter the cohort gate.

    Review fix D3: the gate predicate is extracted to
    ``AgencyEngine._should_cohort_gate`` and only actors with an
    ``activation_profile_name`` are gated. This test pins that
    contract so a future refactor can't widen the gate silently.
    """

    @pytest.mark.asyncio
    async def test_agent_not_gated_by_cohort(self) -> None:
        agent = _passive_agent("agent-lead")
        # Cohort only caps NPCs; agent is exempt regardless.
        cohort = _make_cohort(active_ids=["npc-0"], dormant_ids=["npc-1"], max_active=1)
        engine, _router, _executor, _ledger = await _build_engine([agent], cohort=cohort)
        # We're testing the GATE, not the full agent activation loop
        # (which needs more setup). The key assertion: the gate's
        # dormant branch doesn't fire for an actor with no profile.
        # Direct-unit check: cohort.is_active(agent.actor_id) is False
        # (not registered), but the gate must still allow fallthrough.
        # We introspect the branch by calling _activate_with_tool_loop
        # directly and checking the cohort's queue stays empty.
        agent_state = agent
        await engine._activate_with_tool_loop(agent_state, "event_affected", None)
        # No queueing happened — gate skipped because activation_profile_name is None.
        assert cohort.queue_depth(agent_state.actor_id) == 0

    @pytest.mark.asyncio
    async def test_should_cohort_gate_predicate_agent_false(self) -> None:
        """The extracted predicate must say 'no' for agents."""
        agent = _passive_agent("agent-lead")
        cohort = _make_cohort(active_ids=["npc-0"], dormant_ids=["npc-1"], max_active=1)
        engine, _, _, _ = await _build_engine([agent], cohort=cohort)
        assert engine._should_cohort_gate(agent, cohort) is False

    @pytest.mark.asyncio
    async def test_should_cohort_gate_predicate_dormant_npc_true(self) -> None:
        """The predicate must say 'yes' for a dormant NPC with profile."""
        # npc-9 is dormant (only npc-0 is initially active).
        npc = _active_npc("npc-9")
        cohort = _make_cohort(
            active_ids=["npc-0"],
            dormant_ids=["npc-1", "npc-9"],
            max_active=1,
        )
        engine, _, _, _ = await _build_engine([npc], cohort=cohort)
        assert engine._should_cohort_gate(npc, cohort) is True


class TestCohortDecisionLedger:
    """Review fix M4: every gate decision lands a ``CohortDecisionEntry``
    in the ledger so runners can explain why an NPC didn't activate.
    """

    @pytest.mark.asyncio
    async def test_defer_writes_decision_entry(self) -> None:
        npc = _active_npc("npc-5")
        cohort = _make_cohort(
            active_ids=["npc-0", "npc-1", "npc-2"],
            dormant_ids=["npc-3", "npc-4", "npc-5"],
        )
        engine, _, _, ledger = await _build_engine([npc], cohort=cohort)
        await engine.notify(_exposure("npc-5"))

        # Allow fire-and-forget ledger writes to flush
        import asyncio

        await asyncio.sleep(0.05)
        decisions = [e for e in ledger.entries if getattr(e, "entry_type", "") == "cohort_decision"]
        assert any(d.decision == "defer" for d in decisions), (
            f"No 'defer' decision recorded. Got: {[d.decision for d in decisions]}"
        )

    @pytest.mark.asyncio
    async def test_promote_writes_decision_entry_with_evicted_id(self) -> None:
        npc = _active_npc("npc-5")
        cohort = _make_cohort(
            active_ids=["npc-0"],
            dormant_ids=["npc-1", "npc-5"],
            max_active=1,
            promote_budget=3,
        )
        engine, _, _, ledger = await _build_engine([npc], cohort=cohort)
        await engine.notify(_interview("researcher", "npc-5"))

        import asyncio

        await asyncio.sleep(0.05)
        decisions = [e for e in ledger.entries if getattr(e, "entry_type", "") == "cohort_decision"]
        promote_decisions = [d for d in decisions if d.decision == "promote"]
        assert len(promote_decisions) == 1
        # Evicted id should be the previous active member.
        assert str(promote_decisions[0].evicted_actor_id) == "npc-0"

    @pytest.mark.asyncio
    async def test_budget_exhausted_writes_decision_entry(self) -> None:
        # Make budget=1, send 2 probes to 2 dormant NPCs.
        npcs = [_active_npc(f"npc-{i}") for i in (2, 3)]
        cohort = _make_cohort(
            active_ids=["npc-0"],
            dormant_ids=["npc-1", "npc-2", "npc-3"],
            max_active=1,
            promote_budget=1,
        )
        engine, _, _, ledger = await _build_engine(npcs, cohort=cohort)
        await engine.notify(_interview("researcher", "npc-2"))
        await engine.notify(_interview("researcher", "npc-3"))

        import asyncio

        await asyncio.sleep(0.05)
        decisions = [e for e in ledger.entries if getattr(e, "entry_type", "") == "cohort_decision"]
        exhausted = [d for d in decisions if d.decision == "promote_budget_exhausted"]
        assert len(exhausted) == 1
