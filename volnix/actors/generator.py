"""Actor personality generator protocol.

Defines the :class:`ActorPersonalityGenerator` protocol that all generator
implementations must satisfy.  D2 provides :class:`SimpleActorGenerator`
(heuristic); D4 will add an LLM-based implementation.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from volnix.actors.definition import ActorDefinition
from volnix.actors.personality import FrictionProfile, Personality
from volnix.reality.dimensions import WorldConditions


@runtime_checkable
class ActorPersonalityGenerator(Protocol):
    """Protocol for actor personality generation."""

    async def generate_personality(
        self,
        role: str,
        personality_hint: str,
        conditions: WorldConditions,
        domain_context: str = "",
    ) -> Personality:
        """Generate a personality for the given role and conditions."""
        ...

    async def generate_friction_profile(
        self,
        category: str,
        intensity: int,
        sophistication: Literal["low", "medium", "high"],
        domain_context: str = "",
    ) -> FrictionProfile:
        """Generate a friction profile for the given category."""
        ...

    async def generate_batch(
        self,
        actor_specs: list[dict[str, Any]],
        conditions: WorldConditions,
        domain_context: str = "",
    ) -> list[ActorDefinition]:
        """Generate a batch of actors from YAML-style specs."""
        ...
