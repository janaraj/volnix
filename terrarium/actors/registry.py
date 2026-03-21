"""Actor registry -- in-memory store for actor definitions.

The :class:`ActorRegistry` holds all actor definitions for a world and
provides lookup helpers for common access patterns (by role, by type,
adversarial actors only, etc.).
"""

from __future__ import annotations

from terrarium.core.types import ActorId, ActorType
from terrarium.actors.definition import ActorDefinition


class ActorRegistry:
    """In-memory registry of actor definitions for a world."""

    def __init__(self) -> None:
        ...

    def register(self, actor: ActorDefinition) -> None:
        """Register an actor definition.

        Parameters
        ----------
        actor:
            The actor definition to register.
        """
        ...

    def get(self, actor_id: ActorId) -> ActorDefinition | None:
        """Retrieve an actor by ID.

        Returns ``None`` if no actor with the given ID is registered.
        """
        ...

    def list_actors(self) -> list[ActorDefinition]:
        """Return all registered actor definitions."""
        ...

    def get_by_role(self, role: str) -> list[ActorDefinition]:
        """Return all actors with the given role."""
        ...

    def get_by_type(self, actor_type: ActorType) -> list[ActorDefinition]:
        """Return all actors of the given type."""
        ...

    def get_adversarial(self) -> list[ActorDefinition]:
        """Return all actors that have adversarial characteristics."""
        ...

    def get_agents(self) -> list[ActorDefinition]:
        """Return all actors of type ``AGENT``."""
        ...

    def get_humans(self) -> list[ActorDefinition]:
        """Return all actors of type ``HUMAN``."""
        ...
