"""Ledger entry type hierarchy.

Defines the base :class:`LedgerEntry` and all concrete entry subtypes
that can be appended to the audit ledger.  Every entry is a frozen
Pydantic model carrying a timestamp and structured metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from volnix.core.types import (
    ActorId,
    EntityId,
    EnvelopeId,
    EventId,
    RunId,
    SnapshotId,
)

# ---------------------------------------------------------------------------
# Base entry
# ---------------------------------------------------------------------------


class LedgerEntry(BaseModel, frozen=True):
    """Base class for all ledger entries.

    Attributes:
        entry_id: Auto-assigned unique identifier for this entry.
        entry_type: Discriminator string for the entry subtype.
        timestamp: Wall-clock time when the entry was created.
        metadata: Arbitrary additional metadata.
    """

    entry_id: int = 0
    entry_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Concrete entry types
# ---------------------------------------------------------------------------


class PipelineStepEntry(LedgerEntry):
    """Records the execution of a single pipeline step.

    Attributes:
        step_name: Canonical name of the pipeline step.
        request_id: The request being processed.
        actor_id: The actor whose request triggered the step.
        action: The action being evaluated.
        verdict: The step's outcome verdict string.
        duration_ms: Wall-clock milliseconds the step took.
    """

    entry_type: str = "pipeline_step"
    step_name: str
    request_id: str
    actor_id: ActorId
    action: str
    verdict: str
    duration_ms: float = 0.0
    message: str = ""


class StateMutationEntry(LedgerEntry):
    """Records a state mutation applied to an entity.

    Attributes:
        entity_type: The type/kind of the mutated entity.
        entity_id: The unique identifier of the mutated entity.
        operation: One of ``"create"``, ``"update"``, or ``"delete"``.
        before: State snapshot before the mutation.
        after: State snapshot after the mutation.
        event_id: The event that caused this mutation.
    """

    entry_type: str = "state_mutation"
    entity_type: str
    entity_id: EntityId
    operation: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    event_id: EventId | None = None


class LLMCallEntry(LedgerEntry):
    """Records a single call to a language model.

    Attributes:
        provider: LLM provider name (e.g. ``"openai"``, ``"anthropic"``).
        model: Model identifier string.
        prompt_tokens: Number of prompt/input tokens.
        completion_tokens: Number of completion/output tokens.
        cost_usd: Estimated cost in US dollars.
        latency_ms: Round-trip latency in milliseconds.
        success: Whether the call completed successfully.
        engine_name: The engine that initiated the call.
        use_case: Description of what the LLM call was used for.
    """

    entry_type: str = "llm_call"
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    success: bool = True
    engine_name: str = ""
    use_case: str = ""


class GatewayRequestEntry(LedgerEntry):
    """Records an inbound request handled by the gateway.

    Attributes:
        protocol: The protocol used (e.g. ``"mcp"``, ``"http"``).
        actor_id: The actor who made the request.
        action: The action/tool invoked.
        response_status: The response status code or verdict.
        latency_ms: Total request handling latency in milliseconds.
    """

    entry_type: str = "gateway_request"
    protocol: str
    actor_id: ActorId
    action: str
    response_status: str
    latency_ms: float = 0.0


class ValidationEntry(LedgerEntry):
    """Records the outcome of a validation check.

    Attributes:
        validation_type: Category of validation (e.g. ``"schema"``, ``"semantic"``).
        target: What was being validated.
        passed: Whether the validation passed.
        details: Structured details about the validation outcome.
    """

    entry_type: str = "validation"
    validation_type: str
    target: str
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class EngineLifecycleEntry(LedgerEntry):
    """Records an engine lifecycle transition.

    Attributes:
        engine_name: Name of the engine.
        event_type: The lifecycle event (e.g. ``"init"``, ``"start"``,
                    ``"stop"``, ``"error"``).
        details: Additional details about the transition.
    """

    entry_type: str = "engine_lifecycle"
    engine_name: str
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict)


class SnapshotEntry(LedgerEntry):
    """Records the creation of a world-state snapshot.

    Attributes:
        snapshot_id: Unique identifier for the snapshot.
        run_id: The run during which the snapshot was taken.
        tick: Logical clock value at snapshot time.
        entity_count: Number of entities captured.
        size_bytes: Approximate size of the snapshot in bytes.
    """

    entry_type: str = "snapshot"
    snapshot_id: SnapshotId
    run_id: RunId
    tick: int = 0
    entity_count: int = 0
    size_bytes: int = 0


class WorldCompilationEntry(LedgerEntry):
    """Records a world compilation outcome.

    Attributes:
        plan_name: Name of the compiled world plan.
        behavior: Behavior mode (static/reactive/dynamic).
        seed: Reproducibility seed.
        services: List of service names in the world.
        entity_count: Total entities generated.
        entity_types: List of entity type names.
        actor_count: Number of actors generated.
        seeds_processed: Number of seed scenarios applied.
        total_retries: Sum of all retry attempts.
        warnings_count: Number of warnings during compilation.
        snapshot_id: State snapshot ID if created.
        duration_ms: Wall-clock compilation time.
    """

    entry_type: str = "world_compilation"
    plan_name: str = ""
    behavior: str = ""
    seed: int | None = None
    services: list[str] = Field(default_factory=list)
    entity_count: int = 0
    entity_types: list[str] = Field(default_factory=list)
    actor_count: int = 0
    seeds_processed: int = 0
    total_retries: int = 0
    warnings_count: int = 0
    snapshot_id: str = ""
    duration_ms: float = 0.0


class ServiceResolutionEntry(LedgerEntry):
    """Records how a service was resolved during compilation.

    Attributes:
        service_name: The service being resolved.
        resolution_source: How it was resolved (tier1_pack, tier2_yaml_profile, etc.).
        confidence: Confidence score of the resolution.
        operations_count: Number of operations in the resolved surface.
        entities_count: Number of entity types in the resolved surface.
    """

    entry_type: str = "service_resolution"
    service_name: str = ""
    resolution_source: str = ""
    confidence: float = 0.0
    operations_count: int = 0
    entities_count: int = 0


class ProfileInferenceEntry(LedgerEntry):
    """Records when a service profile is bootstrapped via LLM.

    Attributes:
        service_name: The inferred service.
        sources_used: Which sources contributed (context_hub, openapi, etc.).
        confidence: Confidence score based on sources.
        operations_count: Operations in the generated profile.
        entities_count: Entity types in the generated profile.
        fidelity_source: Always "bootstrapped" for inferred profiles.
    """

    entry_type: str = "profile_inference"
    service_name: str = ""
    sources_used: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    operations_count: int = 0
    entities_count: int = 0
    fidelity_source: str = "bootstrapped"


class FeedbackAnnotationEntry(LedgerEntry):
    """Records a service annotation added via the feedback engine.

    Attributes:
        service_id: The annotated service.
        annotation_text: The annotation content.
        author: Who added the annotation.
    """

    entry_type: str = "feedback.annotation"
    service_id: str = ""
    annotation_text: str = ""
    author: str = ""


class FeedbackPromotionEntry(LedgerEntry):
    """Records a fidelity tier promotion.

    Attributes:
        service_name: The promoted service.
        previous_fidelity: The old fidelity source.
        new_fidelity: The new fidelity source.
        profile_version: The new profile version string.
    """

    entry_type: str = "feedback.promotion"
    service_name: str = ""
    previous_fidelity: str = ""
    new_fidelity: str = ""
    profile_version: str = ""


class FeedbackCaptureEntry(LedgerEntry):
    """Records a service surface capture from a run.

    Attributes:
        service_name: The captured service.
        run_id: The run captured from.
        operations_count: Number of operations observed.
    """

    entry_type: str = "feedback.capture"
    service_name: str = ""
    run_id: str = ""
    operations_count: int = 0


class FeedbackSyncEntry(LedgerEntry):
    """Records an external sync drift check."""

    entry_type: str = "feedback.sync"
    service_name: str = ""
    source: str = ""
    has_drift: bool = False
    operations_added: int = 0
    operations_removed: int = 0


class FeedbackSyncUpdateEntry(LedgerEntry):
    """Records an applied sync update to a profile."""

    entry_type: str = "feedback.sync_update"
    service_name: str = ""
    changes_applied: int = 0
    new_version: str = ""


class ActorActivationEntry(LedgerEntry):
    """Records the activation of an internal actor.

    Attributes:
        actor_id: The actor that was activated.
        activation_reason: Why the actor was activated.
        activation_tier: The activation tier (e.g. ``"reactive"``, ``"proactive"``).
        trigger_event_id: The event that triggered the activation, if any.
    """

    entry_type: str = "actor_activation"
    actor_id: ActorId
    activation_reason: str
    activation_tier: int = 0
    trigger_event_id: EventId | None = None


class ActionGenerationEntry(LedgerEntry):
    """Records the generation of an action by an internal actor.

    Attributes:
        actor_id: The actor that generated the action.
        envelope_id: The ActionEnvelope ID for the generated action.
        action_type: The type of action generated.
        tier: The fidelity tier used for generation.
        llm_prompt_hash: Hash of the LLM prompt used, for reproducibility.
        llm_latency_ms: LLM call latency in milliseconds.
    """

    entry_type: str = "action_generation"
    actor_id: ActorId
    envelope_id: EnvelopeId
    action_type: str
    tier: int = 0
    llm_prompt_hash: str = ""
    llm_latency_ms: float = 0.0


class SubscriptionMatchEntry(LedgerEntry):
    """Records when a subscription matched a committed event.

    Attributes:
        actor_id: The actor whose subscription matched.
        event_id: The event that matched the subscription.
        service_id: The service the subscription is for.
        sensitivity: The subscription sensitivity level.
        activated: Whether the actor was activated as a result.
        reason: How the match was resolved (e.g. "tagged", "open_mode", "passive").
    """

    entry_type: str = "subscription_match"
    actor_id: ActorId
    event_id: EventId
    service_id: str
    sensitivity: str
    activated: bool
    reason: str = ""


class CollaborationNotificationEntry(LedgerEntry):
    """Records a collaboration notification delivery.

    Attributes:
        recipient_actor_id: The actor who received the notification.
        source_actor_id: The actor who produced the event.
        event_id: The event that triggered the notification.
        channel: Communication channel (e.g. "#research").
        intended_for: Tagged recipient roles.
        sensitivity: The subscription sensitivity level.
    """

    entry_type: str = "collaboration_notification"
    recipient_actor_id: ActorId
    source_actor_id: ActorId
    event_id: EventId
    channel: str | None = None
    intended_for: list[str] = Field(default_factory=list)
    sensitivity: str = "immediate"


class ToolLoopStepEntry(LedgerEntry):
    """Records one tool call step within a multi-turn activation."""

    entry_type: str = "tool_loop_step"
    actor_id: ActorId
    activation_id: str
    step_index: int
    tool_name: str
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    event_id: EventId | None = None
    blocked: bool = False
    llm_latency_ms: float = 0.0
    response_preview: str = ""  # First 200 chars of LLM response (tool result or text)


class ActivationCompleteEntry(LedgerEntry):
    """Records completion of a multi-turn agent activation."""

    entry_type: str = "activation_complete"
    actor_id: ActorId
    activation_id: str
    activation_reason: str
    total_tool_calls: int
    total_envelopes: int
    terminated_by: str  # "text_response" | "do_nothing" | "max_tool_calls" | "error"
    final_text: str = ""
    # PMF Plan Phase 4A — prompt-cache observability. Provider
    # response ``usage`` reports cache-read vs cache-write tokens;
    # we capture them here so cohort size + rotation interval can
    # be tuned empirically. Absent metadata → both stay ``None``.
    cache_hit_tokens: int | None = None
    cache_write_tokens: int | None = None


class CohortRotationEntry(LedgerEntry):
    """Records one ``CohortManager.rotate()`` cycle (Phase 4A).

    Written by ``AgencyEngine`` immediately after each rotation.
    The paired :class:`volnix.core.events.CohortRotationEvent` is
    published on the bus at the same moment — the ledger entry is for
    audit; the bus event drives the activation-queue drain.
    """

    entry_type: str = "cohort_rotation"
    tick: int
    rotation_policy: str
    demoted_count: int
    promoted_count: int
    active_count: int
    registered_count: int
    queue_total_depth: int


class CohortDecisionEntry(LedgerEntry):
    """Records a single cohort-gate decision on an Active NPC (Phase 4A).

    Review fix M4: earlier drafts silently dropped observability for
    every policy branch other than rotation (queue overflow, promote
    budget exhausted, record_only). DESIGN_PRINCIPLES: "if it did not
    produce a ledger entry, it did not happen." These entries give
    runners the data to explain why an NPC didn't activate on a
    matching event.

    ``decision`` values:
      * ``"defer"`` — dormant NPC, event queued.
      * ``"promote"`` — dormant NPC, preempt-promoted + activated.
      * ``"promote_budget_exhausted"`` — wanted to promote, fell back to defer.
      * ``"record_only"`` — dormant NPC, just noted the event.
      * ``"queue_overflow"`` — queue was full; oldest event dropped.
    """

    entry_type: str = "cohort_decision"
    actor_id: ActorId
    decision: str
    event_type: str
    queue_depth_after: int = 0
    evicted_actor_id: ActorId | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Entry registry for typed deserialization
# ---------------------------------------------------------------------------

ENTRY_REGISTRY: dict[str, type[LedgerEntry]] = {
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
    "tool_loop_step": ToolLoopStepEntry,
    "activation_complete": ActivationCompleteEntry,
    "cohort_rotation": CohortRotationEntry,
    "cohort_decision": CohortDecisionEntry,
}


def deserialize_entry(row: dict) -> LedgerEntry:
    """Typed deserialization via entry registry.

    Looks up the entry_type in the row, finds the correct LedgerEntry
    subclass, and deserializes the JSON payload to that type.
    """
    entry_type = row.get("entry_type", "")
    cls = ENTRY_REGISTRY.get(entry_type, LedgerEntry)
    return cls.model_validate_json(row["payload"])
