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
    SessionId,
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
# Governance event type constants — canonical strings used by pipeline engines
# ---------------------------------------------------------------------------

PERMISSION_DENIED = "permission.denied"
PERMISSION_ALLOW = "permission.allow"
POLICY_BLOCK = "policy.block"
POLICY_HOLD = "policy.hold"
POLICY_ESCALATE = "policy.escalate"
POLICY_FLAG = "policy.flag"
BUDGET_DEDUCTION = "budget.deduction"
BUDGET_WARNING = "budget.warning"

GOVERNANCE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        PERMISSION_DENIED,
        PERMISSION_ALLOW,
        POLICY_BLOCK,
        POLICY_HOLD,
        POLICY_ESCALATE,
        POLICY_FLAG,
        BUDGET_DEDUCTION,
        BUDGET_WARNING,
    }
)


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
        run_id: The evaluation run this event belongs to.
        action: The action that produced this event.
        service_id: The service the action targeted.
    """

    event_id: EventId = Field(default_factory=_generate_event_id)
    event_type: str
    timestamp: Timestamp
    caused_by: EventId | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    action: str = ""
    service_id: str = ""


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


class PermissionAllowEvent(Event):
    """Permission step allowed the action.

    Attributes:
        actor_id: The actor whose request was allowed.
        action: The action that was requested.
        reason: Why the action was allowed (e.g. ``"explicit_permission"``,
            ``"no_permissions_defined"``, ``"ungoverned"``).
    """

    actor_id: ActorId
    action: str
    reason: str


# ---------------------------------------------------------------------------
# Policy events
# ---------------------------------------------------------------------------


class PolicyEvent(Event):
    """Base for all governance-policy events.

    Attributes:
        policy_id: The policy that produced this event.
        actor_id: The actor whose action triggered policy evaluation.
        action: The action under evaluation.
    """

    policy_id: PolicyId
    actor_id: ActorId
    action: str


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


class CapabilityResolvedEvent(Event):
    """Tool/action resolved to a service handler.

    Attributes:
        actor_id: The actor whose tool request was resolved.
        requested_tool: The tool name that was requested.
        resolved_tier: Resolution tier (``"tier1"``, ``"tier2"``, or ``"passthrough"``).
        service_id: The service that provides the tool, if known.
    """

    actor_id: ActorId
    requested_tool: ToolName
    resolved_tier: str
    service_id: str = ""


class ResponderDispatchEvent(Event):
    """Responder generated a response for an action.

    Attributes:
        actor_id: The actor whose action triggered the response.
        action: The action that was handled.
        fidelity_tier: The fidelity tier used (1 or 2).
        profile_name: The profile name, if a Tier 2 profile was used.
        service_id: The service that handled the action, if known.
    """

    actor_id: ActorId
    action: str
    fidelity_tier: int
    profile_name: str = ""
    service_id: str = ""


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


# ---------------------------------------------------------------------------
# Active-NPC events (Layer 1 of the PMF plan)
#
# These events drive LLM-activated HUMAN actors. Passive NPCs — the
# default — neither emit nor react to them. See the Phase 0 regression
# oracle (``tests/integration/test_passive_npc_regression.py``) for the
# compile-time invariant protecting passive behavior.
#
# Event-type strings are frozen; changing them is a breaking change for
# subscriptions and test fixtures alike.
# ---------------------------------------------------------------------------


class NPCExposureEvent(WorldEvent):
    """An NPC becomes aware of a product feature.

    Source is one of:
      * ``seed`` — planted in the initial world state.
      * ``animator`` — opt-in exposure generation (Phase 3).
      * ``agent_action`` — caused by an agent's world action (e.g. a
        marketing email).
      * ``peer`` — word-of-mouth from another NPC.

    Attributes:
        npc_id: The NPC who is now exposed.
        feature_id: The product feature the NPC was exposed to.
        source: Where the exposure came from.
        medium: Optional human-readable medium (e.g.
            ``"push_notification"``, ``"billboard"``,
            ``"friend_mention"``). Informational only.
    """

    npc_id: ActorId
    feature_id: str
    source: str  # Literal enforced via docstring; kept as str for forward compat.
    medium: str | None = None


class WordOfMouthEvent(WorldEvent):
    """NPC A mentions a product feature to NPC B via the ``npc_chat`` pack.

    Emitted deterministically by the ``npc_chat`` pack when
    ``send_message`` is called with a non-empty ``feature_mention``.

    Attributes:
        sender_id: The NPC who sent the message.
        recipient_id: The NPC who received it.
        feature_id: The feature mentioned.
        sentiment: The mentioner's sentiment toward the feature.
    """

    sender_id: ActorId
    recipient_id: ActorId
    feature_id: str
    sentiment: str  # positive | neutral | negative


class NPCInterviewProbeEvent(WorldEvent):
    """A research-team agent sends a direct probe to an NPC.

    The NPC activates in response, produces an answer, and commits it
    as an ``interview_response`` entity (wired in Layer 2).

    Attributes:
        researcher_id: The agent doing the probing.
        npc_id: The target NPC.
        prompt: The question to ask.
        context: Arbitrary additional context for the NPC's prompt.
    """

    researcher_id: ActorId
    npc_id: ActorId
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


class NPCStateChangedEvent(Event):
    """Emitted after an NPC's persistent state mutates.

    Observability signal for the reporter and signal computers — lets
    them reconstruct awareness / interest / satisfaction trajectories
    without replaying the entire event log.

    Attributes:
        npc_id: The NPC whose state changed.
        before: State dict before the change.
        after: State dict after the change.
        cause_event_id: Optional event that caused the mutation.
    """

    npc_id: ActorId
    before: dict[str, Any]
    after: dict[str, Any]
    cause_event_id: EventId | None = None


class NPCDailyTickEvent(Event):
    """Periodic activation trigger for simulated day rhythm.

    Cadence is configured per-profile via ``activation_triggers:
    - scheduled: daily_life_tick``. The scheduler (Phase 2) emits this
    at the configured interval; active NPCs subscribed to
    ``daily_life_tick`` activate in response.

    Attributes:
        npc_id: The NPC receiving the tick.
        sim_day: The simulated day number.
    """

    npc_id: ActorId
    sim_day: int


# ---------------------------------------------------------------------------
# Cohort events (PMF Plan Phase 4A — activation cycling)
#
# Emitted by ``CohortManager.rotate`` cycles. The AgencyEngine listens
# for this in ``_handle_event`` and drains each promoted NPC's queue
# of deferred events through the normal activation path.
# ---------------------------------------------------------------------------


class CohortRotationEvent(Event):
    """Emitted after each ``CohortManager.rotate()`` cycle.

    Attributes:
        promoted_ids: NPCs just moved from dormant → active.
        demoted_ids: NPCs just moved from active → dormant.
        rotation_policy: Which policy ran this cycle
            (``round_robin`` / ``recency`` / ``event_pressure_weighted``).
        tick: Logical tick the rotation happened at.
    """

    event_type: str = "cohort.rotated"
    promoted_ids: list[ActorId] = Field(default_factory=list)
    demoted_ids: list[ActorId] = Field(default_factory=list)
    rotation_policy: str = ""
    tick: int = 0


# ---------------------------------------------------------------------------
# Session lifecycle events (PMF Plan Phase 4C Step 4)
# ---------------------------------------------------------------------------


class SessionStartedEvent(Event):
    """Emitted by ``SessionManager.start()`` (Step 5) when a new
    platform Session begins.

    Attributes:
        session_id: The new session's identifier.
        world_id: The world the session was started against.
        session_type: ``bounded`` | ``open`` | ``resumable``.
        seed_strategy: ``inherit`` | ``fresh`` | ``explicit``.
    """

    event_type: str = "session.started"
    session_id: SessionId
    world_id: WorldId
    session_type: str
    seed_strategy: str


class SessionPausedEvent(Event):
    """Emitted by ``SessionManager.pause()`` (Step 5) when a
    session transitions from ``ACTIVE`` to ``PAUSED``.

    Carries ``world_id`` for bus-consumer symmetry with
    ``SessionStartedEvent`` and ``SessionResumedEvent`` — a
    subscriber filtering by world shouldn't need a state lookup to
    route pause events.

    PMF Plan Phase 4C Step 5 audit-fold H5.

    Attributes:
        session_id: The paused session's identifier.
        world_id: The world the session belongs to.
        paused_at_tick: Logical tick at pause.
        note: Optional caller-supplied note (e.g. "awaiting input").
    """

    event_type: str = "session.paused"
    session_id: SessionId
    world_id: WorldId
    paused_at_tick: int = 0
    note: str = ""


class SessionEndedEvent(Event):
    """Emitted when a session transitions to a terminal status
    (``COMPLETED`` / ``ABANDONED``). Consumers subscribed via
    ``SessionManager.register_on_session_end(cb)`` (Step 5) receive
    both the callback AND this bus event — not either/or (PMF Plan
    D4 audit-fold).

    Attributes:
        session_id: The session that ended.
        world_id: The world the session belonged to. Optional
            (defaults to ``None``) to preserve backward compatibility
            with Step-4 rows that pre-date the field — review H3.
        status: Terminal status — ``completed`` or ``abandoned``.
        end_tick: Logical tick at session end. ``None`` when a
            paused session is abandoned across a process restart
            before a new run began (review M8 / D4k).
        reason: Optional human-readable reason (e.g. "goal_reached",
            "budget_exhausted", "manual").
    """

    event_type: str = "session.ended"
    session_id: SessionId
    world_id: WorldId | None = None
    status: str
    end_tick: int | None = None
    reason: str = ""


class SessionResumedEvent(Event):
    """Emitted by ``SessionManager.resume()`` (Step 5) when a paused
    session transitions back to ``ACTIVE``.

    Carries ``world_id`` for bus-consumer symmetry with
    ``SessionStartedEvent`` (review M5): a subscriber filtering by
    world shouldn't need a state lookup to route resume events.

    Attributes:
        session_id: The resumed session's identifier.
        world_id: The world the session belongs to.
        resumed_at_tick: Logical tick at resumption — equal to the
            session's preserved ``start_tick`` on first resume,
            advanced by prior runs on subsequent resumes.
    """

    event_type: str = "session.resumed"
    session_id: SessionId
    world_id: WorldId
    resumed_at_tick: int
