"""Anthropic tool use compatibility adapter.

Exposes Volnix world tools in Anthropic's native tool use format.
Agents using the Anthropic SDK can discover and call tools with zero
Volnix-specific code.

Routes (mounted on the shared FastAPI app):
  GET  /anthropic/v1/tools      — list tools in Anthropic format
  POST /anthropic/v1/tools/call  — execute a tool call
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from starlette.requests import Request

from volnix.core.types import ToolName
from volnix.engines.adapter.protocols._auth import resolve_actor_id
from volnix.engines.adapter.protocols._response import unwrap_single_entity
from volnix.engines.adapter.protocols.base import ProtocolAdapter

logger = logging.getLogger(__name__)


class AnthropicCompatAdapter(ProtocolAdapter):
    """Anthropic tool use compatible endpoint.

    Adds ``/anthropic/v1/tools`` and ``/anthropic/v1/tools/call`` routes to
    the shared FastAPI app. Tools are served in Anthropic's ``{"name": ...,
    "input_schema": {...}}`` format via
    ``Gateway.get_tool_manifest(protocol="anthropic")``.
    """

    protocol_name: ClassVar[str] = "anthropic"

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def start_server(self) -> None:
        """Mount Anthropic compat routes on the HTTP adapter's FastAPI app."""
        http_adapter = self._gateway._adapters.get("http")
        if http_adapter is None or http_adapter.fastapi_app is None:
            logger.warning("Anthropic compat: HTTP adapter not available, skipping")
            return

        app = http_adapter.fastapi_app
        gateway = self._gateway
        self._mount_routes(app, gateway)
        logger.info(
            "Anthropic compat routes mounted: /anthropic/v1/tools, /anthropic/v1/tools/call"
        )

    async def stop_server(self) -> None:
        """No-op — routes live on the shared FastAPI app."""

    async def translate_inbound(
        self, tool_name: ToolName, raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Anthropic sends tool input directly — pass through."""
        return raw_input

    async def translate_outbound(
        self, tool_name: ToolName, internal_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Wrap response in Anthropic tool_result format."""
        is_error = isinstance(internal_response, dict) and "error" in internal_response
        return {
            "type": "tool_result",
            "content": json.dumps(internal_response, default=str),
            "is_error": is_error,
        }

    async def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return tools in Anthropic tool use format."""
        return await self._gateway.get_tool_manifest(protocol="anthropic")

    @staticmethod
    def _mount_routes(app: Any, gateway: Any) -> None:
        """Add Anthropic compat routes to the FastAPI app via APIRouter."""
        import fastapi
        from starlette.responses import JSONResponse

        router = fastapi.APIRouter(prefix="/anthropic/v1", tags=["anthropic-compat"])

        @router.get("/tools")
        async def list_tools_anthropic(
            actor_id: str = fastapi.Query(default="anthropic-agent"),
        ):
            """List tools in Anthropic tool use format."""
            return await gateway.get_tool_manifest(
                actor_id=actor_id, protocol="anthropic",
            )

        @router.post("/tools/call")
        async def call_tool_anthropic(request: Request):
            """Execute a tool call in Anthropic format.

            Request body::

                {"name": "email_send", "input": {"to": "a@b.com"}, "actor_id": "agent-1"}

            Response::

                {"type": "tool_result", "content": "{...}", "is_error": false}
            """
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=422,
                    content={"error": "Malformed JSON in request body"},
                )

            tool_name = body.get("name", "")
            # Anthropic uses "input" for tool arguments (not "arguments")
            arguments = body.get("input", {})

            if not tool_name:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Missing 'name' field in request body"},
                )

            if not isinstance(arguments, dict):
                return JSONResponse(
                    status_code=422,
                    content={"error": "'input' must be a dict"},
                )

            # Resolve actor identity (same pattern as HTTP REST)
            actor_id = resolve_actor_id(
                request, body, default="anthropic-agent", gateway=gateway,
            )
            if actor_id is None:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid or expired agent token"},
                )

            result = await gateway.handle_request(
                actor_id=actor_id,
                tool_name=tool_name,
                input_data=arguments,
            )

            # Strip internal fields and unwrap single-entity wrappers
            if isinstance(result, dict):
                result.pop("_event", None)
                result = unwrap_single_entity(result)

            is_error = isinstance(result, dict) and "error" in result
            return {
                "type": "tool_result",
                "content": json.dumps(result, default=str),
                "is_error": is_error,
            }

        app.include_router(router)
