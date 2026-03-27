"""Tests for terrarium.ledger.entries -- typed ledger entry dataclasses."""
from datetime import datetime

import pytest

from terrarium.core.types import ActorId, EntityId, EnvelopeId, EventId, RunId, SnapshotId
from terrarium.ledger.entries import (
    ENTRY_REGISTRY,
    ActionGenerationEntry,
    ActorActivationEntry,
    EngineLifecycleEntry,
    GatewayRequestEntry,
    LedgerEntry,
    LLMCallEntry,
    PipelineStepEntry,
    SnapshotEntry,
    StateMutationEntry,
    ValidationEntry,
    deserialize_entry,
)


def test_ledger_entry_base():
    """LedgerEntry base class should set defaults for entry_id, timestamp, metadata."""
    entry = LedgerEntry(entry_type="test")
    assert entry.entry_id == 0
    assert entry.entry_type == "test"
    assert isinstance(entry.timestamp, datetime)
    assert entry.metadata == {}


def test_pipeline_step_entry():
    """PipelineStepEntry should have entry_type default 'pipeline_step'."""
    entry = PipelineStepEntry(
        step_name="auth_check",
        request_id="req-1",
        actor_id=ActorId("actor-1"),
        action="read",
        verdict="allow",
    )
    assert entry.entry_type == "pipeline_step"
    assert entry.step_name == "auth_check"
    assert entry.request_id == "req-1"
    assert entry.actor_id == ActorId("actor-1")
    assert entry.action == "read"
    assert entry.verdict == "allow"
    assert entry.duration_ms == 0.0


def test_state_mutation_entry():
    """StateMutationEntry should have entry_type default 'state_mutation'."""
    entry = StateMutationEntry(
        entity_type="user",
        entity_id=EntityId("ent-1"),
        operation="create",
        after={"name": "Alice"},
    )
    assert entry.entry_type == "state_mutation"
    assert entry.entity_type == "user"
    assert entry.entity_id == EntityId("ent-1")
    assert entry.operation == "create"
    assert entry.before is None
    assert entry.after == {"name": "Alice"}
    assert entry.event_id is None


def test_llm_call_entry():
    """LLMCallEntry should have entry_type default 'llm_call'."""
    entry = LLMCallEntry(
        provider="openai",
        model="gpt-4",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        latency_ms=250.0,
        engine_name="reasoning",
    )
    assert entry.entry_type == "llm_call"
    assert entry.provider == "openai"
    assert entry.model == "gpt-4"
    assert entry.prompt_tokens == 100
    assert entry.completion_tokens == 50
    assert entry.success is True
    assert entry.engine_name == "reasoning"


def test_gateway_request_entry():
    """GatewayRequestEntry should have entry_type default 'gateway_request'."""
    entry = GatewayRequestEntry(
        protocol="mcp",
        actor_id=ActorId("actor-2"),
        action="tool_call",
        response_status="200",
    )
    assert entry.entry_type == "gateway_request"
    assert entry.protocol == "mcp"
    assert entry.actor_id == ActorId("actor-2")
    assert entry.action == "tool_call"
    assert entry.response_status == "200"
    assert entry.latency_ms == 0.0


def test_validation_entry():
    """ValidationEntry should have entry_type default 'validation'."""
    entry = ValidationEntry(
        validation_type="schema",
        target="request_body",
        passed=True,
        details={"schema_version": "1.0"},
    )
    assert entry.entry_type == "validation"
    assert entry.validation_type == "schema"
    assert entry.target == "request_body"
    assert entry.passed is True
    assert entry.details == {"schema_version": "1.0"}


def test_engine_lifecycle_entry():
    """EngineLifecycleEntry should have entry_type default 'engine_lifecycle'."""
    entry = EngineLifecycleEntry(
        engine_name="reasoning",
        event_type="start",
        details={"version": "2.0"},
    )
    assert entry.entry_type == "engine_lifecycle"
    assert entry.engine_name == "reasoning"
    assert entry.event_type == "start"
    assert entry.details == {"version": "2.0"}


def test_snapshot_entry():
    """SnapshotEntry should have entry_type default 'snapshot'."""
    entry = SnapshotEntry(
        snapshot_id=SnapshotId("snap-1"),
        run_id=RunId("run-1"),
        tick=42,
        entity_count=10,
        size_bytes=2048,
    )
    assert entry.entry_type == "snapshot"
    assert entry.snapshot_id == SnapshotId("snap-1")
    assert entry.run_id == RunId("run-1")
    assert entry.tick == 42
    assert entry.entity_count == 10
    assert entry.size_bytes == 2048


def test_entry_serialization_roundtrip():
    """Entries should survive a model_dump_json -> model_validate_json roundtrip."""
    entry = PipelineStepEntry(
        step_name="policy_eval",
        request_id="req-99",
        actor_id=ActorId("actor-x"),
        action="write",
        verdict="deny",
        duration_ms=12.5,
    )
    json_str = entry.model_dump_json()
    restored = PipelineStepEntry.model_validate_json(json_str)
    assert restored == entry
    assert restored.entry_type == "pipeline_step"
    assert restored.step_name == "policy_eval"


def test_entry_registry_all_types():
    """ENTRY_REGISTRY should contain all concrete entry types."""
    from terrarium.ledger.entries import (
        FeedbackAnnotationEntry,
        FeedbackCaptureEntry,
        FeedbackPromotionEntry,
        FeedbackSyncEntry,
        FeedbackSyncUpdateEntry,
        WorldCompilationEntry,
        ServiceResolutionEntry,
        ProfileInferenceEntry,
        SubscriptionMatchEntry,
        CollaborationNotificationEntry,
    )

    expected = {
        "pipeline_step": PipelineStepEntry,
        "state_mutation": StateMutationEntry,
        "llm_call": LLMCallEntry,
        "gateway_request": GatewayRequestEntry,
        "validation": ValidationEntry,
        "engine_lifecycle": EngineLifecycleEntry,
        "snapshot": SnapshotEntry,
        "actor_activation": ActorActivationEntry,
        "action_generation": ActionGenerationEntry,
        "feedback.annotation": FeedbackAnnotationEntry,
        "feedback.promotion": FeedbackPromotionEntry,
        "feedback.capture": FeedbackCaptureEntry,
        "feedback.sync": FeedbackSyncEntry,
        "feedback.sync_update": FeedbackSyncUpdateEntry,
        "world_compilation": WorldCompilationEntry,
        "service_resolution": ServiceResolutionEntry,
        "profile_inference": ProfileInferenceEntry,
        "subscription_match": SubscriptionMatchEntry,
        "collaboration_notification": CollaborationNotificationEntry,
    }
    assert ENTRY_REGISTRY == expected


def test_deserialize_entry_typed():
    """deserialize_entry should return the correct subclass, not base LedgerEntry."""
    entry = LLMCallEntry(
        provider="anthropic",
        model="claude-3",
        prompt_tokens=200,
        completion_tokens=100,
    )
    row = {"entry_type": "llm_call", "payload": entry.model_dump_json()}
    restored = deserialize_entry(row)
    assert isinstance(restored, LLMCallEntry)
    assert restored.provider == "anthropic"
    assert restored.model == "claude-3"


def test_deserialize_entry_unknown_type():
    """deserialize_entry should fall back to LedgerEntry for unknown types."""
    entry = LedgerEntry(entry_type="unknown_type")
    row = {"entry_type": "unknown_type", "payload": entry.model_dump_json()}
    restored = deserialize_entry(row)
    assert isinstance(restored, LedgerEntry)
    assert restored.entry_type == "unknown_type"


def test_actor_activation_entry():
    """ActorActivationEntry should have entry_type default 'actor_activation'."""
    entry = ActorActivationEntry(
        actor_id=ActorId("actor-internal-1"),
        activation_reason="incoming_message",
        activation_tier=2,
        trigger_event_id=EventId("evt-42"),
    )
    assert entry.entry_type == "actor_activation"
    assert entry.actor_id == ActorId("actor-internal-1")
    assert entry.activation_reason == "incoming_message"
    assert entry.activation_tier == 2
    assert entry.trigger_event_id == EventId("evt-42")


def test_actor_activation_entry_no_trigger():
    """ActorActivationEntry should allow None trigger_event_id."""
    entry = ActorActivationEntry(
        actor_id=ActorId("actor-2"),
        activation_reason="scheduled",
        activation_tier=3,
    )
    assert entry.trigger_event_id is None


def test_action_generation_entry():
    """ActionGenerationEntry should have entry_type default 'action_generation'."""
    entry = ActionGenerationEntry(
        actor_id=ActorId("actor-internal-1"),
        envelope_id=EnvelopeId("env-abc123"),
        action_type="send_message",
        tier=2,
        llm_prompt_hash="sha256:abc123",
        llm_latency_ms=150.5,
    )
    assert entry.entry_type == "action_generation"
    assert entry.actor_id == ActorId("actor-internal-1")
    assert entry.envelope_id == EnvelopeId("env-abc123")
    assert entry.action_type == "send_message"
    assert entry.tier == 2
    assert entry.llm_prompt_hash == "sha256:abc123"
    assert entry.llm_latency_ms == 150.5


def test_action_generation_entry_defaults():
    """ActionGenerationEntry should have sensible defaults."""
    entry = ActionGenerationEntry(
        actor_id=ActorId("actor-1"),
        envelope_id=EnvelopeId("env-def456"),
        action_type="read_data",
        tier=1,
    )
    assert entry.llm_prompt_hash == ""
    assert entry.llm_latency_ms == 0.0
