"""Tests for volnix.actors.state and ActorRegistry state management."""

import pytest
from pydantic import ValidationError

from volnix.actors.definition import ActorDefinition
from volnix.actors.registry import ActorRegistry
from volnix.actors.state import (
    ActorBehaviorTraits,
    ActorState,
    InteractionRecord,
    ScheduledAction,
    WaitingFor,
)
from volnix.core.types import ActorId, ActorType, EntityId


class TestActorStateCreation:
    """Verify ActorState model creation and defaults."""

    def test_actor_state_creation(self) -> None:
        """ActorState can be created with required fields and sensible defaults."""
        state = ActorState(actor_id=ActorId("agent-1"), role="support-agent")
        assert state.actor_id == ActorId("agent-1")
        assert state.role == "support-agent"
        assert state.actor_type == "internal"
        assert state.persona == {}
        assert state.current_goal is None
        assert state.goal_strategy is None
        assert state.waiting_for is None
        assert state.frustration == 0.0
        assert state.urgency == 0.3
        assert state.pending_notifications == []
        assert state.recent_interactions == []
        assert state.scheduled_actions == []
        assert state.activation_tier == 0
        assert state.watched_entities == []
        assert state.max_recent_interactions == 20

    def test_actor_state_with_all_fields(self) -> None:
        """ActorState accepts all optional fields."""
        traits = ActorBehaviorTraits(
            cooperation_level=0.8,
            deception_risk=0.1,
            authority_level=0.5,
            stakes_level=0.7,
            ambient_activity_rate=0.3,
        )
        waiting = WaitingFor(
            description="Waiting for approval",
            since=10.0,
            patience=5.0,
            escalation_action="escalate_to_manager",
        )
        scheduled = ScheduledAction(
            logical_time=20.0,
            action_type="send_reminder",
            description="Send follow-up email",
            target_service="email",
            payload={"template": "reminder"},
        )
        state = ActorState(
            actor_id=ActorId("agent-2"),
            role="manager",
            actor_type="internal",
            persona={"name": "Jane", "department": "HR"},
            behavior_traits=traits,
            current_goal="Process leave request",
            goal_strategy="Check policy then approve",
            waiting_for=waiting,
            frustration=0.4,
            urgency=0.8,
            pending_notifications=["New leave request"],
            recent_interactions=[
                InteractionRecord(
                    tick=1.0,
                    actor_id="bob",
                    actor_role="employee",
                    action="submit_leave_request",
                    summary="Received request from Bob",
                    source="observed",
                    event_id="evt-1",
                ),
            ],
            scheduled_actions=[scheduled],
            activation_tier=2,
            watched_entities=[EntityId("leave-req-001")],
        )
        assert state.behavior_traits.cooperation_level == 0.8
        assert state.waiting_for is not None
        assert state.waiting_for.escalation_action == "escalate_to_manager"
        assert len(state.scheduled_actions) == 1
        assert state.scheduled_actions[0].payload == {"template": "reminder"}
        assert state.activation_tier == 2
        assert EntityId("leave-req-001") in state.watched_entities


class TestWaitingForFrozen:
    """Verify WaitingFor is immutable."""

    def test_waiting_for_frozen(self) -> None:
        """WaitingFor instances cannot be mutated after creation."""
        wf = WaitingFor(description="Waiting for response", since=1.0, patience=10.0)
        with pytest.raises(ValidationError):
            wf.description = "Changed"  # type: ignore[misc]

    def test_waiting_for_fields(self) -> None:
        """WaitingFor stores all fields correctly."""
        wf = WaitingFor(
            description="Approval pending",
            since=5.0,
            patience=15.0,
            escalation_action="notify_ceo",
        )
        assert wf.description == "Approval pending"
        assert wf.since == 5.0
        assert wf.patience == 15.0
        assert wf.escalation_action == "notify_ceo"


class TestScheduledActionFrozen:
    """Verify ScheduledAction is immutable."""

    def test_scheduled_action_frozen(self) -> None:
        """ScheduledAction instances cannot be mutated after creation."""
        sa = ScheduledAction(
            logical_time=10.0,
            action_type="send_email",
            description="Follow up",
        )
        with pytest.raises(ValidationError):
            sa.action_type = "changed"  # type: ignore[misc]

    def test_scheduled_action_defaults(self) -> None:
        """ScheduledAction has correct defaults for optional fields."""
        sa = ScheduledAction(
            logical_time=10.0,
            action_type="check_status",
            description="Periodic check",
        )
        assert sa.target_service is None
        assert sa.payload == {}


class TestBehaviorTraitsDefaults:
    """Verify ActorBehaviorTraits defaults and immutability."""

    def test_behavior_traits_defaults(self) -> None:
        """ActorBehaviorTraits has correct default values."""
        traits = ActorBehaviorTraits()
        assert traits.cooperation_level == 0.5
        assert traits.deception_risk == 0.0
        assert traits.authority_level == 0.0
        assert traits.stakes_level == 0.3
        assert traits.ambient_activity_rate == 0.1

    def test_behavior_traits_frozen(self) -> None:
        """ActorBehaviorTraits instances cannot be mutated after creation."""
        traits = ActorBehaviorTraits()
        with pytest.raises(ValidationError):
            traits.cooperation_level = 0.9  # type: ignore[misc]


class TestActorStateMutable:
    """Verify ActorState is mutable (not frozen)."""

    def test_frustration_can_be_updated(self) -> None:
        """ActorState.frustration can be changed in place."""
        state = ActorState(actor_id=ActorId("a1"), role="customer")
        assert state.frustration == 0.0
        state.frustration = 0.75
        assert state.frustration == 0.75

    def test_urgency_can_be_updated(self) -> None:
        """ActorState.urgency can be changed in place."""
        state = ActorState(actor_id=ActorId("a1"), role="customer")
        state.urgency = 0.9
        assert state.urgency == 0.9

    def test_current_goal_can_be_updated(self) -> None:
        """ActorState.current_goal can be changed in place."""
        state = ActorState(actor_id=ActorId("a1"), role="customer")
        state.current_goal = "Get refund"
        assert state.current_goal == "Get refund"

    def test_waiting_for_can_be_set(self) -> None:
        """ActorState.waiting_for can be assigned."""
        state = ActorState(actor_id=ActorId("a1"), role="customer")
        assert state.waiting_for is None
        state.waiting_for = WaitingFor(description="Waiting for agent", since=1.0, patience=5.0)
        assert state.waiting_for is not None
        assert state.waiting_for.description == "Waiting for agent"

    def test_pending_notifications_appendable(self) -> None:
        """ActorState.pending_notifications list can be appended to."""
        state = ActorState(actor_id=ActorId("a1"), role="customer")
        state.pending_notifications.append("New message")
        assert len(state.pending_notifications) == 1

    def test_activation_tier_can_be_updated(self) -> None:
        """ActorState.activation_tier can be changed."""
        state = ActorState(actor_id=ActorId("a1"), role="customer")
        state.activation_tier = 3
        assert state.activation_tier == 3


class TestRegistryStateManagement:
    """Verify ActorRegistry state management methods."""

    def _make_state(
        self,
        actor_id: str = "a1",
        role: str = "customer",
        actor_type: str = "internal",
        watched: list[str] | None = None,
    ) -> ActorState:
        """Helper to create test ActorState instances."""
        return ActorState(
            actor_id=ActorId(actor_id),
            role=role,
            actor_type=actor_type,
            watched_entities=[EntityId(e) for e in (watched or [])],
        )

    def test_set_and_get_actor_state(self) -> None:
        """set_actor_state stores state; get_actor_state retrieves it."""
        reg = ActorRegistry()
        state = self._make_state("a1", "customer")
        reg.set_actor_state(ActorId("a1"), state)
        result = reg.get_actor_state(ActorId("a1"))
        assert result is not None
        assert result.actor_id == ActorId("a1")
        assert result.role == "customer"

    def test_get_actor_state_missing(self) -> None:
        """get_actor_state returns None for unknown actor IDs."""
        reg = ActorRegistry()
        result = reg.get_actor_state(ActorId("nonexistent"))
        assert result is None

    def test_set_actor_state_overwrite(self) -> None:
        """set_actor_state overwrites existing state for the same actor."""
        reg = ActorRegistry()
        state1 = self._make_state("a1", "customer")
        state2 = self._make_state("a1", "vip-customer")
        reg.set_actor_state(ActorId("a1"), state1)
        reg.set_actor_state(ActorId("a1"), state2)
        result = reg.get_actor_state(ActorId("a1"))
        assert result is not None
        assert result.role == "vip-customer"

    def test_list_internal_actors(self) -> None:
        """list_internal_actors returns only internal actor states."""
        reg = ActorRegistry()
        reg.set_actor_state(ActorId("i1"), self._make_state("i1", "manager", "internal"))
        reg.set_actor_state(ActorId("i2"), self._make_state("i2", "reviewer", "internal"))
        reg.set_actor_state(ActorId("e1"), self._make_state("e1", "agent", "external"))

        internal = reg.list_internal_actors()
        assert len(internal) == 2
        ids = {s.actor_id for s in internal}
        assert ActorId("i1") in ids
        assert ActorId("i2") in ids

    def test_list_internal_actors_empty(self) -> None:
        """list_internal_actors returns empty list when no internal actors exist."""
        reg = ActorRegistry()
        reg.set_actor_state(ActorId("e1"), self._make_state("e1", "agent", "external"))
        assert reg.list_internal_actors() == []

    def test_get_actors_watching(self) -> None:
        """get_actors_watching returns actors watching a given entity."""
        reg = ActorRegistry()
        reg.set_actor_state(
            ActorId("a1"),
            self._make_state("a1", "manager", watched=["ticket-001", "ticket-002"]),
        )
        reg.set_actor_state(
            ActorId("a2"),
            self._make_state("a2", "reviewer", watched=["ticket-001"]),
        )
        reg.set_actor_state(
            ActorId("a3"),
            self._make_state("a3", "agent", watched=["ticket-003"]),
        )

        watchers = reg.get_actors_watching(EntityId("ticket-001"))
        assert len(watchers) == 2
        ids = {s.actor_id for s in watchers}
        assert ActorId("a1") in ids
        assert ActorId("a2") in ids

    def test_get_actors_watching_none(self) -> None:
        """get_actors_watching returns empty list when no actor watches the entity."""
        reg = ActorRegistry()
        reg.set_actor_state(
            ActorId("a1"),
            self._make_state("a1", "manager", watched=["ticket-999"]),
        )
        assert reg.get_actors_watching(EntityId("other-entity")) == []

    def test_dump_states(self) -> None:
        """dump_states serializes all actor states to dicts."""
        reg = ActorRegistry()
        reg.set_actor_state(ActorId("a1"), self._make_state("a1", "customer"))
        reg.set_actor_state(ActorId("a2"), self._make_state("a2", "manager"))

        dumped = reg.dump_states()
        assert len(dumped) == 2
        assert all(isinstance(d, dict) for d in dumped)
        ids = {d["actor_id"] for d in dumped}
        assert "a1" in ids
        assert "a2" in ids

    def test_dump_states_empty(self) -> None:
        """dump_states returns empty list when no states are stored."""
        reg = ActorRegistry()
        assert reg.dump_states() == []

    def test_load_states(self) -> None:
        """load_states deserializes and replaces all actor states."""
        reg = ActorRegistry()
        # Pre-existing state that should be cleared
        reg.set_actor_state(ActorId("old"), self._make_state("old", "stale"))

        snapshot_data = [
            {"actor_id": "a1", "role": "customer", "actor_type": "internal"},
            {"actor_id": "a2", "role": "manager", "actor_type": "internal", "frustration": 0.5},
        ]
        reg.load_states(snapshot_data)

        # Old state should be gone
        assert reg.get_actor_state(ActorId("old")) is None
        # New states should be present
        a1 = reg.get_actor_state(ActorId("a1"))
        assert a1 is not None
        assert a1.role == "customer"
        a2 = reg.get_actor_state(ActorId("a2"))
        assert a2 is not None
        assert a2.frustration == 0.5

    def test_dump_load_roundtrip(self) -> None:
        """dump_states -> load_states preserves all data."""
        reg = ActorRegistry()
        state = ActorState(
            actor_id=ActorId("a1"),
            role="support-agent",
            actor_type="internal",
            persona={"name": "Alice"},
            behavior_traits=ActorBehaviorTraits(cooperation_level=0.9),
            current_goal="Resolve ticket",
            frustration=0.2,
            urgency=0.7,
            pending_notifications=["New message"],
            recent_interactions=[
                InteractionRecord(
                    tick=1.0,
                    actor_id="alice",
                    actor_role="support-agent",
                    action="greet",
                    summary="Greeted customer",
                    source="self",
                    event_id="evt-1",
                ),
            ],
            activation_tier=1,
            watched_entities=[EntityId("ticket-100")],
        )
        reg.set_actor_state(ActorId("a1"), state)

        dumped = reg.dump_states()

        reg2 = ActorRegistry()
        reg2.load_states(dumped)

        restored = reg2.get_actor_state(ActorId("a1"))
        assert restored is not None
        assert restored.actor_id == ActorId("a1")
        assert restored.role == "support-agent"
        assert restored.persona == {"name": "Alice"}
        assert restored.behavior_traits.cooperation_level == 0.9
        assert restored.current_goal == "Resolve ticket"
        assert restored.frustration == 0.2
        assert restored.urgency == 0.7
        assert restored.pending_notifications == ["New message"]
        assert len(restored.recent_interactions) == 1
        assert restored.recent_interactions[0].summary == "Greeted customer"
        assert restored.activation_tier == 1
        assert EntityId("ticket-100") in restored.watched_entities

    def test_state_management_independent_of_definitions(self) -> None:
        """Actor state management works independently from actor definition registration."""
        reg = ActorRegistry()
        # Register a definition
        defn = ActorDefinition(id=ActorId("a1"), type=ActorType.HUMAN, role="customer")
        reg.register(defn)

        # Set state for the same actor
        state = self._make_state("a1", "customer")
        reg.set_actor_state(ActorId("a1"), state)

        # Both definition and state are accessible
        assert reg.get(ActorId("a1")).role == "customer"
        assert reg.get_actor_state(ActorId("a1")) is not None

        # State can also exist for actors without definitions
        reg.set_actor_state(ActorId("no-defn"), self._make_state("no-defn", "ghost"))
        assert reg.get_actor_state(ActorId("no-defn")) is not None
