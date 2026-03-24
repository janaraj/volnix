"""External agent slot binding manager.

Manages the mapping between external agent sessions and actor slots.
In-memory only (snapshot extension is future work).

Rules:
- Agent claims a slot by actor_id at connection time
- Two agents cannot claim the same slot (reject second)
- Permissions come from the ActorDefinition in that slot
- Reconnect resumes the same slot (by actor_id + session_id match)
"""

from __future__ import annotations

import logging

from terrarium.core.types import ActorId

logger = logging.getLogger(__name__)


class SlotBinding:
    """Manages external agent connections to actor slots.

    Rules:
    - Agent claims a slot by actor_id at connection time
    - Two agents cannot claim the same slot (reject second)
    - Permissions come from the ActorDefinition in that slot
    - Reconnect resumes the same slot (by actor_id match)
    """

    def __init__(self, max_agents: int = 10) -> None:
        self._bindings: dict[str, str] = {}  # str(actor_id) -> session_id
        self._sessions: dict[str, ActorId] = {}  # session_id -> actor_id
        self._max_agents = max_agents

    def claim_slot(self, actor_id: ActorId, session_id: str) -> bool:
        """Claim an actor slot.

        Returns True if successful, False if already claimed by another session.
        """
        key = str(actor_id)
        # If same session reconnecting, allow
        if key in self._bindings:
            existing_session = self._bindings[key]
            if existing_session == session_id:
                return True  # reconnect
            return False  # claimed by another
        if len(self._bindings) >= self._max_agents:
            return False  # capacity
        self._bindings[key] = session_id
        self._sessions[session_id] = actor_id
        return True

    def release_slot(self, session_id: str) -> ActorId | None:
        """Release a slot when agent disconnects. Returns the released actor_id."""
        actor_id = self._sessions.pop(session_id, None)
        if actor_id is not None:
            self._bindings.pop(str(actor_id), None)
        return actor_id

    def get_actor_for_session(self, session_id: str) -> ActorId | None:
        """Return the actor_id bound to the given session, or None."""
        return self._sessions.get(session_id)

    def get_session_for_actor(self, actor_id: ActorId) -> str | None:
        """Return the session_id bound to the given actor, or None."""
        return self._bindings.get(str(actor_id))

    def is_slot_claimed(self, actor_id: ActorId) -> bool:
        """Return True if the given actor slot is currently claimed."""
        return str(actor_id) in self._bindings

    def connected_count(self) -> int:
        """Return the number of currently connected agents."""
        return len(self._bindings)

    def list_connected(self) -> list[ActorId]:
        """Return all currently connected actor_ids."""
        return [ActorId(k) for k in self._bindings]
