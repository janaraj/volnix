"""Domain types for the Volnix framework.

This module defines all shared value objects, identity types, and enumerations
used across the Volnix system. Every type here is either a lightweight
NewType alias, an immutable enum, or a frozen Pydantic model (value object).

Other modules should import these types rather than defining their own ad-hoc
representations.
"""

from __future__ import annotations

import enum
import uuid as _uuid
from datetime import datetime
from typing import Any, Literal, NewType

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Identity newtypes
# ---------------------------------------------------------------------------

EntityId = NewType("EntityId", str)
"""Globally unique identifier for any entity within a world."""

ActorId = NewType("ActorId", str)
"""Identifier for an actor (agent, human, or system) that can perform actions."""

ServiceId = NewType("ServiceId", str)
"""Identifier for a simulated service within a world."""

EventId = NewType("EventId", str)
"""Unique identifier for a single event in the event ledger."""

WorldId = NewType("WorldId", str)
"""Unique identifier for a world instance."""

SnapshotId = NewType("SnapshotId", str)
"""Identifier for a point-in-time snapshot of world state."""

PolicyId = NewType("PolicyId", str)
"""Identifier for a governance policy."""

ToolName = NewType("ToolName", str)
"""Canonical name for a tool exposed to agents."""

RunId = NewType("RunId", str)
"""Identifier for a single evaluation / interaction run."""

SessionId = NewType("SessionId", str)
"""Identifier for a platform Session — a container for ≥1 Run within
one World. Session spans activations, persists memory, survives
process restarts (``SessionManager`` owns the backing store).
PMF Plan Phase 4C Step 4."""

ActivationId = NewType("ActivationId", str)
"""Identifier for a single NPC/agent activation — the atomic unit
of LLM invocation inside a Run. Deterministically derived via
``uuid5(SESSION_NAMESPACE, f"{session_id}:{actor_id}:{tick}:{seq}")``
in Step 7 (PMF Plan D8); currently ``uuid4().hex[:12]`` at the two
call sites (``engines/agency/engine.py`` + ``npc_activator.py``).
Typed here ahead of Step 7 so the ``LLMUtteranceEntry`` schema
(Step 4) and the two pre-existing entries (``ToolLoopStepEntry``,
``ActivationCompleteEntry``) don't carry raw ``str`` activation
identifiers — closes CLAUDE.md's "never pass raw strings for
domain identifiers" violation."""

ProfileVersion = NewType("ProfileVersion", str)
"""Version tag for a service fidelity profile."""

EnvelopeId = NewType("EnvelopeId", str)
"""Unique identifier for an ActionEnvelope."""

MemoryRecordId = NewType("MemoryRecordId", str)
"""Unique identifier for a single :class:`volnix.core.memory_types.MemoryRecord`.
Phase 4B (PMF Plan)."""

TeamId = NewType("TeamId", str)
"""Identifier for a collaborative actor team. Plumbed in Phase 4B
for team-scope memory; exercised in Phase 4D."""

# PMF Plan Phase 4C Step 7 — deterministic ``activation_id``
# namespace. Stable UUID5 basis so replay-journal lookup keys are
# reproducible across Python processes (independent of
# PYTHONHASHSEED). The 12 trailing hex chars encode "volnix";
# leading 20 hex chars are zero-padded to a valid UUID shape.
SESSION_NAMESPACE: _uuid.UUID = _uuid.UUID("00000000-0000-0000-0000-766f6c6e6978")


def generate_activation_id(
    *,
    session_id: SessionId | None,
    actor_id: ActorId | str,
    tick: int,
    activation_index: int = 0,
) -> ActivationId:
    """Generate a 12-char ``ActivationId`` (PMF Plan D8 + Step 7).

    - Session present: deterministic via
      ``uuid5(SESSION_NAMESPACE, f"{session_id}:{actor_id}:{tick}:{activation_index}")``.
      Two calls with the same tuple return the same id — the
      replay-journal lookup key used by Step 8 ``ReplayLLMProvider``.
    - Session absent: falls back to ``uuid4().hex[:12]`` — matches
      pre-Step-7 behaviour so non-session runs stay identical.

    ``activation_index`` disambiguates parallel activations of the
    same actor at the same tick. Default ``0`` is correct for the
    current single-activation-per-tick NPC path; parallel-activation
    paths (future work) must supply a monotonic index.
    """
    if session_id is None:
        return ActivationId(_uuid.uuid4().hex[:12])
    key = f"{session_id}:{actor_id}:{tick}:{activation_index}"
    return ActivationId(_uuid.uuid5(SESSION_NAMESPACE, key).hex[:12])


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FidelityTier(enum.IntEnum):
    """Numeric tier indicating how faithful a service simulation is.

    Lower values indicate higher fidelity.
    """

    VERIFIED = 1
    PROFILED = 2


class FidelitySource(enum.StrEnum):
    """Where a service's fidelity comes from."""

    VERIFIED_PACK = "verified_pack"
    CURATED_PROFILE = "curated_profile"
    BOOTSTRAPPED = "bootstrapped"  # inferred at compile time, runs as Tier 2


class RealityPreset(enum.StrEnum):
    """World reality presets."""

    IDEAL = "ideal"
    MESSY = "messy"
    HOSTILE = "hostile"


class BehaviorMode(enum.StrEnum):
    """World behavior mode — how the world evolves over time."""

    STATIC = "static"
    REACTIVE = "reactive"
    DYNAMIC = "dynamic"


class FidelityMode(enum.StrEnum):
    """Service fidelity resolution mode."""

    AUTO = "auto"  # best available tier per service
    STRICT = "strict"  # only Tier 1/2, skip unknown services
    EXPLORATORY = "exploratory"  # allow bootstrapping for unknown services


class EnforcementMode(enum.StrEnum):
    """How a policy violation should be enforced."""

    HOLD = "hold"
    BLOCK = "block"
    ESCALATE = "escalate"
    LOG = "log"


class StepVerdict(enum.StrEnum):
    """Outcome verdict returned by a pipeline step."""

    ALLOW = "allow"
    DENY = "deny"
    HOLD = "hold"
    ESCALATE = "escalate"
    ERROR = "error"


class ActorType(enum.StrEnum):
    """Classification of an actor within the system."""

    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"
    OBSERVER = "observer"


class WorldMode(enum.StrEnum):
    """Operating mode of a world instance."""

    GOVERNED = "governed"
    UNGOVERNED = "ungoverned"


class ActionSource(enum.StrEnum):
    """Originator of an action in the simulation."""

    EXTERNAL = "external"  # user's agent via MCP/HTTP
    INTERNAL = "internal"  # internal actor via AgencyEngine
    ENVIRONMENT = "environment"  # world event via Animator


class EnvelopePriority(enum.IntEnum):
    """Priority for tie-breaking in EventQueue. Lower = higher priority."""

    SYSTEM = 0  # meta-actions (deliverable, lifecycle) — highest priority
    ENVIRONMENT = 1  # environment events (world state changes)
    EXTERNAL = 2  # external agent actions
    INTERNAL = 3  # internal actor actions — lowest priority


class GapResponse(enum.StrEnum):
    """How the system responded when a capability gap was detected."""

    HALLUCINATED = "hallucinated"
    ADAPTED = "adapted"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


class ValidationType(enum.StrEnum):
    """Categories of validation checks."""

    SCHEMA = "schema"
    STATE_MACHINE = "state_machine"
    CONSISTENCY = "consistency"
    TEMPORAL = "temporal"
    AMOUNT = "amount"
    SEED = "seed"
    COUNT = "count"


# ---------------------------------------------------------------------------
# Frozen value objects
# ---------------------------------------------------------------------------


class FidelityMetadata(BaseModel, frozen=True):
    """Metadata describing the fidelity characteristics of an action or event.

    Attributes:
        tier: The fidelity tier of the source service.
        source: Human-readable label for the fidelity source (e.g. profile name).
        profile_version: Optional version of the fidelity profile used.
        deterministic: Whether the service behaviour is fully deterministic.
        replay_stable: Whether replaying the same inputs yields identical outputs.
        benchmark_grade: Whether this fidelity level is suitable for benchmarking.
    """

    tier: FidelityTier
    source: str
    fidelity_source: FidelitySource | None = None
    profile_version: ProfileVersion | None = None
    deterministic: bool = False
    replay_stable: bool = False
    benchmark_grade: bool = False


class ActionCost(BaseModel, frozen=True):
    """Immutable record of resource costs incurred by a single action.

    Attributes:
        api_calls: Number of API calls consumed.
        llm_spend_usd: LLM token spend in US dollars.
        world_actions: Number of world-mutating actions performed.
        spend_usd: Domain spend in US dollars (e.g. refund amount, order value).
        time_seconds: Wall-clock seconds consumed by this action.
    """

    api_calls: int = 0
    llm_spend_usd: float = 0.0
    world_actions: int = 0
    spend_usd: float = 0.0
    time_seconds: float = 0.0


class BudgetState(BaseModel, frozen=True):
    """Snapshot of an actor's remaining budget across all dimensions.

    Attributes:
        api_calls_remaining: API calls still available.
        api_calls_total: Original API call budget.
        llm_spend_remaining_usd: Remaining LLM spend in USD.
        llm_spend_total_usd: Original LLM spend budget in USD.
        world_actions_remaining: World-mutating actions still available.
        world_actions_total: Original world-action budget.
        time_remaining_seconds: Wall-clock seconds remaining, if time-bounded.
    """

    api_calls_remaining: int
    api_calls_total: int
    llm_spend_remaining_usd: float
    llm_spend_total_usd: float
    world_actions_remaining: int
    world_actions_total: int
    spend_usd_remaining: float = 0.0
    spend_usd_total: float = 0.0
    time_remaining_seconds: float | None = None


class StateDelta(BaseModel, frozen=True):
    """Description of a single state mutation to an entity.

    Attributes:
        entity_type: The type/kind of the entity being mutated.
        entity_id: The unique identifier of the target entity.
        operation: One of ``"create"``, ``"update"``, or ``"delete"``.
        fields: The fields being set or changed.
        previous_fields: The prior values of changed fields, if available.
    """

    entity_type: str
    entity_id: EntityId
    operation: str  # "create" | "update" | "delete"
    fields: dict[str, Any]
    previous_fields: dict[str, Any] | None = None


class SideEffect(BaseModel, frozen=True):
    """Declarative description of a side effect that should be executed.

    Attributes:
        effect_type: Discriminator for the kind of side effect.
        target_service: The service that should execute the effect.
        target_entity: An optional entity the effect is directed at.
        parameters: Arbitrary key-value parameters for the effect handler.
    """

    effect_type: str
    target_service: ServiceId | None = None
    target_entity: EntityId | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class VisibilityRule(BaseModel, frozen=True):
    """Declarative rule for entity-level visibility scoping.

    Generated at compile time by the LLM from world context.
    Stored as entities in the State Engine (entity_type
    configurable via ``PermissionConfig.visibility_rule_entity_type``).

    Attributes:
        id: Unique rule identifier.
        actor_role: The actor role this rule applies to.
        target_entity_type: Entity type this rule scopes, or ``"*"`` for all.
        filter_field: Entity field to filter on (``None`` = see all).
        filter_value: Value to match.  ``$self.actor_id`` is resolved at runtime.
        include_unmatched: Also include entities where *filter_field* is null/empty.
        description: Human-readable explanation.
    """

    id: str
    actor_role: str
    target_entity_type: str
    filter_field: str | None = None
    filter_value: str | None = None
    include_unmatched: bool = False
    description: str = ""


class Timestamp(BaseModel, frozen=True):
    """Compound timestamp pairing world-internal time with wall-clock time.

    Attributes:
        world_time: The simulated in-world time.
        wall_time: The real wall-clock time when the event occurred.
        tick: Monotonically increasing logical clock / sequence number.
    """

    world_time: datetime
    wall_time: datetime
    tick: int


class RunResult(BaseModel, frozen=True):
    """Unified result from any runner (simulation or game).

    Both :class:`SimulationRunner` and :class:`OrchestratorRunner` return
    this type from ``run()``, eliminating the need for type-based
    dispatch in the CLI.

    Attributes:
        reason: Why the run stopped (StopReason value or game termination reason).
        runner_kind: Discriminator: ``"simulation"`` or ``"game"``.
        winner: Game-only — the winning actor, if any.
        total_events: Number of committed events processed.
        wall_clock_seconds: Elapsed wall-clock time.
        deliverable_produced: Whether a deliverable artifact was produced.
        deliverable_content: The deliverable JSON content, if produced.
        final_standings: Game-only — ordered player standings.
        behavior_scores: Game-only — per-player behavior metric scores.
    """

    reason: str
    runner_kind: Literal["simulation", "game"]
    winner: str | None = None
    total_events: int = 0
    wall_clock_seconds: float = 0.0
    deliverable_produced: bool = False
    deliverable_content: dict[str, Any] | None = None
    final_standings: list[dict[str, Any]] = Field(default_factory=list)
    behavior_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
