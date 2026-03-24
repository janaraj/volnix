"""Persistent runtime state for internal actors.

ActorState is mutable (unlike ActorDefinition which is frozen).
Updated deterministically after each committed event.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from terrarium.core.types import ActorId, EntityId


class WaitingFor(BaseModel, frozen=True):
    """Describes what an actor is waiting for."""

    description: str
    since: float  # logical_time when waiting started
    patience: float  # duration before frustration increases
    escalation_action: str | None = None


class ScheduledAction(BaseModel, frozen=True):
    """An action scheduled for a future logical time."""

    logical_time: float
    action_type: str
    description: str
    target_service: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ActorBehaviorTraits(BaseModel, frozen=True):
    """Normalized behavioral traits extracted from persona at compile time.

    These structured fields are used for tier classification routing.
    The persona dict remains freeform for LLM prompt realism.
    """

    cooperation_level: float = 0.5  # 0.0=hostile, 1.0=fully cooperative
    deception_risk: float = 0.0  # 0.0=honest, 1.0=highly deceptive
    authority_level: float = 0.0  # 0.0=no authority, 1.0=full authority
    stakes_level: float = 0.3  # 0.0=trivial, 1.0=critical
    ambient_activity_rate: float = 0.1  # 0.0=never initiates, 1.0=constantly active


class ActorState(BaseModel):
    """Persistent mutable state for an internal actor.

    This is NOT frozen -- it is updated deterministically during simulation.
    One ActorState per internal actor, managed by AgencyEngine.
    """

    actor_id: ActorId
    role: str
    actor_type: str = "internal"  # "external" | "internal"

    # Identity (generated at compile time, immutable during run)
    persona: dict[str, Any] = Field(default_factory=dict)
    behavior_traits: ActorBehaviorTraits = Field(default_factory=ActorBehaviorTraits)

    # Goal (v1: single active goal)
    current_goal: str | None = None
    goal_strategy: str | None = None

    # Reactive state (updated during simulation)
    waiting_for: WaitingFor | None = None
    frustration: float = 0.0  # 0.0 - 1.0
    urgency: float = 0.3  # 0.0 - 1.0

    # Memory
    pending_notifications: list[str] = Field(default_factory=list)
    recent_interactions: list[str] = Field(default_factory=list)

    # Scheduling
    scheduled_action: ScheduledAction | None = None

    # Activation
    activation_tier: int = 0  # 0, 1, 2, or 3
    watched_entities: list[EntityId] = Field(default_factory=list)

    # Configuration
    max_recent_interactions: int = 20
