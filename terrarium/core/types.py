"""Domain types for the Terrarium framework.

This module defines all shared value objects, identity types, and enumerations
used across the Terrarium system. Every type here is either a lightweight
NewType alias, an immutable enum, or a frozen Pydantic model (value object).

Other modules should import these types rather than defining their own ad-hoc
representations.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, NewType

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

ProfileVersion = NewType("ProfileVersion", str)
"""Version tag for a service fidelity profile."""

EnvelopeId = NewType("EnvelopeId", str)
"""Unique identifier for an ActionEnvelope."""

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
    """

    api_calls: int = 0
    llm_spend_usd: float = 0.0
    world_actions: int = 0


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
