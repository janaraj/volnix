"""Ledger entry type hierarchy.

Defines the base :class:`LedgerEntry` and all concrete entry subtypes
that can be appended to the audit ledger.  Every entry is a frozen
Pydantic model carrying a timestamp and structured metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from terrarium.core.types import (
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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
}


def deserialize_entry(row: dict) -> LedgerEntry:
    """Typed deserialization via entry registry.

    Looks up the entry_type in the row, finds the correct LedgerEntry
    subclass, and deserializes the JSON payload to that type.
    """
    entry_type = row.get("entry_type", "")
    cls = ENTRY_REGISTRY.get(entry_type, LedgerEntry)
    return cls.model_validate_json(row["payload"])
