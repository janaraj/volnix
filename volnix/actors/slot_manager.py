"""External agent slot manager — identity lifecycle for external agents.

Orchestrates the Discover → Register → Act flow:
1. Discover: query ActorRegistry for available external actor slots
2. Register: claim a slot, get an agent token
3. Act: resolve token on every request to get the actor identity

Uses SlotBinding for session tracking and ActorRegistry for actor definitions.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel

from volnix.actors.config import SlotManagerConfig
from volnix.actors.definition import ActorDefinition
from volnix.actors.registry import ActorRegistry
from volnix.actors.slot_binding import SlotBinding
from volnix.core.types import ActorId

logger = logging.getLogger(__name__)

AgentToken = str


class SlotInfo(BaseModel, frozen=True):
    """An available or claimed actor slot, exposed via the discovery API."""

    actor_id: str
    role: str
    permissions: dict[str, Any] = {}
    budget: dict[str, Any] | None = None
    status: str = "available"  # "available" | "claimed"


class RegistrationResult(BaseModel, frozen=True):
    """Result of claiming a slot."""

    agent_token: str
    actor_id: str
    role: str
    permissions: dict[str, Any] = {}
    budget: dict[str, Any] | None = None


class SlotManager:
    """Manages external agent connections to world-defined actor slots.

    Responsibilities:
    - Discover available external actor slots from ActorRegistry
    - Register external agents to slots (issue tokens)
    - Resolve tokens to ActorIds on every request
    - Handle auto-assignment for simple cases
    - Fall back to default actor for unregistered requests
    """

    def __init__(
        self,
        actor_registry: ActorRegistry,
        config: SlotManagerConfig | None = None,
    ) -> None:
        self._registry = actor_registry
        self._config = config or SlotManagerConfig()
        self._binding = SlotBinding(max_agents=self._config.max_external_agents)
        # token -> (actor_id, agent_name)
        self._tokens: dict[str, tuple[ActorId, str]] = {}
        # actor_id -> token (reverse lookup)
        self._actor_tokens: dict[str, str] = {}

    def discover_slots(self) -> list[SlotInfo]:
        """Return all external actor slots with their claim status."""
        slots: list[SlotInfo] = []
        for actor in self._registry.list_actors():
            # Only show agent-type actors (external agents, not system/internal)
            actor_type = str(getattr(actor, "type", ""))
            if actor_type != "agent":
                continue
            # Skip default gateway actors
            if str(actor.id) in ("http-agent", "mcp-agent"):
                continue

            perms = getattr(actor, "permissions", {})
            if hasattr(perms, "model_dump"):
                perms = perms.model_dump()
            budget = getattr(actor, "budget", None)
            if budget and hasattr(budget, "model_dump"):
                budget = budget.model_dump()

            slots.append(
                SlotInfo(
                    actor_id=str(actor.id),
                    role=getattr(actor, "role", ""),
                    permissions=perms if isinstance(perms, dict) else {},
                    budget=budget if isinstance(budget, dict) else None,
                    status="claimed" if self._binding.is_slot_claimed(actor.id) else "available",
                )
            )
        return slots

    def register(
        self,
        actor_id: ActorId,
        agent_name: str,
    ) -> RegistrationResult | None:
        """Claim a specific actor slot and issue an agent token.

        Args:
            actor_id: The world-defined actor to claim.
            agent_name: Human-readable name for the connecting agent.

        Returns:
            RegistrationResult with token, or None if slot unavailable.
        """
        # Verify actor exists in registry
        actor = self._registry.get_or_none(actor_id)
        if actor is None:
            logger.warning("Register failed: actor %s not in registry", actor_id)
            return None

        # Try to claim the slot
        token = self._generate_token()
        success = self._binding.claim_slot(actor_id, token)
        if not success:
            logger.warning("Register failed: slot %s already claimed", actor_id)
            return None

        # Store token mapping
        self._tokens[token] = (actor_id, agent_name)
        self._actor_tokens[str(actor_id)] = token

        perms = getattr(actor, "permissions", {})
        if hasattr(perms, "model_dump"):
            perms = perms.model_dump()
        budget = getattr(actor, "budget", None)
        if budget and hasattr(budget, "model_dump"):
            budget = budget.model_dump()

        logger.info(
            "Agent '%s' registered as %s (token: %s...)",
            agent_name,
            actor_id,
            token[:12],
        )

        return RegistrationResult(
            agent_token=token,
            actor_id=str(actor_id),
            role=getattr(actor, "role", ""),
            permissions=perms if isinstance(perms, dict) else {},
            budget=budget if isinstance(budget, dict) else None,
        )

    def restore_assignment(
        self,
        *,
        actor_id: ActorId,
        agent_name: str,
        token: str,
    ) -> None:
        """Re-hydrate a persisted ``(actor, agent, token)`` tuple into
        in-memory state (PMF Plan Phase 4C Step 5, audit-fold H2).

        Used by ``SessionManager.resume`` to restore slot pinnings
        after a process restart. Populates the two dicts AND calls
        ``self._binding.claim_slot(actor_id, token)`` so
        ``discover_slots()`` correctly reports the slot as
        ``claimed``. Skipping the binding step (pre-audit) would
        have let a second agent steal a restored slot.

        Idempotent: a duplicate call with the same ``token`` is a
        no-op; a call with a DIFFERENT token for the same
        ``actor_id`` overwrites the prior token (matches the
        ``register`` reassign semantics).

        Does NOT consult the actor registry — restore trusts the
        persisted data, supporting the case where the registry has
        been re-populated since the original pinning.
        """
        self._tokens[token] = (actor_id, agent_name)
        self._actor_tokens[str(actor_id)] = token
        # Idempotent claim: if the binding already exists for this
        # (actor, token) pair, ``claim_slot`` returns True. A stale
        # token for the same actor is cleared first.
        if self._binding.is_slot_claimed(actor_id):
            existing_session = self._binding.get_session_for_actor(actor_id)
            if existing_session != token:
                self._binding.release_slot(existing_session or "")
        self._binding.claim_slot(actor_id, token)

    def auto_assign(
        self,
        agent_name: str,
        role_hint: str | None = None,
    ) -> RegistrationResult | None:
        """Auto-assign an agent to the first available slot.

        Args:
            agent_name: Human-readable name for the agent.
            role_hint: Prefer slots with this role (optional).

        Returns:
            RegistrationResult, or None if no slots available.
        """
        if not self._config.auto_assign_enabled:
            return None

        slots = self.discover_slots()
        available = [s for s in slots if s.status == "available"]

        if not available:
            return None

        # Prefer role match if hint provided
        if role_hint:
            matched = [s for s in available if role_hint.lower() in s.role.lower()]
            if matched:
                available = matched

        target = available[0]
        return self.register(ActorId(target.actor_id), agent_name)

    def resolve_token(self, token: str) -> ActorId | None:
        """Resolve an agent token to an ActorId. O(1)."""
        entry = self._tokens.get(token)
        return entry[0] if entry else None

    def resolve_actor_id(self, raw_actor_id: str) -> str:
        """Resolve a raw actor_id string.

        Priority:
        1. Known registered actor → return as-is
        2. allow_unregistered_access → auto-register with defaults, return
        3. Fall back to http-agent
        """
        if self._registry.get_or_none(ActorId(raw_actor_id)) is not None:
            return raw_actor_id

        # Auto-register unknown agents with defaults
        if self._config.allow_unregistered_access:
            result = self.register_default_agent(raw_actor_id)
            if result:
                return result.actor_id  # Return the REGISTERED ID (includes hash)

        return "http-agent"

    def register_from_profile(
        self,
        definitions: list[ActorDefinition],
    ) -> int:
        """Register external agent definitions from a loaded profile.

        Called during create_run() when --agents flag is used.

        Args:
            definitions: ActorDefinition objects from profile YAML.

        Returns:
            Number of agents registered.
        """
        count = 0
        for actor_def in definitions:
            if not self._registry.has_actor(actor_def.id):
                self._registry.register(actor_def)
                count += 1
                logger.info(
                    "Registered agent profile: %s (role=%s)",
                    actor_def.id,
                    actor_def.role,
                )
        return count

    def register_default_agent(self, agent_name: str) -> RegistrationResult | None:
        """Auto-register an unknown agent with default permissions.

        Called when allow_unregistered_access=True and an unknown actor_id
        comes through. Creates a default ActorDefinition and registers it.

        Args:
            agent_name: The actor_id string from the request.

        Returns:
            RegistrationResult, or None if disabled.
        """
        if not self._config.allow_unregistered_access:
            return None

        from volnix.actors.profile import make_default_agent

        actor_def = make_default_agent(
            agent_name=agent_name,
            default_permissions=self._config.default_permissions,
            default_budget=self._config.default_budget,
        )

        # Idempotent — skip if already registered
        if self._registry.has_actor(actor_def.id):
            return RegistrationResult(
                agent_token="",
                actor_id=str(actor_def.id),
                role=actor_def.role,
                permissions=actor_def.permissions,
                budget=actor_def.budget,
            )

        self._registry.register(actor_def)
        logger.info("Auto-registered agent: %s with default permissions", agent_name)

        return RegistrationResult(
            agent_token="",
            actor_id=str(actor_def.id),
            role=actor_def.role,
            permissions=actor_def.permissions,
            budget=actor_def.budget,
        )

    def release(self, token: str) -> ActorId | None:
        """Release a slot and invalidate the token."""
        entry = self._tokens.pop(token, None)
        if entry is None:
            return None
        actor_id, agent_name = entry
        self._actor_tokens.pop(str(actor_id), None)
        self._binding.release_slot(token)
        logger.info("Agent '%s' released slot %s", agent_name, actor_id)
        return actor_id

    def get_agent_name(self, token: str) -> str | None:
        """Get the human-readable agent name for a token."""
        entry = self._tokens.get(token)
        return entry[1] if entry else None

    def _generate_token(self) -> str:
        """Generate a unique agent token."""
        return f"{self._config.token_prefix}{uuid.uuid4().hex}"
