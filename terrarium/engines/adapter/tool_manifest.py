"""Tool manifest generator -- builds protocol-specific tool lists from PackRegistry.

This is the bridge: PackRegistry (discovered packs) -> protocol-specific tool lists.
When a new pack is added to PackRegistry, its tools automatically appear.
"""

from __future__ import annotations

from typing import Any

from terrarium.core import ActorId


class ToolManifestGenerator:
    """Generates protocol-specific tool manifests from PackRegistry.

    This is the bridge: PackRegistry (discovered packs) -> protocol-specific tool lists.
    When a new pack is added to PackRegistry, its tools automatically appear.
    """

    def __init__(self, pack_registry: Any) -> None:
        self._pack_registry = pack_registry

    def generate(self, protocol: str = "mcp", actor_id: str | None = None) -> list[dict]:
        """Generate tool manifest for the given protocol.

        Uses ServiceSurface.to_mcp_tool() / to_http_route() etc.
        """
        from terrarium.kernel.surface import ServiceSurface
        tools: list[dict[str, Any]] = []
        for pack_meta in self._pack_registry.list_packs():
            pack = self._pack_registry.get_pack(pack_meta["pack_name"])
            surface = ServiceSurface.from_pack(pack)
            if protocol == "mcp":
                tools.extend(surface.get_mcp_tools())
            elif protocol == "http":
                tools.extend(surface.get_http_routes())
            elif protocol == "openai":
                tools.extend(op.to_openai_function() for op in surface.operations)
            elif protocol == "anthropic":
                tools.extend(op.to_anthropic_tool() for op in surface.operations)
        return tools

    async def filter_by_permissions(
        self, actor_id: ActorId, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter tools to only those the actor is permitted to use.

        Placeholder for Phase E2 permission filtering.
        """
        # Phase E1: return all tools unfiltered
        return tools
