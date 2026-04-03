"""Google Gemini function calling compatibility adapter.

Exposes Terrarium world tools in Gemini's native function declaration format.
Agents using the Google GenAI SDK can discover and call tools with zero
Terrarium-specific code.

Routes (mounted on the shared FastAPI app):
  GET  /gemini/v1/tools      — list tools in Gemini function format
  POST /gemini/v1/tools/call  — execute a tool call
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from starlette.requests import Request

from terrarium.core.types import ToolName
from terrarium.engines.adapter.protocols._auth import resolve_actor_id
from terrarium.engines.adapter.protocols._response import unwrap_single_entity
from terrarium.engines.adapter.protocols.base import ProtocolAdapter

logger = logging.getLogger(__name__)


class GeminiCompatAdapter(ProtocolAdapter):
    """Google Gemini function calling compatible endpoint.

    Adds ``/gemini/v1/tools`` and ``/gemini/v1/tools/call`` routes to the
    shared FastAPI app. Tools are served using ``parameters_json_schema``
    so the Gemini SDK accepts standard JSON Schema dicts directly.
    """

    protocol_name: ClassVar[str] = "gemini"

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def start_server(self) -> None:
        """Mount Gemini compat routes on the HTTP adapter's FastAPI app."""
        http_adapter = self._gateway._adapters.get("http")
        if http_adapter is None or http_adapter.fastapi_app is None:
            logger.warning("Gemini compat: HTTP adapter not available, skipping")
            return

        app = http_adapter.fastapi_app
        gateway = self._gateway
        self._mount_routes(app, gateway)
        logger.info(
            "Gemini compat routes mounted: /gemini/v1/tools, /gemini/v1/tools/call"
        )

    async def stop_server(self) -> None:
        """No-op — routes live on the shared FastAPI app."""

    async def translate_inbound(
        self, tool_name: ToolName, raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Gemini sends function call args directly — pass through."""
        return raw_input

    async def translate_outbound(
        self, tool_name: ToolName, internal_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Wrap response in Gemini function response format."""
        return {
            "name": str(tool_name),
            "response": internal_response,
        }

    async def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return tools in Gemini function declaration format."""
        return await self._gateway.get_tool_manifest(protocol="gemini")

    @staticmethod
    def _mount_routes(app: Any, gateway: Any) -> None:
        """Add Gemini compat routes to the FastAPI app via APIRouter."""
        import fastapi
        from starlette.responses import JSONResponse

        router = fastapi.APIRouter(prefix="/gemini/v1", tags=["gemini-compat"])

        @router.get("/tools")
        async def list_tools_gemini(
            actor_id: str = fastapi.Query(default="gemini-agent"),
        ):
            """List tools in Gemini function declaration format."""
            return await gateway.get_tool_manifest(
                actor_id=actor_id, protocol="gemini",
            )

        @router.post("/tools/call")
        async def call_tool_gemini(request: Request):
            """Execute a tool call in Gemini format.

            Request body::

                {"name": "email_send", "args": {"to": "a@b.com"}, "actor_id": "agent-1"}

            Response::

                {"name": "email_send", "response": {...}}
            """
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=422,
                    content={"error": "Malformed JSON in request body"},
                )

            tool_name = body.get("name", "")
            # Gemini uses "args" for function call arguments
            arguments = body.get("args", {})

            if not tool_name:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Missing 'name' field in request body"},
                )

            if not isinstance(arguments, dict):
                return JSONResponse(
                    status_code=422,
                    content={"error": "'args' must be a dict"},
                )

            # Resolve actor identity (same pattern as all other adapters)
            actor_id = resolve_actor_id(
                request, body, default="gemini-agent", gateway=gateway,
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

            # Gemini function response format
            return {
                "name": tool_name,
                "response": result,
            }

        app.include_router(router)
