"""Tests for terrarium.core.envelope -- ActionEnvelope and related types."""

import pytest

from terrarium.core.envelope import ActionEnvelope, _generate_envelope_id
from terrarium.core.types import (
    ActionSource,
    ActorId,
    EnvelopeId,
    EnvelopePriority,
    EventId,
    ServiceId,
)


class TestActionSource:
    """Verify ActionSource enum values."""

    def test_action_source_values(self):
        assert ActionSource.EXTERNAL == "external"
        assert ActionSource.INTERNAL == "internal"
        assert ActionSource.ENVIRONMENT == "environment"

    def test_action_source_member_count(self):
        assert len(ActionSource) == 3


class TestEnvelopePriority:
    """Verify EnvelopePriority ordering."""

    def test_envelope_priority_ordering(self):
        assert EnvelopePriority.ENVIRONMENT < EnvelopePriority.EXTERNAL
        assert EnvelopePriority.EXTERNAL < EnvelopePriority.INTERNAL

    def test_envelope_priority_numeric_values(self):
        assert EnvelopePriority.SYSTEM == 0
        assert EnvelopePriority.ENVIRONMENT == 1
        assert EnvelopePriority.EXTERNAL == 2
        assert EnvelopePriority.INTERNAL == 3

    def test_priority_sortable(self):
        priorities = [
            EnvelopePriority.INTERNAL,
            EnvelopePriority.ENVIRONMENT,
            EnvelopePriority.EXTERNAL,
        ]
        sorted_priorities = sorted(priorities)
        assert sorted_priorities == [
            EnvelopePriority.ENVIRONMENT,
            EnvelopePriority.EXTERNAL,
            EnvelopePriority.INTERNAL,
        ]


class TestEnvelopeId:
    """Verify EnvelopeId generation."""

    def test_envelope_id_unique(self):
        id1 = _generate_envelope_id()
        id2 = _generate_envelope_id()
        assert id1 != id2

    def test_envelope_id_prefix(self):
        eid = _generate_envelope_id()
        assert eid.startswith("env-")

    def test_envelope_id_is_str(self):
        eid = EnvelopeId("env-abc123")
        assert isinstance(eid, str)


class TestActionEnvelope:
    """Verify ActionEnvelope creation, defaults, and immutability."""

    def test_envelope_creation(self):
        env = ActionEnvelope(
            actor_id=ActorId("actor-1"),
            source=ActionSource.EXTERNAL,
            action_type="send_message",
        )
        assert env.actor_id == ActorId("actor-1")
        assert env.source == ActionSource.EXTERNAL
        assert env.action_type == "send_message"
        assert env.target_service is None
        assert env.payload == {}
        assert env.logical_time == 0.0
        assert env.priority == EnvelopePriority.INTERNAL
        assert env.parent_event_ids == []
        assert env.metadata == {}

    def test_envelope_id_auto_generated(self):
        env = ActionEnvelope(
            actor_id=ActorId("actor-1"),
            source=ActionSource.INTERNAL,
            action_type="read_data",
        )
        assert env.envelope_id.startswith("env-")

    def test_envelope_id_unique(self):
        env1 = ActionEnvelope(
            actor_id=ActorId("actor-1"),
            source=ActionSource.INTERNAL,
            action_type="read_data",
        )
        env2 = ActionEnvelope(
            actor_id=ActorId("actor-1"),
            source=ActionSource.INTERNAL,
            action_type="read_data",
        )
        assert env1.envelope_id != env2.envelope_id

    def test_envelope_frozen(self):
        env = ActionEnvelope(
            actor_id=ActorId("actor-1"),
            source=ActionSource.EXTERNAL,
            action_type="send_message",
        )
        with pytest.raises(Exception):
            env.action_type = "other_action"

    def test_envelope_with_all_fields(self):
        env = ActionEnvelope(
            envelope_id=EnvelopeId("env-custom123"),
            actor_id=ActorId("actor-2"),
            source=ActionSource.ENVIRONMENT,
            action_type="status_change",
            target_service=ServiceId("slack"),
            payload={"channel": "#general", "text": "hello"},
            logical_time=42.5,
            priority=EnvelopePriority.ENVIRONMENT,
            parent_event_ids=[EventId("evt-1"), EventId("evt-2")],
            metadata={"retry": True},
        )
        assert env.envelope_id == EnvelopeId("env-custom123")
        assert env.target_service == ServiceId("slack")
        assert env.payload == {"channel": "#general", "text": "hello"}
        assert env.logical_time == 42.5
        assert env.priority == EnvelopePriority.ENVIRONMENT
        assert len(env.parent_event_ids) == 2
        assert env.metadata == {"retry": True}

    def test_envelope_with_parent_events(self):
        parent_ids = [EventId("evt-a"), EventId("evt-b"), EventId("evt-c")]
        env = ActionEnvelope(
            actor_id=ActorId("actor-1"),
            source=ActionSource.INTERNAL,
            action_type="respond",
            parent_event_ids=parent_ids,
        )
        assert env.parent_event_ids == parent_ids
        assert len(env.parent_event_ids) == 3

    def test_envelope_serialization_roundtrip(self):
        env = ActionEnvelope(
            actor_id=ActorId("actor-1"),
            source=ActionSource.EXTERNAL,
            action_type="create_ticket",
            target_service=ServiceId("jira"),
            payload={"title": "Bug report"},
        )
        json_str = env.model_dump_json()
        restored = ActionEnvelope.model_validate_json(json_str)
        assert restored == env
        assert restored.source == ActionSource.EXTERNAL
        assert restored.payload == {"title": "Bug report"}
