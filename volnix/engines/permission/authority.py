"""Authority checker -- read/write/action permission enforcement.

Provides standalone permission checks that can be used outside the
pipeline step context (e.g., by the adapter engine for tool filtering).
"""

from __future__ import annotations

from typing import Any

from volnix.core import ActorId, ServiceId, ToolName


class AuthorityChecker:
    """Checks actor authority for read, write, and action operations.

    Requires an ``actor_registry`` to be injected for actor lookups.
    """

    def __init__(self, actor_registry: Any = None) -> None:
        self._actor_registry = actor_registry

    async def check_read(self, actor_id: ActorId, service_id: ServiceId) -> bool:
        """Check whether the actor may read from the service.

        Returns ``True`` if the actor has read access to the service,
        or if the actor is not found in the registry (permissive default).
        """
        actor = self._get_actor(actor_id)
        if actor is None:
            return True

        perms = actor.permissions
        if not perms:
            return True

        read_access = perms.get("read", [])
        return self._check_access(read_access, str(service_id))

    async def check_write(self, actor_id: ActorId, service_id: ServiceId) -> bool:
        """Check whether the actor may write to the service.

        Returns ``True`` if the actor has write access to the service,
        or if the actor is not found in the registry (permissive default).
        """
        actor = self._get_actor(actor_id)
        if actor is None:
            return True

        perms = actor.permissions
        if not perms:
            return True

        write_access = perms.get("write", [])
        return self._check_access(write_access, str(service_id))

    async def check_action(
        self, actor_id: ActorId, action: ToolName, input_data: dict[str, Any]
    ) -> tuple[bool, str]:
        """Check whether the actor may perform the action.

        Returns:
            A tuple of (allowed, reason). If allowed is ``False``, reason
            explains why the action was denied.
        """
        actor = self._get_actor(actor_id)
        if actor is None:
            return True, ""

        perms = actor.permissions
        if not perms:
            return True, ""

        actions = perms.get("actions", {})
        if str(action) not in actions:
            # Action not in constraints = allowed
            return True, ""

        constraint = actions[str(action)]
        if isinstance(constraint, dict):
            for key, limit in constraint.items():
                field_name = key.replace("max_", "")
                input_val = input_data.get(field_name, input_data.get(key))
                if (
                    input_val is not None
                    and isinstance(input_val, (int, float))
                    and isinstance(limit, (int, float))
                    and input_val > limit
                ):
                    return False, (
                        f"Action '{action}' exceeds authority: "
                        f"{field_name}={input_val} > {key}={limit}"
                    )

        return True, ""

    def _get_actor(self, actor_id: ActorId) -> Any:
        """Look up an actor from the registry, returning None if not found."""
        if self._actor_registry is None:
            return None
        return self._actor_registry.get_or_none(actor_id)

    @staticmethod
    def _check_access(access_config: Any, service: str) -> bool:
        """Check if access config grants access to the given service.

        "all" → universal access. list → service must be in list. else → deny.
        """
        if access_config == "all":
            return True
        if isinstance(access_config, list):
            return service in access_config
        return False
