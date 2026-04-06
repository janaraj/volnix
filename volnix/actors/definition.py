"""Actor definition model.

An :class:`ActorDefinition` is the complete description of an actor within
a Volnix world.  It is a single, generic model for ALL roles -- no
per-role subclasses.  Domain-specific fields go into ``metadata``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from volnix.actors.personality import FrictionProfile, Personality
from volnix.core.types import ActorId, ActorType


class ActorDefinition(BaseModel, frozen=True):
    """Complete definition of an actor in the world.

    Actors may be AI agents, human participants, or system-level services.
    Each actor has a unique identifier, a type, and a role that determines
    what actions they can perform.
    """

    id: ActorId
    type: ActorType
    role: str
    team: str | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] | None = None
    visibility: dict[str, Any] | None = None
    personality: Personality | None = None
    friction_profile: FrictionProfile | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    personality_hint: str = ""
