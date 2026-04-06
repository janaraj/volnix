"""Event type hierarchy for the Volnix event ledger.

Every meaningful occurrence in Volnix is recorded as an immutable Event.
This module defines the complete taxonomy of events as frozen Pydantic models,
organised into logical families:

* **WorldEvent** -- actions taken against simulated services.
* **Policy events** -- governance decisions (block, hold, escalate, flag).
* **Budget events** -- resource consumption tracking.
* **Capability / Animator / Annotation** -- auxiliary event families.
* **Lifecycle events** -- engine and simulation status transitions.

All event classes are frozen (immutable) and carry a globally unique
``event_id`` produced by :func:`_generate_event_id`.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from volnix.core.types import (
    ActionSource,
    ActorId,
    EntityId,
    EventId,
    FidelityMetadata,
    FidelityTier,
    PolicyId,
    ServiceId,
    Timestamp,
    ToolName,
    WorldId,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_event_id() -> EventId:
    """Generate a globally unique event identifier.

    Returns:
        A new :class:`EventId` backed by a UUID-4 string.
    """
    return EventId(str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------


class Event(BaseModel, frozen=True):
    """Root of the event hierarchy.

    Every event carries a unique id, a discriminating ``event_type`` string,
    a compound timestamp, an optional causal parent, and free-form metadata.

    Attributes:
        event_id: Globally unique event identifier.
        event_type: Discriminator string (typically the class name).
        timestamp: When the event occurred (world + wall time).
        caused_by: Optional parent event that triggered this one.
        metadata: Arbitrary metadata bag.
    """

    event_id: EventId = Field(default_factory=_generate_event_id)
    event_type: str
    timestamp: Timestamp
    caused_by: EventId | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# World events
# ---------------------------------------------------------------------------


class WorldEvent(Event):
    """An action performed by an actor against a simulated service.

    Attributes:
        actor_id: The actor who initiated the action.
        service_id: The target service.
        action: The action/tool name invoked.
        target_entity: Optional entity the action is directed at.
        input_data: Raw input payload.
        pre_state: State snapshot before the action (if captured).
        post_state: State snapshot after the action (if captured).
        fidelity: Fidelity metadata for this action's simulation.
        causes: List of upstream event IDs that causally led to this event.
        source: Origin of this action (external agent, internal, environment).
        response_body: The service response payload returned to the caller.
        outcome: Pipeline verdict — ``success``, ``blocked``, ``held``,
            ``escalated``, ``denied``, ``budget_exhausted``, ``error``,
            or ``policy_hit``.
        state_deltas: Entity mutations applied by this action. Each dict
            contains ``entity_type``, ``entity_id``, ``operation``,
            ``fields``, and ``previous_fields``.
        cost: Action cost breakdown (api_calls, llm_spend_usd, world_actions).
        run_id: The evaluation run this event belongs to.
    """

    actor_id: ActorId
    service_id: ServiceId
    action: str
    target_entity: EntityId | None = None
    input_data: dict[str, Any] = Field(default_factory=dict)
    pre_state: dict[str, Any] | None = None
    post_state: dict[str, Any] | None = None
    fidelity: FidelityMetadata | None = None
    causes: list[EventId] = Field(default_factory=list)
    source: ActionSource | None = None
    response_body: dict[str, Any] | None = None
    outcome: str = "success"
    state_deltas: list[dict[str, Any]] = Field(default_factory=list)
    cost: dict[str, Any] | None = None
    run_id: str | None = None


# ---------------------------------------------------------------------------
# Permission events
# ---------------------------------------------------------------------------


class PermissionDeniedEvent(Event):
    """Emitted when an actor is denied permission for an action.

    Attributes:
        actor_id: The actor whose request was denied.
        action: The action that was requested.
        reason: Human-readable explanation for the denial.
        target_entity: Optional entity the action targeted.
    """

    actor_id: ActorId
    action: str
    reason: str
    target_entity: EntityId | None = None


# ---------------------------------------------------------------------------
# Policy events
# ---------------------------------------------------------------------------


class PolicyEvent(Event):
    """Base for all governance-policy events.

    Attributes:
        policy_id: The policy that produced this event.
        actor_id: The actor whose action triggered policy evaluation.
        action: The action under evaluation.
        run_id: The evaluation run this event belongs to.
    """

    policy_id: PolicyId
    actor_id: ActorId
    action: str
    run_id: str | None = None


class PolicyBlockEvent(PolicyEvent):
    """A policy blocked an action outright.

    Attributes:
        reason: Why the policy blocked the action.
    """

    reason: str


class PolicyHoldEvent(PolicyEvent):
    """A policy placed an action on hold pending approval.

    Attributes:
        approver_role: The role that must approve the held action.
        timeout_seconds: How long the hold remains valid before auto-expiry.
        hold_id: Unique identifier for this hold instance.
    """

    approver_role: str
    timeout_seconds: float
    hold_id: str


class PolicyEscalateEvent(PolicyEvent):
    """A policy escalated an action to a higher authority.

    Attributes:
        target_role: The role the action is escalated to.
        original_actor: The actor who originally initiated the action.
    """

    target_role: str
    original_actor: ActorId


class PolicyFlagEvent(PolicyEvent):
    """A policy flagged an action for logging only (no enforcement)."""

    pass


class ApprovalEvent(Event):
    """Records the resolution of a held action.

    Attributes:
        hold_id: The hold that is being resolved.
        approved: Whether the action was approved.
        approver: Identity of the approver.
        reason: Optional explanation for the decision.
    """

    hold_id: str
    approved: bool
    approver: ActorId
    reason: str | None = None


# ---------------------------------------------------------------------------
# Budget events
# ---------------------------------------------------------------------------


class BudgetEvent(Event):
    """Base for budget-related events.

    Attributes:
        actor_id: The actor whose budget is affected.
        budget_type: The budget dimension (e.g. ``"api_calls"``, ``"llm_spend"``).
    """

    actor_id: ActorId
    budget_type: str


class BudgetDeductionEvent(BudgetEvent):
    """A budget deduction was applied.

    Attributes:
        amount: The quantity deducted.
        remaining: The remaining budget after deduction.
    """

    amount: float
    remaining: float


class BudgetWarningEvent(BudgetEvent):
    """A budget threshold was crossed, triggering a warning.

    Attributes:
        threshold_pct: The threshold percentage that was breached.
        remaining: The remaining budget at the time of warning.
    """

    threshold_pct: float
    remaining: float


class BudgetExhaustedEvent(BudgetEvent):
    """A budget dimension has been fully exhausted."""

    pass


# ---------------------------------------------------------------------------
# Capability gap events
# ---------------------------------------------------------------------------


class CapabilityGapEvent(Event):
    """Emitted when an actor requests a tool that is not available.

    Attributes:
        actor_id: The actor who made the request.
        requested_tool: The tool name that was requested but not found.
        input_data: The input the actor attempted to pass to the tool.
    """

    actor_id: ActorId
    requested_tool: ToolName
    input_data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Animator events
# ---------------------------------------------------------------------------


class AnimatorEvent(Event):
    """An event generated by the world animator (NPC / environment behaviour).

    Attributes:
        sub_type: Discriminator within the animator family.
        actor_id: The simulated actor or entity that produced the event.
        content: Free-form content payload.
    """

    sub_type: str
    actor_id: ActorId
    content: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Annotation events
# ---------------------------------------------------------------------------


class AnnotationEvent(Event):
    """A human or automated annotation attached to a service or entity.

    Attributes:
        service_id: The service being annotated.
        annotation_text: The annotation content.
        author: Who authored the annotation.
    """

    service_id: ServiceId
    annotation_text: str
    author: str


# ---------------------------------------------------------------------------
# Tier promotion events
# ---------------------------------------------------------------------------


class TierPromotionEvent(Event):
    """Records a service's fidelity tier being promoted or demoted.

    Attributes:
        service_id: The service whose tier changed.
        from_tier: The previous fidelity tier.
        to_tier: The new fidelity tier.
    """

    service_id: ServiceId
    from_tier: FidelityTier
    to_tier: FidelityTier


# ---------------------------------------------------------------------------
# Validation events
# ---------------------------------------------------------------------------


class ValidationFailureEvent(Event):
    """Emitted when a validation check fails.

    Attributes:
        failure_type: Category of validation failure.
        details: Detailed description or structured data about the failure.
        source_event_id: The event that failed validation.
    """

    failure_type: str
    details: dict[str, Any] = Field(default_factory=dict)
    source_event_id: EventId | None = None


# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------


class EngineLifecycleEvent(Event):
    """Tracks engine start/stop/health transitions.

    Attributes:
        engine_name: Name of the engine whose lifecycle changed.
        status: The new status (e.g. ``"started"``, ``"stopped"``, ``"error"``).
    """

    engine_name: str
    status: str


class SimulationEvent(Event):
    """Tracks simulation-level status changes.

    Attributes:
        status: The new simulation status.
        world_id: The world instance this simulation pertains to.
    """

    status: str
    world_id: WorldId
