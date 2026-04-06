"""Gateway -- single entry/exit point for all agent communication.

PURE protocol translation. ZERO business logic.
Discovers tools from PackRegistry (same source as WorldResponderEngine).
Routes all requests through VolnixApp.handle_action() -> 7-step pipeline.
Records every request to Ledger (GatewayRequestEntry).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from volnix.core.types import ActorId, ToolName
from volnix.gateway.config import GatewayConfig

logger = logging.getLogger(__name__)


class Gateway:
    """Single entry/exit point for all agent protocol communication."""

    def __init__(self, app: Any, config: GatewayConfig) -> None:
        self._app = app
        self._config = config
        self._adapters: dict[str, Any] = {}
        self._tool_map: dict[str, tuple[str, str]] = {}  # tool_name -> (service_id, action)
        self._world_services: set[str] | None = None  # filter to world's services when set
        self._started = False

    @property
    def config(self) -> GatewayConfig:
        """Public accessor for the gateway configuration."""
        return self._config

    async def initialize(self) -> None:
        """Discover tools from packs and create protocol adapters."""
        # Build tool map from the SAME PackRegistry the Responder uses
        responder = self._app.registry.get("responder")
        if hasattr(responder, "_pack_registry"):
            pack_registry = responder._pack_registry
            for tool_info in pack_registry.list_tools():
                tool_name = tool_info.get("name")
                if not tool_name:
                    continue
                service = tool_info.get("pack_name", tool_info.get("service", ""))
                self._tool_map[tool_name] = (service, tool_name)

        pack_tool_count = len(self._tool_map)

        # Tier 2 profile tools — only for services that have NO verified pack.
        # Pack tools are registered first, so `not in self._tool_map` ensures
        # pack tools always take precedence.
        if hasattr(responder, "_profile_registry"):
            for profile in responder._profile_registry.list_profiles():
                for op in profile.operations:
                    if op.name and op.name not in self._tool_map:
                        self._tool_map[op.name] = (profile.service_name, op.name)

        profile_tool_count = len(self._tool_map) - pack_tool_count
        logger.info(
            "Gateway: discovered %d tools from %d packs + %d from profiles",
            len(self._tool_map),
            len(set(s for s, _ in list(self._tool_map.values())[:pack_tool_count])),
            profile_tool_count,
        )

        # Create protocol adapters
        from volnix.engines.adapter.protocols.anthropic_compat import AnthropicCompatAdapter
        from volnix.engines.adapter.protocols.gemini_compat import GeminiCompatAdapter
        from volnix.engines.adapter.protocols.http_rest import HTTPRestAdapter
        from volnix.engines.adapter.protocols.mcp_server import MCPServerAdapter
        from volnix.engines.adapter.protocols.openai_compat import OpenAICompatAdapter

        mcp_adapter = MCPServerAdapter(self)
        http_adapter = HTTPRestAdapter(self, self._config)
        openai_adapter = OpenAICompatAdapter(self)
        anthropic_adapter = AnthropicCompatAdapter(self)
        gemini_adapter = GeminiCompatAdapter(self)
        self._adapters["mcp"] = mcp_adapter
        self._adapters["http"] = http_adapter
        self._adapters["openai"] = openai_adapter
        self._adapters["anthropic"] = anthropic_adapter
        self._adapters["gemini"] = gemini_adapter

        self._started = True

    def set_active_services(self, services: set[str]) -> None:
        """Restrict tools to only the services defined in the world.

        Called after world compilation. Until called, all packs are visible.
        """
        self._world_services = services if services else None
        if self._world_services:
            # Filter tool map to only active services
            self._tool_map = {
                name: (svc, action)
                for name, (svc, action) in self._tool_map.items()
                if svc in self._world_services
            }
            logger.info(
                "Gateway: filtered to %d tools from services %s",
                len(self._tool_map), self._world_services,
            )

    async def handle_request(
        self,
        actor_id: ActorId,
        tool_name: ToolName,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle an inbound tool-call request from an actor.

        Matches ``GatewayProtocol.handle_request()`` exactly.

        1. Resolve tool -> (service_id, action)
        2. Delegate to app.handle_action() -> 7-step pipeline
        3. Record to ledger (GatewayRequestEntry)
        4. Return response

        This method contains ZERO business logic.
        """
        start = time.monotonic()

        # Infer protocol from actor_id prefix for ledger recording
        protocol = self._infer_protocol(str(actor_id))

        # Resolve tool
        tool = str(tool_name)
        resolution = self._tool_map.get(tool)
        if resolution is None:
            await self._record_request(
                protocol, str(actor_id), tool, "capability_gap", 0,
            )
            return {
                "status": "capability_not_available",
                "message": f"Tool '{tool}' is not available in this world.",
                "available_tools": list(self._tool_map.keys()),
            }

        service_id, action = resolution

        # Delegate to pipeline (THE pipeline -- no shortcuts)
        result = await self._app.handle_action(
            actor_id=str(actor_id),
            service_id=service_id,
            action=action,
            input_data=input_data,
        )

        latency_ms = (time.monotonic() - start) * 1000
        status = "error" if "error" in result else "success"
        await self._record_request(
            protocol, str(actor_id), tool, status, latency_ms,
        )

        return result

    async def deliver_observation(
        self,
        actor_id: ActorId,
        observation: dict[str, Any],
    ) -> None:
        """Push an observation event to an actor."""
        logger.debug(
            "Gateway: deliver_observation to %s: %s",
            actor_id, list(observation.keys()),
        )

    @staticmethod
    def _infer_protocol(actor_id: str) -> str:
        """Infer protocol from actor ID for ledger recording."""
        if actor_id.startswith("mcp-"):
            return "mcp"
        if actor_id.startswith("http-"):
            return "http"
        if actor_id in ("system", "environment"):
            return "internal"
        # Compiled actors (e.g., "developer-a3b1799d") are internal
        if "-" in actor_id and not actor_id.startswith(("mcp-", "http-")):
            return "internal"
        return "unknown"

    async def get_tool_manifest(
        self, actor_id: str | None = None, protocol: str = "mcp",
    ) -> list[dict[str, Any]]:
        """Return tools available in the requested protocol format.

        Tools come from PackRegistry -- the same source as WorldResponderEngine.
        When a new pack is added, its tools appear here automatically.
        """
        responder = self._app.registry.get("responder")
        if not hasattr(responder, "_pack_registry"):
            return []

        pack_registry = responder._pack_registry
        tools: list[dict[str, Any]] = []

        for pack_meta in pack_registry.list_packs():
            pack_name = pack_meta["pack_name"]
            # Filter to world's active services when set
            if self._world_services and pack_name not in self._world_services:
                continue
            pack = pack_registry.get_pack(pack_name)
            from volnix.kernel.surface import ServiceSurface
            surface = ServiceSurface.from_pack(pack)

            if protocol == "mcp":
                tools.extend(surface.get_mcp_tools())
            elif protocol == "http":
                tools.extend(surface.get_http_routes())
            elif protocol == "openai":
                tools.extend(op.to_openai_function() for op in surface.operations)
            elif protocol == "anthropic":
                tools.extend(op.to_anthropic_tool() for op in surface.operations)
            elif protocol == "gemini":
                tools.extend(op.to_gemini_tool() for op in surface.operations)

        return tools

    async def _record_request(
        self, protocol: str, actor_id: str, tool_name: str,
        status: str, latency_ms: float,
    ) -> None:
        """Record gateway request to ledger."""
        ledger = self._app.ledger
        if ledger is None:
            return
        from volnix.ledger.entries import GatewayRequestEntry
        entry = GatewayRequestEntry(
            protocol=protocol,
            actor_id=ActorId(actor_id),
            action=tool_name,
            response_status=status,
            latency_ms=latency_ms,
        )
        await ledger.append(entry)

    async def start_adapters(self) -> None:
        """Start all protocol adapter servers."""
        for name, adapter in self._adapters.items():
            await adapter.start_server()
            logger.info("Gateway: %s adapter started", name)

    async def shutdown(self) -> None:
        """Stop all protocol adapter servers."""
        for name, adapter in self._adapters.items():
            await adapter.stop_server()
        self._started = False

