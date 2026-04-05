"""OpenAI function calling compatibility adapter.

Exposes Volnix world tools in OpenAI's native function calling format.
Agents using the OpenAI SDK can discover and call tools with zero
Volnix-specific code.

Routes (mounted on the shared FastAPI app):
  GET  /openai/v1/tools      — list tools in OpenAI function format
  POST /openai/v1/tools/call  — execute a tool call
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


class OpenAICompatAdapter(ProtocolAdapter):
    """OpenAI function calling compatible endpoint.

    Adds ``/openai/v1/tools`` and ``/openai/v1/tools/call`` routes to the
    shared FastAPI app. Tools are served in OpenAI's ``{"type": "function",
    "function": {...}}`` format via ``Gateway.get_tool_manifest(protocol="openai")``.
    """

    protocol_name: ClassVar[str] = "openai"

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway
        # Reverse map: sanitized name → original name (dots replaced with underscores)
        # OpenAI requires tool names to match ^[a-zA-Z0-9_-]+$
        self._name_map: dict[str, str] = {}

    async def start_server(self) -> None:
        """Mount OpenAI compat routes on the HTTP adapter's FastAPI app."""
        http_adapter = self._gateway._adapters.get("http")
        if http_adapter is None or http_adapter.fastapi_app is None:
            logger.warning("OpenAI compat: HTTP adapter not available, skipping")
            return

        app = http_adapter.fastapi_app
        gateway = self._gateway
        self._mount_routes(app, gateway)
        logger.info("OpenAI compat routes mounted: /openai/v1/tools, /openai/v1/tools/call")

    async def stop_server(self) -> None:
        """No-op — routes live on the shared FastAPI app."""

    async def translate_inbound(
        self, tool_name: ToolName, raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        """OpenAI sends function arguments directly — pass through."""
        return raw_input

    async def translate_outbound(
        self, tool_name: ToolName, internal_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Wrap response in OpenAI tool result format."""
        is_error = isinstance(internal_response, dict) and "error" in internal_response
        return {
            "role": "tool",
            "content": json.dumps(internal_response, default=str),
            "is_error": is_error,
        }

    async def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return tools in OpenAI function calling format."""
        return await self._gateway.get_tool_manifest(protocol="openai")

    def _mount_routes(self, app: Any, gateway: Any) -> None:
        """Add OpenAI compat routes to the FastAPI app via APIRouter."""
        import fastapi
        from starlette.responses import JSONResponse

        name_map = self._name_map
        router = fastapi.APIRouter(prefix="/openai/v1", tags=["openai-compat"])

        @router.get("/tools")
        async def list_tools_openai(
            actor_id: str = fastapi.Query(default="openai-agent"),
        ):
            """List tools in OpenAI function calling format."""
            tools = await gateway.get_tool_manifest(
                actor_id=actor_id, protocol="openai",
            )
            # Sanitize tool names: OpenAI requires ^[a-zA-Z0-9_-]+$
            # Build reverse map so /tools/call can restore original names
            name_map.clear()
            for t in tools:
                func = t.get("function", {})
                original = func.get("name", "")
                sanitized = original.replace(".", "_")
                if sanitized != original:
                    name_map[sanitized] = original
                    func["name"] = sanitized
            return tools

        @router.post("/tools/call")
        async def call_tool_openai(request: Request):
            """Execute a tool call in OpenAI format.

            Request body::

                {"name": "email_send", "arguments": {"to": "a@b.com"}, "actor_id": "agent-1"}

            Response::

                {"role": "tool", "content": "{...}", "is_error": false}
            """
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=422,
                    content={"error": "Malformed JSON in request body"},
                )

            sanitized_name = body.get("name", "")
            # Restore original tool name (with dots) from reverse map
            tool_name = name_map.get(sanitized_name, sanitized_name)
            arguments = body.get("arguments", {})

            if not tool_name:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Missing 'name' field in request body"},
                )

            if not isinstance(arguments, dict):
                return JSONResponse(
                    status_code=422,
                    content={"error": "'arguments' must be a dict"},
                )

            # Resolve actor identity (same pattern as HTTP REST)
            actor_id = resolve_actor_id(
                request, body, default="openai-agent", gateway=gateway,
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
                "role": "tool",
                "content": json.dumps(result, default=str),
                "is_error": is_error,
            }

        app.include_router(router)
