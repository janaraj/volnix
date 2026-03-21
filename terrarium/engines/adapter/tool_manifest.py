"""Tool manifest generator -- builds protocol-specific tool lists."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActorId, PermissionEngineProtocol, StateEngineProtocol


class ToolManifestGenerator:
    """Generates tool manifests filtered by actor permissions."""

    def __init__(
        self, state: StateEngineProtocol, permissions: PermissionEngineProtocol
    ) -> None:
        self._state = state
        self._permissions = permissions

    async def generate(
        self, actor_id: ActorId, protocol: str
    ) -> list[dict[str, Any]]:
        """Generate a tool manifest for the given actor and protocol."""
        ...

    async def filter_by_permissions(
        self, actor_id: ActorId, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter tools to only those the actor is permitted to use."""
        ...
