"""Actor registry -- generic multi-key in-memory store for actor definitions.

The :class:`ActorRegistry` holds all actor definitions for a world and
provides a generic ``query(**filters)`` for flexible lookups by role, type,
team, friction status, and friction category.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.state import ActorState
from terrarium.core.errors import ActorNotFoundError, DuplicateActorError
from terrarium.core.types import ActorId, ActorType, EntityId


class ActorRegistry:
    """In-memory registry of actor definitions for a world."""

    def __init__(self) -> None:
        self._actors: dict[ActorId, ActorDefinition] = {}
        self._role_index: dict[str, list[ActorId]] = defaultdict(list)
        self._type_index: dict[ActorType, list[ActorId]] = defaultdict(list)
        self._team_index: dict[str, list[ActorId]] = defaultdict(list)
        self._actor_states: dict[str, ActorState] = {}

    # -- Registration --------------------------------------------------------

    def register(self, actor: ActorDefinition) -> None:
        """Register an actor definition.

        Raises :class:`DuplicateActorError` if an actor with the same ID
        is already registered.
        """
        if actor.id in self._actors:
            raise DuplicateActorError(
                f"Actor '{actor.id}' is already registered",
                context={"actor_id": actor.id},
            )
        self._actors[actor.id] = actor
        self._role_index[actor.role].append(actor.id)
        self._type_index[actor.type].append(actor.id)
        if actor.team is not None:
            self._team_index[actor.team].append(actor.id)

    def register_batch(self, actors: list[ActorDefinition]) -> None:
        """Register multiple actor definitions at once."""
        for actor in actors:
            self.register(actor)

    # -- Lookup --------------------------------------------------------------

    def get(self, actor_id: ActorId) -> ActorDefinition:
        """Retrieve an actor by ID.

        Raises :class:`ActorNotFoundError` if no actor with the given ID
        is registered.
        """
        if actor_id not in self._actors:
            raise ActorNotFoundError(
                f"Actor '{actor_id}' not found",
                context={"actor_id": actor_id},
            )
        return self._actors[actor_id]

    def get_or_none(self, actor_id: ActorId) -> ActorDefinition | None:
        """Retrieve an actor by ID, returning ``None`` if not found."""
        return self._actors.get(actor_id)

    # -- Generic query -------------------------------------------------------

    def query(self, **filters: Any) -> list[ActorDefinition]:
        """Generic multi-key lookup.

        Supported filters (AND logic):
        - ``role``: match actor role string
        - ``type``: match :class:`ActorType`
        - ``team``: match team string
        - ``has_friction``: ``True`` for actors with a friction profile
        - ``friction_category``: match friction profile category
        """
        known = {"role", "type", "team", "has_friction", "friction_category"}
        unknown = set(filters) - known
        if unknown:
            raise ValueError(f"Unknown query filters: {unknown}. Valid: {sorted(known)}")

        if not filters:
            return list(self._actors.values())

        # Start with all actor IDs
        result_ids: set[ActorId] | None = None

        # Index-based filters (fast set intersection)
        if "role" in filters:
            ids = set(self._role_index.get(filters["role"], []))
            result_ids = ids if result_ids is None else result_ids & ids
        if "type" in filters:
            ids = set(self._type_index.get(filters["type"], []))
            result_ids = ids if result_ids is None else result_ids & ids
        if "team" in filters:
            ids = set(self._team_index.get(filters["team"], []))
            result_ids = ids if result_ids is None else result_ids & ids

        # Get actor objects
        if result_ids is None:
            results = list(self._actors.values())
        else:
            results = [self._actors[aid] for aid in result_ids if aid in self._actors]

        # Object-level filters (linear scan on filtered set)
        if "has_friction" in filters:
            want = filters["has_friction"]
            results = [a for a in results if (a.friction_profile is not None) == want]
        if "friction_category" in filters:
            cat = filters["friction_category"]
            results = [
                a
                for a in results
                if a.friction_profile and a.friction_profile.category == cat
            ]

        return results

    # -- Convenience ---------------------------------------------------------

    def list_actors(self) -> list[ActorDefinition]:
        """Return all registered actor definitions."""
        return list(self._actors.values())

    def count(self) -> int:
        """Return the total number of registered actors."""
        return len(self._actors)

    def has_actor(self, actor_id: ActorId) -> bool:
        """Check whether an actor with the given ID is registered."""
        return actor_id in self._actors

    def summary(self) -> dict[str, Any]:
        """Return metadata: counts by type, role, and friction status."""
        by_type: dict[str, int] = defaultdict(int)
        by_role: dict[str, int] = defaultdict(int)
        friction_count = 0
        friction_by_cat: dict[str, int] = defaultdict(int)

        for actor in self._actors.values():
            by_type[actor.type.value] += 1
            by_role[actor.role] += 1
            if actor.friction_profile is not None:
                friction_count += 1
                friction_by_cat[actor.friction_profile.category] += 1

        return {
            "total": len(self._actors),
            "by_type": dict(by_type),
            "by_role": dict(by_role),
            "friction_count": friction_count,
            "friction_by_category": dict(friction_by_cat),
        }

    # -- Actor state management -----------------------------------------------

    def set_actor_state(self, actor_id: ActorId, state: ActorState) -> None:
        """Store or update the runtime state for an actor."""
        self._actor_states[str(actor_id)] = state

    def get_actor_state(self, actor_id: ActorId) -> ActorState | None:
        """Retrieve the runtime state for an actor, or None if not set."""
        return self._actor_states.get(str(actor_id))

    def list_internal_actors(self) -> list[ActorState]:
        """Return all actor states where actor_type is 'internal'."""
        return [s for s in self._actor_states.values() if s.actor_type == "internal"]

    def get_actors_watching(self, entity_id: EntityId) -> list[ActorState]:
        """Return all actor states that are watching the given entity."""
        return [
            s
            for s in self._actor_states.values()
            if entity_id in s.watched_entities
        ]

    def dump_states(self) -> list[dict[str, Any]]:
        """Serialize all actor states for snapshot persistence."""
        return [s.model_dump() for s in self._actor_states.values()]

    def load_states(self, states: list[dict[str, Any]]) -> None:
        """Deserialize and load actor states from a snapshot."""
        self._actor_states.clear()
        for data in states:
            state = ActorState.model_validate(data)
            self._actor_states[str(state.actor_id)] = state
