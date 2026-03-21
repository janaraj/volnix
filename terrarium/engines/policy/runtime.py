"""Runtime policy management -- add, remove, update active policies."""

from __future__ import annotations

from typing import Any

from terrarium.core import PolicyId


class RuntimePolicyManager:
    """Manages the live set of active policies at runtime."""

    def __init__(self, engine: Any) -> None:
        """Initialize with a reference to the owning PolicyEngine."""
        self._engine = engine

    async def add(self, policy_def: dict[str, Any]) -> PolicyId:
        """Add a new policy to the active set."""
        ...

    async def remove(self, policy_id: PolicyId) -> None:
        """Remove a policy from the active set."""
        ...

    async def update(self, policy_id: PolicyId, updates: dict[str, Any]) -> None:
        """Update fields on an active policy."""
        ...

    async def list_active(self) -> list[dict[str, Any]]:
        """Return all currently active policies."""
        ...
