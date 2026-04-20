"""Ledger entry type hierarchy.

Defines the base :class:`LedgerEntry` and all concrete entry subtypes
that can be appended to the audit ledger.  Every entry is a frozen
Pydantic model carrying a timestamp and structured metadata.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from volnix.core.memory_types import MemoryScope
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
        schema_version: Monotonically-increasing schema version of this
            entry type (PMF Plan Phase 4C Step 3). Baseline for every
            current entry type is ``1``. When a subclass bumps its
            shape incompatibly, it MUST (a) bump ``LATEST_SCHEMA_VERSION``
            on that subclass, and (b) accept either the old or the new
            shape in its own validator. A reader that sees
            ``schema_version > LATEST_SCHEMA_VERSION`` will wrap the
            row in ``UnknownLedgerEntry`` rather than silently dropping
            fields — see ``deserialize_entry``.
        timestamp: Wall-clock time when the entry was created.
        metadata: Arbitrary additional metadata.

    Class attributes:
        LATEST_SCHEMA_VERSION: Highest ``schema_version`` this reader
            knows how to parse for this subclass. Override on a
            subclass when you bump its shape; leave at 1 otherwise.
    """

    LATEST_SCHEMA_VERSION: ClassVar[int] = 1

    entry_id: int = 0
    entry_type: str
    schema_version: int = Field(default=1, ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


#: Reserved discriminator used by ``UnknownLedgerEntry`` as its own
#: ``entry_type``. New entry types MUST NOT register under this name —
#: ``deserialize_entry`` uses it to route wrapper-passthrough on
#: re-read, so a collision would create a wrapping loop.
_UNKNOWN_ENTRY_TYPE_SENTINEL = "unknown"


class UnknownLedgerEntry(LedgerEntry):
    """Forward-compat wrapper for a ledger entry whose ``entry_type``
    is not registered in ``ENTRY_REGISTRY`` OR whose ``schema_version``
    exceeds the reader's ``LATEST_SCHEMA_VERSION`` (PMF Plan Phase 4C
    Step 3).

    Older Volnix readers may encounter ledger rows produced by newer
    writers (after an engine upgrade, or when a consumer embeds a
    newer Volnix against an older data file). Pre-4C behaviour
    silently degraded unknown rows to a bare ``LedgerEntry``, dropping
    every subclass-specific field. This wrapper preserves the
    original ``entry_type`` discriminator AND the entire parsed JSON
    payload so consumers can introspect unknown rows without data loss.

    Attributes:
        entry_type: Always the sentinel ``"unknown"`` (reserved — see
            ``_UNKNOWN_ENTRY_TYPE_SENTINEL``). The ORIGINAL discriminator
            is preserved in ``raw_entry_type`` so a consumer can branch
            on it.
        raw_entry_type: The discriminator string emitted by the
            newer writer (e.g. ``"session.started"`` against a reader
            that hasn't been taught that type yet).
        raw_payload: Full parsed JSON payload of the row. All
            unknown fields land here intact for forensic/audit use.
    """

    entry_type: str = _UNKNOWN_ENTRY_TYPE_SENTINEL
    raw_entry_type: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)


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
# Memory Engine entries (Phase 4B — PMF Plan)
# ---------------------------------------------------------------------------


class MemoryWriteEntry(LedgerEntry):
    """Records a single :meth:`MemoryEngineProtocol.remember` call.

    Written on every successful write — explicit (``remember`` tool),
    implicit (post-activation distiller), or ``consolidated``
    (periodic consolidation).

    Typed-ID discipline (C3, C4): ``caller_actor_id`` is always an
    ``ActorId``; ``target_scope`` is the ``MemoryScope`` Literal;
    ``target_owner`` stays ``str`` because it is polymorphic
    (``ActorId`` for actor scope, ``TeamId`` for team scope).
    """

    entry_type: str = "memory_write"
    caller_actor_id: ActorId
    target_scope: MemoryScope
    target_owner: str
    record_id: str
    kind: str
    source: str
    importance: float = Field(ge=0.0, le=1.0)
    tick: int = Field(ge=0)


class MemoryRecallEntry(LedgerEntry):
    """Records a single :meth:`MemoryEngineProtocol.recall` call.

    Captures the query mode and result count so replay + cost audits
    can reason about memory-read pressure per actor.
    """

    entry_type: str = "memory_recall"
    caller_actor_id: ActorId
    target_scope: MemoryScope
    target_owner: str
    query_mode: str
    query_id: str
    result_count: int = Field(ge=0)
    tick: int = Field(ge=0)


class MemoryConsolidationEntry(LedgerEntry):
    """Records one episodic → semantic consolidation pass."""

    entry_type: str = "memory_consolidation"
    actor_id: ActorId
    episodic_consumed: int = Field(ge=0)
    semantic_produced: int = Field(ge=0)
    episodic_pruned: int = Field(ge=0)
    tick: int = Field(ge=0)


class MemoryEvictionEntry(LedgerEntry):
    """Records a flush-on-demote of one actor's memory buffer."""

    entry_type: str = "memory_eviction"
    actor_id: ActorId


class MemoryHydrationEntry(LedgerEntry):
    """Records a warm-on-promote of one actor's memory cache."""

    entry_type: str = "memory_hydration"
    actor_id: ActorId


class MemoryAccessDeniedEntry(LedgerEntry):
    """Records a blocked cross-scope access attempt.

    DESIGN_PRINCIPLES: "if it did not produce a ledger entry, it did
    not happen." Denied accesses are first-class audit events, not
    silently swallowed.
    """

    entry_type: str = "memory_access_denied"
    caller_actor_id: ActorId
    target_scope: MemoryScope
    target_owner: str
    op: str


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
    "memory_write": MemoryWriteEntry,
    "memory_recall": MemoryRecallEntry,
    "memory_consolidation": MemoryConsolidationEntry,
    "memory_eviction": MemoryEvictionEntry,
    "memory_hydration": MemoryHydrationEntry,
    "memory_access_denied": MemoryAccessDeniedEntry,
}


def deserialize_entry(row: dict) -> LedgerEntry:
    """Typed deserialization via entry registry.

    PMF Plan Phase 4C Step 3 — contract:

    - **Known type, known schema_version**: parse as the concrete
      subclass via ``cls.model_validate(payload)``.
    - **Known type, newer schema_version** (``schema_version >
      cls.LATEST_SCHEMA_VERSION``): wrap in ``UnknownLedgerEntry``
      preserving the original ``entry_type`` in ``raw_entry_type``.
      This honours the docstring promise that elevated
      schema_versions wrap rather than silently drop fields.
    - **Unknown type**: wrap in ``UnknownLedgerEntry``.
    - **Wrapper-passthrough**: when reading back a previously-stored
      ``UnknownLedgerEntry`` (row ``entry_type`` is the reserved
      sentinel and the payload carries ``raw_entry_type`` +
      ``raw_payload``), re-route with the original discriminator
      before registry lookup. Avoids the ``raw_payload`` nesting loop
      identified in review M1; also means a reader upgraded to know
      the original type recovers the concrete class on the next read.

    Error handling:

    - Missing ``payload`` key → ``ValueError`` naming the row shape.
    - Malformed JSON in payload → ``ValueError`` with the underlying
      decoder message and the row's ``entry_type``. Both replace the
      pre-fix ``KeyError`` / ``json.JSONDecodeError`` bubbles that
      aborted an entire ``Ledger.query()`` on one corrupt row.
    """
    entry_type = row.get("entry_type", "")
    payload_raw = row.get("payload")
    if payload_raw is None:
        raise ValueError(
            f"deserialize_entry: row missing 'payload' key (entry_type={entry_type!r})"
        )
    try:
        payload: Any = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"deserialize_entry: malformed JSON payload for entry_type={entry_type!r}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"deserialize_entry: payload must decode to a dict, "
            f"got {type(payload).__name__} for entry_type={entry_type!r}"
        )

    # Wrapper-passthrough: unnest a previously-wrapped row so the next
    # read sees the original discriminator again (review M1 fix).
    # Requires BOTH raw_entry_type AND raw_payload — a partial/corrupt
    # wrapper falls through to the else branch (audit L1: surfaces as
    # an ``UnknownLedgerEntry`` with ``raw_entry_type="unknown"`` so a
    # consumer inspecting ``raw_entry_type`` can distinguish corruption
    # from a legitimately-unknown type).
    if (
        entry_type == _UNKNOWN_ENTRY_TYPE_SENTINEL
        and "raw_entry_type" in payload
        and "raw_payload" in payload
    ):
        entry_type = payload["raw_entry_type"]
        payload = payload["raw_payload"]
        if not isinstance(payload, dict):
            payload = {}

    cls = ENTRY_REGISTRY.get(entry_type)
    schema_version = payload.get("schema_version", 1)
    if cls is not None and schema_version <= cls.LATEST_SCHEMA_VERSION:
        return cls.model_validate(payload)

    # Unknown type OR schema_version exceeds what we know → wrap.
    # Lift only the base fields that are actually present; missing
    # fields fall through to the base-class defaults rather than
    # getting a misleading fresh ``datetime.now()`` fallback
    # (review L2 fix).
    base_kwargs = {
        k: payload[k]
        for k in ("entry_id", "schema_version", "timestamp", "metadata")
        if k in payload
    }
    return UnknownLedgerEntry(
        raw_entry_type=entry_type,
        raw_payload=payload,
        **base_kwargs,
    )
