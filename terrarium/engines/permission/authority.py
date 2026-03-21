"""Authority checker -- read/write/action permission enforcement."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActorId, ServiceId, ToolName


class AuthorityChecker:
    """Checks actor authority for read, write, and action operations."""

    async def check_read(self, actor_id: ActorId, service_id: ServiceId) -> bool:
        """Check whether the actor may read from the service."""
        ...

    async def check_write(self, actor_id: ActorId, service_id: ServiceId) -> bool:
        """Check whether the actor may write to the service."""
        ...

    async def check_action(
        self, actor_id: ActorId, action: ToolName, input_data: dict[str, Any]
    ) -> tuple[bool, str]:
        """Check whether the actor may perform the action.

        Returns:
            A tuple of (allowed, reason).
        """
        ...
