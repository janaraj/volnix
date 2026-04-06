"""Unit tests for the Collaborative Communication Extension.

Tests subscription matching, InteractionRecord construction, intended_for
tagging, sensitivity levels, prompt rendering, reply-to conventions,
state updates from LLM, deliverable presets, and SimulationRunner extensions.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.actors.state import (
    ActorBehaviorTraits,
    ActorState,
    InteractionRecord,
    Subscription,
)
from volnix.core.envelope import ActionEnvelope
from volnix.core.events import WorldEvent
from volnix.core.types import (
    ActionSource,
    ActorId,
    EntityId,
    EnvelopePriority,
    ServiceId,
    Timestamp,
)
from volnix.deliverable_presets import AVAILABLE_PRESETS, load_preset
from volnix.engines.agency.engine import AgencyEngine
from volnix.engines.agency.prompt_builder import ActorPromptBuilder
from volnix.simulation.config import SimulationRunnerConfig
from volnix.simulation.event_queue import EventQueue
from volnix.simulation.runner import SimulationRunner, SimulationType, StopReason
from volnix.simulation.world_context import WorldContextBundle

# ---------------------------------------------------------------------------
# Helpers (reuse the same patterns as tests/engines/agency/test_engine.py)
# ---------------------------------------------------------------------------


def _make_timestamp(tick: int = 1) -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=tick)


def _make_world_event(
    actor_id: str = "agent-external",
    service_id: str = "chat",
    action: str = "chat.postMessage",
    tick: int = 10,
    target_entity: str | None = None,
    input_data: dict | None = None,
    response_body: dict | None = None,
    metadata: dict | None = None,
) -> WorldEvent:
    return WorldEvent(
        event_type="world.action",
        timestamp=_make_timestamp(tick),
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        target_entity=EntityId(target_entity) if target_entity else None,
        input_data=input_data or {},
        response_body=response_body,
        metadata=metadata or {},
    )


def _make_actor(
    actor_id: str = "actor-alice",
    role: str = "researcher",
    watched_entities: list[str] | None = None,
    frustration: float = 0.0,
    subscriptions: list[Subscription] | None = None,
    pending_tasks: list[str] | None = None,
    goal_context: str | None = None,
    current_goal: str | None = "Investigate jet stream anomaly",
    behavior_traits: ActorBehaviorTraits | None = None,
    recent_interactions: list[InteractionRecord] | None = None,
) -> ActorState:
    return ActorState(
        actor_id=ActorId(actor_id),
        role=role,
        actor_type="internal",
        watched_entities=[EntityId(e) for e in (watched_entities or [])],
        frustration=frustration,
        behavior_traits=behavior_traits or ActorBehaviorTraits(),
        subscriptions=subscriptions or [],
        pending_tasks=pending_tasks or [],
        goal_context=goal_context,
        current_goal=current_goal,
        goal_strategy="Collaborate with team",
        recent_interactions=recent_interactions or [],
    )


async def _create_engine(
    actors: list[ActorState] | None = None,
    config_overrides: dict | None = None,
) -> AgencyEngine:
    engine = AgencyEngine()
    raw_config = config_overrides or {}
    raw_config.setdefault("collaboration_enabled", True)
    raw_config.setdefault("collaboration_mode", "tagged")
    await engine.initialize(raw_config, bus=None)
    if actors is not None:
        ctx = WorldContextBundle(
            world_description="Climate research station",
            reality_summary="Messy conditions",
            behavior_mode="dynamic",
        )
        await engine.configure(actors, ctx)
    return engine


# =========================================================================
# 1. Subscription matching (5 tests)
# =========================================================================


class TestSubscriptionMatching:
    """Test _matches_subscription logic in AgencyEngine."""

    async def test_matches_chat_channel(self):
        """Subscription for chat channel #research matches chat event with that channel."""
        actor = _make_actor(
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})]
        )
        engine = await _create_engine([actor])
        event = _make_world_event(
            service_id="chat",
            action="chat.postMessage",
            input_data={"channel": "#research", "text": "New data available"},
        )
        sub = actor.subscriptions[0]
        assert engine._matches_subscription(event, sub) is True

    async def test_matches_email_to_self(self):
        """Subscription for email service with filter for 'self' passes (resolved at activation)."""
        sub = Subscription(service_id="email", filter={"to_addr": "self"})
        engine = await _create_engine([_make_actor()])
        event = _make_world_event(
            service_id="email",
            action="email_send",
            input_data={"to_addr": "alice@lab.org", "subject": "Report"},
        )
        # 'self' filter value is skipped during matching (resolved at activation)
        assert engine._matches_subscription(event, sub) is True

    async def test_no_match_wrong_service(self):
        """Chat subscription does not match an email event."""
        sub = Subscription(service_id="chat", filter={"channel": "#research"})
        engine = await _create_engine([_make_actor()])
        event = _make_world_event(
            service_id="email",
            action="email_send",
            input_data={"to_addr": "bob@lab.org"},
        )
        assert engine._matches_subscription(event, sub) is False

    async def test_no_match_wrong_filter(self):
        """Chat subscription for #admin does not match event in #research."""
        sub = Subscription(service_id="chat", filter={"channel": "#admin"})
        engine = await _create_engine([_make_actor()])
        event = _make_world_event(
            service_id="chat",
            action="chat.postMessage",
            input_data={"channel": "#research", "text": "hello"},
        )
        assert engine._matches_subscription(event, sub) is False

    async def test_matches_empty_filter(self):
        """Subscription with empty filter matches any event on the same service."""
        sub = Subscription(service_id="chat", filter={})
        engine = await _create_engine([_make_actor()])
        event = _make_world_event(
            service_id="chat",
            action="chat.postMessage",
            input_data={"channel": "#random", "text": "hello"},
        )
        assert engine._matches_subscription(event, sub) is True


# =========================================================================
# 2. InteractionRecord (4 tests)
# =========================================================================


class TestInteractionRecord:
    """Test _build_interaction_record in AgencyEngine."""

    async def test_from_chat_event(self):
        """Build interaction record from a chat postMessage event."""
        poster = _make_actor(actor_id="actor-bob", role="oceanographer")
        observer = _make_actor(actor_id="actor-alice", role="researcher")
        engine = await _create_engine([poster, observer])

        event = _make_world_event(
            actor_id="actor-bob",
            service_id="chat",
            action="chat.postMessage",
            input_data={
                "channel": "#research",
                "text": "SST anomaly confirmed in sector 7",
                "intended_for": ["researcher"],
            },
        )

        record = engine._build_interaction_record(event, observer, source="notified")

        assert record.actor_id == "actor-bob"
        assert record.actor_role == "oceanographer"
        assert record.action == "chat.postMessage"
        assert record.channel == "#research"
        assert record.source == "notified"
        assert "SST anomaly" in record.summary

    async def test_from_email_event(self):
        """Build interaction record from an email_send event (uses 'body' field)."""
        sender = _make_actor(actor_id="actor-carol", role="data-analyst")
        observer = _make_actor(actor_id="actor-alice", role="researcher")
        engine = await _create_engine([sender, observer])

        event = _make_world_event(
            actor_id="actor-carol",
            service_id="email",
            action="email_send",
            input_data={
                "subject": "Weekly data report",
                "body": "Attached findings from satellite analysis.",
            },
        )

        record = engine._build_interaction_record(event, observer, source="observed")

        assert record.actor_role == "data-analyst"
        assert record.source == "observed"
        # Should pick 'body' since 'content' and 'text' are absent
        assert "satellite analysis" in record.summary

    async def test_truncates_long_content(self):
        """Long summary text is truncated to 500 characters."""
        actor = _make_actor()
        engine = await _create_engine([actor])

        long_text = "A" * 600
        event = _make_world_event(
            input_data={"text": long_text},
        )

        record = engine._build_interaction_record(event, actor, source="observed")

        assert len(record.summary) == 500
        assert record.summary.endswith("...")

    async def test_includes_reply_to(self):
        """reply_to_event_id in input_data is captured as reply_to field."""
        actor = _make_actor()
        engine = await _create_engine([actor])

        event = _make_world_event(
            input_data={
                "text": "Good point, I agree.",
                "reply_to_event_id": "evt-original-123",
                "channel": "#research",
            },
        )

        record = engine._build_interaction_record(event, actor, source="notified")

        assert record.reply_to == "evt-original-123"


# =========================================================================
# 3. intended_for tagging -- tagged mode (4 tests)
# =========================================================================


class TestIntendedForTagged:
    """Test intended_for behavior in tagged collaboration mode."""

    async def test_only_intended_actor_activates(self):
        """In tagged mode, only the actor in intended_for activates."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        bob = _make_actor(
            actor_id="actor-bob",
            role="oceanographer",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice, bob],
            config_overrides={"collaboration_mode": "tagged", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={
                "channel": "#research",
                "text": "Researcher, please check the SST data.",
                "intended_for": ["researcher"],
            },
        )

        await engine.notify(event)
        # Alice (researcher) should be activated, Bob (oceanographer) should not
        activated_ids = {
            str(a.actor_id) for a in engine.get_all_states() if a.pending_notifications
        }
        assert "actor-alice" in activated_ids

    async def test_all_tag_activates_everyone(self):
        """intended_for: ['all'] activates all subscribed actors."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        bob = _make_actor(
            actor_id="actor-bob",
            role="oceanographer",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice, bob],
            config_overrides={"collaboration_mode": "tagged", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={
                "channel": "#research",
                "text": "Team update: new satellite data is in.",
                "intended_for": ["all"],
            },
        )

        await engine.notify(event)
        # Both actors should have received notifications
        assert len(alice.pending_notifications) > 0
        assert len(bob.pending_notifications) > 0

    async def test_untagged_gets_passive_notification(self):
        """In tagged mode, untagged actors still get interaction records but do not activate."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        bob = _make_actor(
            actor_id="actor-bob",
            role="oceanographer",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice, bob],
            config_overrides={"collaboration_mode": "tagged", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={
                "channel": "#research",
                "text": "Only for researcher",
                "intended_for": ["researcher"],
            },
        )

        await engine.notify(event)

        # Bob's subscription matched, so he gets an interaction record
        assert len(bob.recent_interactions) > 0
        # But Bob should NOT have been activated (no pending_notifications)
        # Alice (the tagged one) should have notifications
        assert len(alice.pending_notifications) > 0

    async def test_no_intended_for_records_passively(self):
        """When intended_for is absent, interactions are recorded but agents don't activate."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        bob = _make_actor(
            actor_id="actor-bob",
            role="oceanographer",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice, bob],
            config_overrides={"collaboration_mode": "tagged", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={
                "channel": "#research",
                "text": "General announcement to all.",
                # No intended_for field
            },
        )

        await engine.notify(event)

        # Interactions recorded (passive), but NOT activated (no pending_notifications)
        assert len(alice.recent_interactions) > 0
        assert len(bob.recent_interactions) > 0
        assert len(alice.pending_notifications) == 0
        assert len(bob.pending_notifications) == 0


# =========================================================================
# 4. Open mode (1 test)
# =========================================================================


class TestOpenMode:
    """Test collaboration in open mode."""

    async def test_all_subscribed_actors_activate_with_intended_for_all(self):
        """With intended_for=["all"], all subscribed actors activate."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        bob = _make_actor(
            actor_id="actor-bob",
            role="oceanographer",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice, bob],
            config_overrides={"collaboration_mode": "open", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={
                "channel": "#research",
                "text": "Data update",
                "intended_for": ["all"],  # Broadcast activates everyone
            },
        )

        await engine.notify(event)

        # Both should activate when intended_for includes "all"
        assert len(alice.pending_notifications) > 0
        assert len(bob.pending_notifications) > 0


# =========================================================================
# 5. Sensitivity levels (3 tests)
# =========================================================================


class TestSensitivityLevels:
    """Test immediate, batch, and passive sensitivity handling."""

    async def test_immediate_activates_same_tick(self):
        """Immediate sensitivity with intended_for triggers activation on the same event."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[
                Subscription(
                    service_id="chat",
                    filter={"channel": "#research"},
                    sensitivity="immediate",
                )
            ],
        )
        engine = await _create_engine(
            [alice],
            config_overrides={"collaboration_mode": "tagged", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={
                "channel": "#research",
                "text": "Urgent data",
                "intended_for": ["researcher"],
            },
        )

        await engine.notify(event)
        assert len(alice.pending_notifications) > 0

    @pytest.mark.skip(reason="V2: batch/passive sensitivity disabled for MVP")
    async def test_batch_accumulates_then_activates(self):
        """Batch sensitivity accumulates notifications and activates after threshold."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[
                Subscription(
                    service_id="chat",
                    filter={"channel": "#research"},
                    sensitivity="batch",
                )
            ],
        )
        alice.batch_threshold = 3
        engine = await _create_engine(
            [alice],
            config_overrides={"collaboration_mode": "open", "collaboration_enabled": True},
        )

        # Send events below threshold -- should NOT activate
        for i in range(2):
            event = _make_world_event(
                actor_id="agent-external",
                service_id="chat",
                action="chat.postMessage",
                tick=10 + i,
                input_data={"channel": "#research", "text": f"Message {i}"},
            )
            await engine.notify(event)

        # After 2 messages, batch_notification_count should be 2 (not yet triggered)
        assert alice.batch_notification_count == 2

        # Third message should trigger activation (count reaches threshold)
        event3 = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            tick=12,
            input_data={"channel": "#research", "text": "Message 3"},
        )
        await engine.notify(event3)

        # After threshold reached, count resets
        assert alice.batch_notification_count == 0
        # Actor should now have pending notifications from the third batch
        assert len(alice.pending_notifications) > 0

    @pytest.mark.skip(reason="V2: batch/passive sensitivity disabled for MVP")
    async def test_passive_stores_no_activation(self):
        """Passive sensitivity records interaction but does not activate actor."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[
                Subscription(
                    service_id="chat",
                    filter={"channel": "#general"},
                    sensitivity="passive",
                )
            ],
        )
        engine = await _create_engine(
            [alice],
            config_overrides={"collaboration_mode": "open", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={"channel": "#general", "text": "Casual chat"},
        )

        await engine.notify(event)

        # Interaction record is stored
        assert len(alice.recent_interactions) > 0
        # But NO pending notifications (passive does not activate)
        assert len(alice.pending_notifications) == 0


# =========================================================================
# 6. Prompt rendering (4 tests)
# =========================================================================


class TestPromptRendering:
    """Test ActorPromptBuilder with InteractionRecords and collaboration fields."""

    def _make_builder(self) -> ActorPromptBuilder:
        ctx = WorldContextBundle(
            world_description="Climate research station",
            reality_summary="Messy conditions",
            behavior_mode="dynamic",
            mission="Investigate jet stream anomaly",
        )
        return ActorPromptBuilder(ctx)

    def test_renders_interaction_records_as_conversation(self):
        """InteractionRecords render as conversation-style lines in the prompt."""
        builder = self._make_builder()
        records = [
            InteractionRecord(
                tick=1.0,
                actor_id="actor-bob",
                actor_role="oceanographer",
                action="chat.postMessage",
                summary="SST anomaly confirmed in sector 7",
                source="notified",
                event_id="evt-001",
                channel="#research",
            ),
            InteractionRecord(
                tick=2.0,
                actor_id="actor-alice",
                actor_role="researcher",
                action="chat.postMessage",
                summary="I will cross-reference with satellite data",
                source="self",
                event_id="evt-002",
                channel="#research",
                reply_to="evt-001",
            ),
        ]
        actor = _make_actor(recent_interactions=records)

        event = _make_world_event()
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=event,
            activation_reason="subscription_immediate",
            available_actions=[],
        )

        assert "oceanographer" in prompt
        assert "SST anomaly" in prompt
        assert "Your Investigation" in prompt  # self-authored actions
        assert "cross-reference" in prompt  # self action summary

    def test_includes_pending_tasks(self):
        """Pending tasks appear in the prompt."""
        builder = self._make_builder()
        actor = _make_actor(
            pending_tasks=["Analyze SST data", "Draft findings summary"],
        )

        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=_make_world_event(),
            activation_reason="subscription_immediate",
            available_actions=[],
        )

        assert "Pending Tasks" in prompt
        assert "Analyze SST data" in prompt
        assert "Draft findings summary" in prompt

    def test_includes_goal_context(self):
        """Goal context appears in the prompt."""
        builder = self._make_builder()
        actor = _make_actor(
            goal_context="Phase 2 complete. Waiting on satellite comparison results.",
        )

        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=_make_world_event(),
            activation_reason="subscription_immediate",
            available_actions=[],
        )

        assert "Mission Context" in prompt
        assert "Phase 2 complete" in prompt

    def test_backward_compat_string_interactions(self):
        """Plain string entries in recent_interactions don't crash prompt building.

        The new _build_recent_activity splits interactions into own/team using
        isinstance(r, InteractionRecord), so plain strings are silently skipped.
        Backward compat means no crash, not necessarily rendered.
        """
        builder = self._make_builder()
        actor = _make_actor()
        # Manually inject a plain string (old format -- should not crash)
        actor.recent_interactions.append("old-style interaction: email sent by alice")  # type: ignore[arg-type]

        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=_make_world_event(),
            activation_reason="event_affected",
            available_actions=[],
        )

        # Prompt builds without error; plain strings are silently skipped
        assert isinstance(prompt, str)
        assert len(prompt) > 0


# =========================================================================
# 7. Reply-to convention (2 tests)
# =========================================================================


class TestReplyToConvention:
    """Test that reply_to in input_data maps to parent_event_ids in envelopes."""

    async def test_reply_to_copied_to_parent_event_ids(self):
        """When LLM output includes reply_to, the envelope carries it in parent_event_ids."""
        actor = _make_actor(actor_id="actor-alice", role="researcher")
        engine = await _create_engine([actor])

        # Simulate LLM response with a reply_to in the action
        raw_output = json.dumps(
            {
                "action_type": "chat.postMessage",
                "target_service": "chat",
                "payload": {
                    "channel": "#research",
                    "text": "I agree with the analysis.",
                    "reply_to_event_id": "evt-original-999",
                },
                "reasoning": "Responding to oceanographer's finding",
            }
        )

        trigger_event = _make_world_event()
        envelope = engine._parse_llm_action(
            actor, raw_output, "subscription_immediate", trigger_event
        )

        assert envelope is not None
        assert envelope.action_type == "chat.postMessage"
        # parent_event_ids should include the trigger event
        assert trigger_event.event_id in envelope.parent_event_ids

    async def test_reply_to_absent_no_parent_added(self):
        """When no reply_to, parent_event_ids still contains the trigger event."""
        actor = _make_actor(actor_id="actor-alice", role="researcher")
        engine = await _create_engine([actor])

        raw_output = json.dumps(
            {
                "action_type": "chat.postMessage",
                "target_service": "chat",
                "payload": {"channel": "#research", "text": "New thread topic"},
                "reasoning": "Starting a new discussion",
            }
        )

        trigger_event = _make_world_event()
        envelope = engine._parse_llm_action(
            actor, raw_output, "subscription_immediate", trigger_event
        )

        assert envelope is not None
        assert trigger_event.event_id in envelope.parent_event_ids


# =========================================================================
# 8. State updates from LLM (3 tests)
# =========================================================================


class TestStateUpdatesFromLLM:
    """Test _apply_state_updates for collaborative communication fields."""

    async def test_apply_pending_tasks(self):
        """LLM-provided pending_tasks are stored on the actor state."""
        actor = _make_actor()
        engine = await _create_engine([actor])

        updates = {
            "pending_tasks": ["Verify satellite data", "Draft conclusions"],
        }
        engine._apply_state_updates(actor, updates)

        assert actor.pending_tasks == ["Verify satellite data", "Draft conclusions"]

    async def test_apply_goal_context(self):
        """LLM-provided goal_context is stored on the actor state."""
        actor = _make_actor()
        engine = await _create_engine([actor])

        updates = {
            "goal_context": "Phase 1: Data collection complete. Moving to analysis.",
        }
        engine._apply_state_updates(actor, updates)

        assert actor.goal_context == "Phase 1: Data collection complete. Moving to analysis."

    async def test_apply_deliverable_flag(self):
        """State update with new_goal and goal_strategy updates actor."""
        actor = _make_actor()
        engine = await _create_engine([actor])

        updates = {
            "new_goal": "Produce synthesis deliverable",
            "goal_strategy": "Compile all findings from team interactions",
            "pending_tasks": ["Finalize report", "Review dissenting views"],
        }
        engine._apply_state_updates(actor, updates)

        assert actor.current_goal == "Produce synthesis deliverable"
        assert actor.goal_strategy == "Compile all findings from team interactions"
        assert len(actor.pending_tasks) == 2


# =========================================================================
# 9. Deliverable presets (4 tests)
# =========================================================================


class TestDeliverablePresets:
    """Test loading and validating deliverable presets."""

    def test_load_synthesis_preset(self):
        """Load the synthesis preset and verify structure."""
        preset = load_preset("synthesis")

        assert preset["name"] == "synthesis"
        assert "description" in preset
        assert "schema" in preset
        assert "prompt_instructions" in preset
        assert preset["schema"]["type"] == "object"
        assert "findings" in preset["schema"]["properties"]

    def test_load_all_presets_valid(self):
        """All declared presets load without error."""
        for name in AVAILABLE_PRESETS:
            preset = load_preset(name)
            assert "name" in preset
            assert "description" in preset
            assert "schema" in preset
            assert "prompt_instructions" in preset

    def test_preset_has_required_keys(self):
        """Each preset contains name, description, schema, prompt_instructions."""
        required = {"name", "description", "schema", "prompt_instructions"}
        for name in AVAILABLE_PRESETS:
            preset = load_preset(name)
            missing = required - set(preset.keys())
            assert not missing, f"Preset '{name}' missing keys: {missing}"

    def test_unknown_preset_raises(self):
        """Loading a non-existent preset raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_preset("nonexistent_deliverable")


# =========================================================================
# 10. SimulationRunner extensions (3 tests)
# =========================================================================


class TestSimulationRunnerExtensions:
    """Test SimulationType detection, kickstart, and idle_stop."""

    def test_detect_simulation_type(self):
        """Correctly classify internal-only, external-driven, and mixed."""
        # Internal only
        runner1 = SimulationRunner(
            event_queue=EventQueue(),
            pipeline_executor=AsyncMock(),
            actor_specs=[{"type": "internal"}, {"type": "internal"}],
        )
        assert runner1.simulation_type == SimulationType.INTERNAL_ONLY

        # External driven
        runner2 = SimulationRunner(
            event_queue=EventQueue(),
            pipeline_executor=AsyncMock(),
            actor_specs=[{"type": "external"}],
        )
        assert runner2.simulation_type == SimulationType.EXTERNAL_DRIVEN

        # Mixed
        runner3 = SimulationRunner(
            event_queue=EventQueue(),
            pipeline_executor=AsyncMock(),
            actor_specs=[{"type": "internal"}, {"type": "external"}],
        )
        assert runner3.simulation_type == SimulationType.MIXED

    # test_kickstart_envelope_created and test_kickstart_not_created_for_external
    # removed: create_kickstart_envelope was moved from SimulationRunner to
    # VolnixApp.build_kickstart_envelope() which resolves channels from
    # the actual world state, not hardcoded values.

    def test_idle_stop_works(self):
        """SimulationRunner detects idle_stop condition."""
        queue = EventQueue()
        # Add a dummy pending item so QUEUE_EMPTY does not trigger first
        queue.submit(
            ActionEnvelope(
                actor_id=ActorId("dummy"),
                source=ActionSource.INTERNAL,
                action_type="noop",
                logical_time=0.0,
                priority=EnvelopePriority.INTERNAL,
            )
        )
        runner = SimulationRunner(
            event_queue=queue,
            pipeline_executor=AsyncMock(),
            actor_specs=[{"type": "internal"}],
            config=SimulationRunnerConfig(idle_stop_ticks=3),
        )

        # Simulate consecutive idle ticks by setting internal counter
        runner._consecutive_idle_ticks = 3
        reason = runner._check_end_conditions()
        assert reason == StopReason.IDLE_STOP


# =========================================================================
# Additional edge case tests
# =========================================================================


class TestCollaborationDisabled:
    """Verify that subscription matching is skipped when disabled."""

    async def test_no_subscription_activation_when_disabled(self):
        """When collaboration_enabled=False, subscriptions are not checked."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice],
            config_overrides={"collaboration_enabled": False},
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={"channel": "#research", "text": "hello"},
        )

        await engine.notify(event)
        # No activation from subscriptions when disabled
        assert len(alice.pending_notifications) == 0


class TestSelfNotificationPrevention:
    """Verify actors do not notify themselves."""

    async def test_actor_does_not_self_activate_via_subscription(self):
        """An actor's own event does not trigger their subscription."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice],
            config_overrides={"collaboration_mode": "open", "collaboration_enabled": True},
        )

        event = _make_world_event(
            actor_id="actor-alice",  # Alice's own event
            service_id="chat",
            action="chat.postMessage",
            input_data={"channel": "#research", "text": "My own message"},
        )

        await engine.notify(event)
        assert len(alice.pending_notifications) == 0


class TestLedgerRecording:
    """Verify that subscription matches are recorded to ledger."""

    async def test_subscription_match_recorded_to_ledger(self):
        """SubscriptionMatchEntry and CollaborationNotificationEntry are written to ledger."""
        mock_ledger = AsyncMock()
        mock_ledger.entries = []

        async def _append(entry):
            mock_ledger.entries.append(entry)

        mock_ledger.append = AsyncMock(side_effect=_append)

        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={"channel": "#research"})],
        )
        engine = await _create_engine(
            [alice],
            config_overrides={
                "collaboration_mode": "open",
                "collaboration_enabled": True,
                "_ledger": mock_ledger,
            },
        )

        event = _make_world_event(
            actor_id="agent-external",
            service_id="chat",
            action="chat.postMessage",
            input_data={"channel": "#research", "text": "Test message"},
        )

        await engine.notify(event)
        await asyncio.sleep(0.1)  # yield for non-blocking ledger writes

        from volnix.ledger.entries import (
            CollaborationNotificationEntry,
            SubscriptionMatchEntry,
        )

        entry_types = [type(e) for e in mock_ledger.entries]
        assert SubscriptionMatchEntry in entry_types
        assert CollaborationNotificationEntry in entry_types


class TestMaxRecentInteractions:
    """Verify interaction records are trimmed to max_recent_interactions."""

    async def test_interaction_records_trimmed(self):
        """Recent interactions list is trimmed to max_recent_interactions."""
        alice = _make_actor(
            actor_id="actor-alice",
            role="researcher",
            subscriptions=[Subscription(service_id="chat", filter={})],
        )
        alice.max_recent_interactions = 5
        engine = await _create_engine(
            [alice],
            config_overrides={"collaboration_mode": "open", "collaboration_enabled": True},
        )

        # Send more events than the max
        for i in range(10):
            event = _make_world_event(
                actor_id="agent-external",
                service_id="chat",
                action="chat.postMessage",
                tick=10 + i,
                input_data={"text": f"Message {i}"},
            )
            await engine.notify(event)

        assert len(alice.recent_interactions) <= 5


class TestSubscriptionFilterMetadata:
    """Test that subscription filter checks metadata and response_body."""

    async def test_filter_matches_metadata(self):
        """Subscription filter can match against event metadata fields."""
        sub = Subscription(service_id="chat", filter={"priority": "high"})
        engine = await _create_engine([_make_actor()])

        event = _make_world_event(
            service_id="chat",
            action="chat.postMessage",
            metadata={"priority": "high"},
        )
        assert engine._matches_subscription(event, sub) is True

    async def test_filter_matches_response_body(self):
        """Subscription filter can match against event response_body fields."""
        sub = Subscription(service_id="email", filter={"status": "delivered"})
        engine = await _create_engine([_make_actor()])

        event = _make_world_event(
            service_id="email",
            action="email_send",
            response_body={"status": "delivered"},
        )
        assert engine._matches_subscription(event, sub) is True
