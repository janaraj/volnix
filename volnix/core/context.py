"""Pipeline context and step result types.

This module provides the mutable :class:`ActionContext` that flows through
every pipeline step, accumulating intermediate results; the immutable
:class:`StepResult` returned by each step; and the immutable
:class:`ResponseProposal` that captures a proposed response before it is
committed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from volnix.core.types import (
    ActionCost,
    ActionSource,
    ActorId,
    EntityId,
    FidelityMetadata,
    RealityPreset,
    RunId,
    ServiceId,
    SideEffect,
    StateDelta,
    StepVerdict,
    WorldMode,
)

# ---------------------------------------------------------------------------
# Step result (immutable)
# ---------------------------------------------------------------------------


class StepResult(BaseModel, frozen=True):
    """Immutable result returned by a single pipeline step.

    Attributes:
        step_name: Canonical name of the step that produced this result.
        verdict: The step's outcome verdict.
        message: Human-readable explanation of the verdict.
        events: Events generated during step execution.
        metadata: Arbitrary metadata produced by the step.
        duration_ms: Wall-clock milliseconds the step took to execute.
    """

    step_name: str
    verdict: StepVerdict
    message: str = ""
    events: list[Any] = Field(default_factory=list)  # Event objects (not EventId strings)
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` if this verdict should stop the pipeline."""
        return self.verdict in (
            StepVerdict.DENY,
            StepVerdict.HOLD,
            StepVerdict.ESCALATE,
            StepVerdict.ERROR,
        )


# ---------------------------------------------------------------------------
# Response proposal (immutable)
# ---------------------------------------------------------------------------


class ResponseProposal(BaseModel, frozen=True):
    """An immutable proposal for the response to an action request.

    Created by the responder engine, this captures the intended response
    body together with all state mutations and side effects that should
    be committed atomically.

    Attributes:
        response_body: The response payload to return to the caller.
        proposed_events: Events that should be committed with this response.
        proposed_state_deltas: State mutations to apply.
        proposed_side_effects: Side effects to execute.
        fidelity: Fidelity metadata for the generated response.
        fidelity_warning: Optional human-readable fidelity caveat.
    """

    response_body: dict[str, Any] = Field(default_factory=dict)
    proposed_events: list[Any] = Field(default_factory=list)
    proposed_state_deltas: list[StateDelta] = Field(default_factory=list)
    proposed_side_effects: list[SideEffect] = Field(default_factory=list)
    fidelity: FidelityMetadata | None = None
    fidelity_warning: str | None = None


# ---------------------------------------------------------------------------
# Action context (mutable -- accumulates data across pipeline steps)
# ---------------------------------------------------------------------------


class ActionContext(BaseModel):
    """Mutable context object threaded through the governance pipeline.

    Each pipeline step reads from and writes to the context, progressively
    enriching it with permission results, policy verdicts, budget checks,
    capability evaluations, and finally a response proposal.

    Attributes:
        request_id: Unique identifier for this request.
        actor_id: The actor initiating the action.
        service_id: The target service.
        action: The action / tool being invoked.
        input_data: Raw input payload from the caller.
        target_entity: Optional target entity for the action.
        world_time: Simulated in-world time at request arrival.
        wall_time: Real wall-clock time at request arrival.
        tick: Logical clock value at request arrival.
        run_id: Identifier of the current evaluation run.
        permission_result: Result from the permission step (populated mid-pipeline).
        policy_result: Result from the policy step.
        budget_result: Result from the budget step.
        capability_result: Result from the capability-gap step.
        response_proposal: The proposed response (populated by responder).
        validation_result: Result from the validation step.
        commit_result: Result from the commit step.
        policy_flags: Accumulated policy flags/tags.
        fidelity: Fidelity metadata for this action.
        computed_cost: Computed resource cost for the action.
        short_circuited: Whether the pipeline was terminated early.
        short_circuit_step: Name of the step that caused early termination.
    """

    request_id: str
    actor_id: ActorId
    service_id: ServiceId
    action: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    target_entity: EntityId | None = None
    world_time: datetime | None = None
    wall_time: datetime | None = None
    tick: int = 0
    run_id: RunId | None = None
    source: ActionSource | None = None
    envelope_id: str | None = None

    # Pipeline step results (populated progressively)
    permission_result: StepResult | None = None
    policy_result: StepResult | None = None
    budget_result: StepResult | None = None
    capability_result: StepResult | None = None
    responder_result: StepResult | None = None
    response_proposal: ResponseProposal | None = None
    validation_result: StepResult | None = None
    commit_result: StepResult | None = None

    # World simulation context
    world_mode: WorldMode | str | None = None
    reality_preset: RealityPreset | str | None = None

    # Accumulated flags and metadata
    policy_flags: list[str] = Field(default_factory=list)
    fidelity: FidelityMetadata | None = None
    computed_cost: ActionCost | None = None
    short_circuited: bool = False
    short_circuit_step: str | None = None
