"""Integration test: Full AgencyEngine loop with mock LLM.

Tests the EXACT same flow as the live test but with instant mock responses.
No codex-acp, no 10-minute waits, catches all bugs in seconds.

Flow tested:
  External action → ActionEnvelope → EventQueue → SimulationRunner →
  pipeline commits → AgencyEngine.notify() → Tier 1 check → Tier 2/3 LLM →
  internal actor ActionEnvelope → back to queue → pipeline → state updated
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from terrarium.actors.state import ActorBehaviorTraits, ActorState, WaitingFor
from terrarium.core.envelope import ActionEnvelope
from terrarium.core.events import WorldEvent
from terrarium.core.types import (
    ActionSource,
    ActorId,
    EnvelopePriority,
    EntityId,
    EventId,
    ServiceId,
    Timestamp,
)
from terrarium.engines.agency.config import AgencyConfig
from terrarium.engines.agency.engine import AgencyEngine
from terrarium.simulation.config import SimulationRunnerConfig
from terrarium.simulation.event_queue import EventQueue
from terrarium.simulation.runner import SimulationRunner, SimulationStatus, StopReason
from terrarium.simulation.world_context import WorldContextBundle


# ── Helpers ──────────────────────────────────────────────────


def _make_world_context() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="Support team with email and tickets.",
        reality_summary="Messy world, some data outdated.",
        behavior_mode="dynamic",
        behavior_description="World is alive.",
        mission="Resolve tickets.",
    )


def _make_actor_state(
    actor_id: str,
    role: str = "customer",
    frustration: float = 0.0,
    watched: list[str] | None = None,
    authority: float = 0.0,
) -> ActorState:
    return ActorState(
        actor_id=ActorId(actor_id),
        role=role,
        actor_type="internal",
        persona={"description": f"A {role} actor"},
        behavior_traits=ActorBehaviorTraits(
            cooperation_level=0.5,
            authority_level=authority,
            stakes_level=0.3,
        ),
        frustration=frustration,
        watched_entities=[EntityId(e) for e in (watched or [])],
    )


def _make_world_event(
    actor_id: str = "external-agent",
    action: str = "tickets.update",
    target_entity: str | None = None,
    source: ActionSource = ActionSource.EXTERNAL,
    tick: int = 1,
) -> WorldEvent:
    return WorldEvent(
        event_type=f"world.{action}",
        timestamp=Timestamp(
            world_time=datetime.now(UTC),
            wall_time=datetime.now(UTC),
            tick=tick,
        ),
        actor_id=ActorId(actor_id),
        service_id=ServiceId("zendesk"),
        action=action,
        target_entity=EntityId(target_entity) if target_entity else None,
        source=source,
    )


def _mock_llm_router(response_json: dict | list | None = None):
    """Create a mock LLM router that returns format-appropriate JSON responses.

    Individual (Tier 3) calls get: {"action_type": ..., "reasoning": ...}
    Batch (Tier 2) calls get: {"actor_actions": [{"actor_id": ..., "action_type": ...}]}
    """
    from terrarium.llm.types import LLMResponse

    individual_response = {
        "action_type": "email_send",
        "target_service": "email",
        "payload": {"to": "agent@acme.com", "subject": "Follow up", "body": "Where is my refund?"},
        "reasoning": "Customer is frustrated and wants an update.",
    }

    def _route_side_effect(request, engine_name="", use_case=""):
        # If a custom response was provided, use it for individual calls
        # AND derive batch response from it
        if response_json and "batch" in use_case:
            action_type = response_json.get("action_type", "do_nothing")
            import re
            prompt = request.user_content or ""
            ids = re.findall(r"\(ID:\s*([^)]+)\)", prompt)
            actor_actions = [
                {"actor_id": aid.strip(), "action_type": action_type,
                 "reasoning": response_json.get("reasoning", ""), **{
                     k: v for k, v in response_json.items()
                     if k not in ("action_type", "reasoning")
                 }}
                for aid in ids
            ]
            return LLMResponse(
                content=json.dumps({"actor_actions": actor_actions}),
                provider="mock", model="mock", latency_ms=5.0,
            )
        if "batch" in use_case:
            # Extract actor IDs from the prompt to build batch response
            prompt = request.user_content or ""
            # Build response for each actor mentioned
            actor_actions = []
            # Find actor IDs from batch prompt format: "(ID: customer-001)"
            import re
            ids = re.findall(r"\(ID:\s*([^)]+)\)", prompt)
            if not ids:
                ids = re.findall(r"Actor ID:\s*(\S+)", prompt)
            for aid in ids:
                aid = aid.strip("'\"`,")
                actor_actions.append({
                    "actor_id": aid,
                    "action_type": "email_send",
                    "target_service": "email",
                    "payload": {"to": "agent@acme.com"},
                    "reasoning": f"Actor {aid} wants update.",
                })
            # If no IDs found, return one generic action
            if not actor_actions:
                actor_actions = [{"actor_id": "unknown", "action_type": "do_nothing", "reasoning": "no context"}]

            return LLMResponse(
                content=json.dumps({"actor_actions": actor_actions}),
                provider="mock", model="mock", latency_ms=5.0,
            )
        else:
            return LLMResponse(
                content=json.dumps(response_json or individual_response),
                provider="mock", model="mock", latency_ms=5.0,
            )

    router = AsyncMock()
    router.route = AsyncMock(side_effect=_route_side_effect)
    return router


async def _create_agency_engine(
    actor_states: list[ActorState],
    world_context: WorldContextBundle | None = None,
    llm_router: AsyncMock | None = None,
) -> AgencyEngine:
    """Create and configure an AgencyEngine with mock dependencies."""
    engine = AgencyEngine()
    config = {
        "_llm_router": llm_router or _mock_llm_router(),
        "_actor_registry": AsyncMock(),
    }
    bus = AsyncMock()
    await engine.initialize(config, bus)

    # Configure with actor states
    ctx = world_context or _make_world_context()
    available_actions = [
        {"name": "email_send", "description": "Send email", "service": "email"},
        {"name": "tickets.update", "description": "Update ticket", "service": "tickets"},
    ]
    await engine.configure(actor_states, ctx, available_actions)
    return engine


# ── Tests ────────────────────────────────────────────────────


class TestFullLoopWithMockLLM:
    """Full SimulationRunner loop with mock LLM — instant, no codex-acp."""

    async def test_external_action_triggers_internal_actor(self):
        """External agent updates ticket → customer watching it activates → LLM generates action."""
        # Setup: 1 customer watching ticket tck_001
        customer = _make_actor_state("customer-001", watched=["tck_001"])
        engine = await _create_agency_engine([customer])

        # External event targets the watched ticket
        event = _make_world_event(target_entity="tck_001")

        # Notify → should activate customer → LLM call → ActionEnvelope
        envelopes = await engine.notify(event)

        assert len(envelopes) >= 1, "Customer should have generated an action"
        env = envelopes[0]
        assert str(env.actor_id) == "customer-001"
        assert env.source == ActionSource.INTERNAL
        assert env.action_type == "email_send"  # from mock response
        assert env.metadata.get("activation_reason") == "event_affected"

    async def test_supervisor_activates_as_tier3(self):
        """Supervisor (high authority) should be Tier 3 individual LLM call."""
        supervisor = _make_actor_state(
            "supervisor-001", role="supervisor",
            watched=["tck_001"], authority=0.8,
        )
        engine = await _create_agency_engine([supervisor])

        event = _make_world_event(target_entity="tck_001")
        envelopes = await engine.notify(event)

        assert len(envelopes) >= 1
        assert envelopes[0].metadata.get("activation_tier") == 3

    async def test_frustrated_customer_activates_as_tier3(self):
        """Customer with high frustration → Tier 3."""
        customer = _make_actor_state("customer-001", frustration=0.8, watched=["tck_001"])
        engine = await _create_agency_engine([customer])

        event = _make_world_event(target_entity="tck_001")
        envelopes = await engine.notify(event)

        assert len(envelopes) >= 1
        assert envelopes[0].metadata.get("activation_tier") == 3

    async def test_multiple_actors_different_tiers(self):
        """2 customers (Tier 2) + 1 supervisor (Tier 3) all watch same entity."""
        customer1 = _make_actor_state("cust-001", watched=["tck_001"])
        customer2 = _make_actor_state("cust-002", watched=["tck_001"])
        supervisor = _make_actor_state("sup-001", role="supervisor", watched=["tck_001"], authority=0.8)

        # Mock batch response for Tier 2 actors
        batch_response = {
            "actor_actions": [
                {"actor_id": "cust-001", "action_type": "email_send", "target_service": "email",
                 "payload": {}, "reasoning": "Checking status"},
                {"actor_id": "cust-002", "action_type": "do_nothing", "reasoning": "Will wait"},
            ]
        }
        from terrarium.llm.types import LLMResponse
        router = _mock_llm_router()
        # First call = batch (Tier 2), second call = individual (Tier 3)
        router.route = AsyncMock(side_effect=[
            # Tier 3 individual call (supervisor first since Tier 3 processed first)
            LLMResponse(
                content=json.dumps({"action_type": "tickets.update", "target_service": "tickets",
                                    "payload": {"id": "tck_001", "status": "open"}, "reasoning": "Reviewing"}),
                provider="mock", model="mock", latency_ms=5.0,
            ),
            # Tier 2 batch call (customers)
            LLMResponse(
                content=json.dumps(batch_response),
                provider="mock", model="mock", latency_ms=5.0,
            ),
        ])

        engine = await _create_agency_engine([customer1, customer2, supervisor], llm_router=router)
        event = _make_world_event(target_entity="tck_001")
        envelopes = await engine.notify(event)

        # Supervisor (Tier 3) + cust-001 (Tier 2, do action) = 2 envelopes
        # cust-002 said do_nothing = skipped
        assert len(envelopes) == 2
        actor_ids = {str(e.actor_id) for e in envelopes}
        assert "sup-001" in actor_ids
        assert "cust-001" in actor_ids

    async def test_no_activation_when_no_watched_entity_match(self):
        """If event doesn't touch watched entities, no activation."""
        customer = _make_actor_state("cust-001", watched=["tck_999"])
        engine = await _create_agency_engine([customer])

        event = _make_world_event(target_entity="tck_001")  # Different entity
        envelopes = await engine.notify(event)

        assert len(envelopes) == 0

    async def test_self_activation_skipped(self):
        """Actor should NOT activate from its own event."""
        customer = _make_actor_state("cust-001", watched=["tck_001"])
        engine = await _create_agency_engine([customer])

        # Event from the same actor
        event = _make_world_event(actor_id="cust-001", target_entity="tck_001")
        envelopes = await engine.notify(event)

        assert len(envelopes) == 0

    async def test_do_nothing_response_produces_no_envelope(self):
        """LLM says do_nothing → no envelope submitted."""
        customer = _make_actor_state("cust-001", watched=["tck_001"])
        router = _mock_llm_router({"action_type": "do_nothing", "reasoning": "Will wait"})
        engine = await _create_agency_engine([customer], llm_router=router)

        event = _make_world_event(target_entity="tck_001")
        envelopes = await engine.notify(event)

        assert len(envelopes) == 0

    async def test_state_updated_after_event(self):
        """Actor state (pending_notifications, recent_interactions) updated after notify."""
        customer = _make_actor_state("cust-001", watched=["tck_001"])
        engine = await _create_agency_engine([customer])

        event = _make_world_event(target_entity="tck_001")
        await engine.notify(event)

        state = engine._actor_states.get("cust-001")
        assert state is not None
        assert len(state.pending_notifications) > 0
        # recent_interactions updated via update_states_for_event (if called)

    async def test_max_envelopes_per_event_respected(self):
        """Config limits how many envelopes one event can produce."""
        # 10 actors all watching same entity
        actors = [_make_actor_state(f"cust-{i:03d}", watched=["tck_001"]) for i in range(10)]
        engine = await _create_agency_engine(actors)
        # Override config to limit to 3
        engine._typed_config = AgencyConfig(max_envelopes_per_event=3)

        event = _make_world_event(target_entity="tck_001")
        envelopes = await engine.notify(event)

        assert len(envelopes) <= 3


class TestSimulationRunnerLoop:
    """SimulationRunner processes envelopes through pipeline and notifies agency."""

    async def test_runner_processes_external_then_internal(self):
        """External envelope → pipeline → agency notified → internal envelope → pipeline."""
        event_queue = EventQueue()
        events_processed = []
        agency_notified = []

        # Mock pipeline: records what was processed
        async def mock_pipeline(envelope):
            events_processed.append(envelope)
            return _make_world_event(
                actor_id=str(envelope.actor_id),
                action=envelope.action_type,
                target_entity="tck_001",
            )

        # Mock agency: returns one internal envelope on first notify
        mock_agency = AsyncMock()
        call_count = [0]

        async def mock_notify(event):
            agency_notified.append(event)
            call_count[0] += 1
            if call_count[0] == 1:
                # First notify → internal actor reacts
                return [ActionEnvelope(
                    actor_id=ActorId("cust-001"),
                    source=ActionSource.INTERNAL,
                    action_type="email_send",
                    target_service=ServiceId("email"),
                    payload={"to": "agent@acme.com"},
                    logical_time=2.0,
                    priority=EnvelopePriority.INTERNAL,
                )]
            return []  # No more reactions

        mock_agency.notify = mock_notify
        mock_agency.check_scheduled_actions = AsyncMock(return_value=[])
        mock_agency.has_scheduled_actions = lambda: False
        mock_agency.update_states_for_event = AsyncMock()

        config = SimulationRunnerConfig(
            max_total_events=5,
            stop_on_empty_queue=True,
            loop_breaker_threshold=10,
        )

        runner = SimulationRunner(
            event_queue=event_queue,
            pipeline_executor=mock_pipeline,
            agency_engine=mock_agency,
            config=config,
        )

        # Submit external action
        event_queue.submit(ActionEnvelope(
            actor_id=ActorId("agent-001"),
            source=ActionSource.EXTERNAL,
            action_type="tickets.update",
            target_service=ServiceId("zendesk"),
            payload={"id": "tck_001"},
            logical_time=1.0,
            priority=EnvelopePriority.EXTERNAL,
        ))
        runner.connect_agent(ActorId("agent-001"))

        # Run
        stop_reason = await runner.run()

        # Verify
        assert stop_reason == StopReason.QUEUE_EMPTY
        assert len(events_processed) == 2  # external + internal
        assert str(events_processed[0].actor_id) == "agent-001"  # external first
        assert str(events_processed[1].actor_id) == "cust-001"  # then internal reaction
        assert len(agency_notified) == 2  # notified for both events
        mock_agency.update_states_for_event.assert_called()

    async def test_runner_stops_at_max_events(self):
        """Runner stops after max_total_events."""
        event_queue = EventQueue()

        async def mock_pipeline(envelope):
            return _make_world_event()

        mock_agency = AsyncMock()
        # Agency keeps producing events (would be infinite without limit)
        mock_agency.notify = AsyncMock(return_value=[
            ActionEnvelope(
                actor_id=ActorId("cust-001"),
                source=ActionSource.INTERNAL,
                action_type="email_send",
                logical_time=0.0,
                priority=EnvelopePriority.INTERNAL,
            )
        ])
        mock_agency.check_scheduled_actions = AsyncMock(return_value=[])
        mock_agency.has_scheduled_actions = lambda: False
        mock_agency.update_states_for_event = AsyncMock()

        config = SimulationRunnerConfig(max_total_events=3, loop_breaker_threshold=100)

        runner = SimulationRunner(
            event_queue=event_queue,
            pipeline_executor=mock_pipeline,
            agency_engine=mock_agency,
            config=config,
        )

        event_queue.submit(ActionEnvelope(
            actor_id=ActorId("agent-001"),
            source=ActionSource.EXTERNAL,
            action_type="test",
            logical_time=0.0,
        ))
        runner.connect_agent(ActorId("agent-001"))

        stop_reason = await runner.run()

        assert stop_reason == StopReason.MAX_EVENTS_REACHED
        assert runner.total_events_processed == 3

    async def test_runner_loop_breaker_triggers(self):
        """Loop breaker stops when too many events without external input."""
        event_queue = EventQueue()

        async def mock_pipeline(envelope):
            return _make_world_event()

        mock_agency = AsyncMock()
        mock_agency.notify = AsyncMock(return_value=[
            ActionEnvelope(
                actor_id=ActorId("cust-001"),
                source=ActionSource.INTERNAL,
                action_type="email_send",
                logical_time=0.0,
                priority=EnvelopePriority.INTERNAL,
            )
        ])
        mock_agency.check_scheduled_actions = AsyncMock(return_value=[])
        mock_agency.has_scheduled_actions = lambda: False
        mock_agency.update_states_for_event = AsyncMock()

        config = SimulationRunnerConfig(
            max_total_events=100,
            loop_breaker_threshold=5,
        )

        runner = SimulationRunner(
            event_queue=event_queue,
            pipeline_executor=mock_pipeline,
            agency_engine=mock_agency,
            config=config,
        )

        event_queue.submit(ActionEnvelope(
            actor_id=ActorId("agent-001"),
            source=ActionSource.EXTERNAL,
            action_type="test",
            logical_time=0.0,
        ))
        runner.connect_agent(ActorId("agent-001"))

        stop_reason = await runner.run()

        assert stop_reason == StopReason.LOOP_BREAKER

    async def test_runner_with_animator(self):
        """Animator produces environment events that get processed."""
        event_queue = EventQueue()
        events = []

        async def mock_pipeline(envelope):
            events.append(envelope)
            return _make_world_event(actor_id=str(envelope.actor_id), action=envelope.action_type)

        mock_animator = AsyncMock()
        call_count = [0]

        async def mock_check_scheduled(current_time):
            call_count[0] += 1
            if call_count[0] == 1:
                return [ActionEnvelope(
                    actor_id=ActorId("environment"),
                    source=ActionSource.ENVIRONMENT,
                    action_type="service_degradation",
                    logical_time=0.5,
                    priority=EnvelopePriority.ENVIRONMENT,
                )]
            return []

        mock_animator.check_scheduled_events = mock_check_scheduled
        mock_animator.notify_event = AsyncMock(return_value=[])
        mock_animator.has_scheduled_events = lambda: False

        config = SimulationRunnerConfig(
            max_total_events=5,
            stop_on_empty_queue=True,
        )

        runner = SimulationRunner(
            event_queue=event_queue,
            pipeline_executor=mock_pipeline,
            animator=mock_animator,
            config=config,
        )

        # Submit one external event to start the loop
        event_queue.submit(ActionEnvelope(
            actor_id=ActorId("agent-001"),
            source=ActionSource.EXTERNAL,
            action_type="test",
            logical_time=1.0,
        ))

        stop_reason = await runner.run()

        # Should have processed environment event (from animator) + external event
        assert len(events) >= 2
        sources = {e.source for e in events}
        assert ActionSource.ENVIRONMENT in sources
        assert ActionSource.EXTERNAL in sources


class TestWaitingForAndFrustration:
    """Test patience timeout → frustration → activation."""

    async def test_waiting_actor_activates_on_patience_expired(self):
        """Actor with expired patience triggers via wait_threshold."""
        customer = _make_actor_state("cust-001", watched=[])
        customer.waiting_for = WaitingFor(
            description="Waiting for refund confirmation",
            since=0.0,
            patience=5.0,  # patience runs out at tick 5
        )

        engine = await _create_agency_engine([customer])

        # Event at tick 10 — patience (5.0) expired since tick 0
        event = _make_world_event(tick=10)
        envelopes = await engine.notify(event)

        assert len(envelopes) >= 1
        assert envelopes[0].metadata.get("activation_reason") == "wait_threshold"

    async def test_waiting_actor_not_activated_before_patience(self):
        """Actor with remaining patience does NOT activate."""
        customer = _make_actor_state("cust-001", watched=[])
        customer.waiting_for = WaitingFor(
            description="Waiting for refund",
            since=0.0,
            patience=100.0,  # patience runs out at tick 100
        )

        engine = await _create_agency_engine([customer])

        event = _make_world_event(tick=5)  # Way before patience expires
        envelopes = await engine.notify(event)

        assert len(envelopes) == 0

    async def test_high_frustration_activates_without_watched_entity(self):
        """Frustrated actor activates even without matching watched entity."""
        customer = _make_actor_state("cust-001", frustration=0.9, watched=[])
        engine = await _create_agency_engine([customer])

        event = _make_world_event(target_entity="unrelated")
        envelopes = await engine.notify(event)

        assert len(envelopes) >= 1
        assert envelopes[0].metadata.get("activation_reason") == "frustration_threshold"
        assert envelopes[0].metadata.get("activation_tier") == 3  # High frustration → Tier 3
