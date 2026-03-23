"""HTTP REST Adapter -- exposes Terrarium world tools as REST API endpoints.

Routes:
  GET  /api/v1/tools              -- list available tools
  POST /api/v1/actions/{tool}     -- execute a tool call
  GET  /api/v1/health             -- health check
  GET  /api/v1/entities/{type}    -- query entities (read-only)
  WS   /api/v1/events/stream      -- WebSocket for event streaming

Uses: FastAPI + Uvicorn
Uses: Gateway.handle_request() for all tool calls
"""

import asyncio
import json
import logging
from typing import Any, ClassVar

from terrarium.core import ActionContext, ActorId
from terrarium.engines.adapter.protocols.base import ProtocolAdapter

logger = logging.getLogger(__name__)


class HTTPRestAdapter(ProtocolAdapter):
    """Exposes Terrarium world as a REST API."""

    protocol_name: ClassVar[str] = "http"

    def __init__(self, gateway: Any, config: Any = None) -> None:
        self._gateway = gateway
        self._config = config
        self._app_instance: Any = None
        self._server_task: Any = None

    async def start_server(self) -> None:
        """Create FastAPI app with routes."""
        import fastapi
        from starlette.requests import Request as StarletteRequest
        from starlette.websockets import WebSocket, WebSocketDisconnect

        app = fastapi.FastAPI(
            title="Terrarium World API",
            description="Simulated world services -- agents interact here",
        )

        gateway = self._gateway

        @app.get("/api/v1/tools")
        async def list_tools(
            actor_id: str = fastapi.Query(default="http-agent"),
        ):
            """List all tools available in this world."""
            return await gateway.get_tool_manifest(
                actor_id=actor_id, protocol="http"
            )

        @app.post("/api/v1/actions/{tool_name}")
        async def call_tool(tool_name: str, request: StarletteRequest):
            """Execute a tool call through the full pipeline."""
            try:
                body = await request.json()
            except Exception:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=422,
                    content={"error": "Malformed JSON in request body"},
                )
            actor_id = body.get("actor_id", "http-agent")
            arguments = body.get("arguments", {})
            return await gateway.handle_request(
                protocol="http",
                actor_id=actor_id,
                tool_name=tool_name,
                arguments=arguments,
            )

        @app.get("/api/v1/health")
        async def health():
            return {"status": "ok"}

        @app.get("/api/v1/entities/{entity_type}")
        async def query_entities(entity_type: str):
            """Query entities from state (read-only view)."""
            state = gateway._app.registry.get("state")
            entities = await state.query_entities(entity_type)
            return {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": entities,
            }

        @app.websocket("/api/v1/events/stream")
        async def event_stream(websocket: WebSocket):
            """WebSocket endpoint for streaming events."""
            await websocket.accept()
            try:
                # Subscribe to the event bus
                bus = gateway._app.bus
                queue: asyncio.Queue = asyncio.Queue()

                async def _on_event(event: Any) -> None:
                    await queue.put(event)

                bus.subscribe("world", _on_event)

                while True:
                    event = await queue.get()
                    await websocket.send_json({
                        "event_type": getattr(event, "event_type", "unknown"),
                        "event_id": str(getattr(event, "event_id", "")),
                        "data": event.model_dump(mode="json") if hasattr(event, "model_dump") else {},
                    })
            except WebSocketDisconnect:
                logger.debug("WebSocket client disconnected")

        # -- Report endpoints --------------------------------------------------

        @app.get("/api/v1/report")
        async def get_full_report():
            """Generate a full evaluation report."""
            reporter = gateway._app.registry.get("reporter")
            return await reporter.generate_full_report()

        @app.get("/api/v1/report/scorecard")
        async def get_scorecard():
            """Generate the governance scorecard."""
            reporter = gateway._app.registry.get("reporter")
            return await reporter.generate_scorecard()

        @app.get("/api/v1/report/gaps")
        async def get_gaps():
            """Generate the capability gap log."""
            reporter = gateway._app.registry.get("reporter")
            return await reporter.generate_gap_log()

        @app.get("/api/v1/report/causal/{event_id}")
        async def get_causal(event_id: str):
            """Generate a causal trace for a specific event."""
            from terrarium.core.types import EventId as EId
            reporter = gateway._app.registry.get("reporter")
            return await reporter.generate_causal_trace(EId(event_id))

        @app.get("/api/v1/report/challenges")
        async def get_challenges():
            """Generate two-direction observation report (challenges + boundaries)."""
            reporter = gateway._app.registry.get("reporter")
            return await reporter.generate_condition_report()

        # Mount real-world API paths from pack http_path definitions
        await self._mount_pack_routes(app, gateway)

        self._app_instance = app
        logger.info("HTTP REST adapter created")

    async def _mount_pack_routes(self, app: Any, gateway: Any) -> None:
        """Auto-mount HTTP routes from pack tool definitions."""
        from starlette.requests import Request

        routes = await gateway.get_tool_manifest(protocol="http")
        for route_def in routes:
            path = route_def.get("path", "")
            method = route_def.get("method", "POST").upper()
            tool_name = route_def.get("tool_name", "")
            if not path or not tool_name:
                continue

            # Create a closure with the correct tool_name
            def make_handler(tn: str):
                async def handler(request: Request):
                    body = await request.json() if method == "POST" else {}
                    return await gateway.handle_request(
                        protocol="http",
                        actor_id="http-agent",
                        tool_name=tn,
                        arguments=body,
                    )
                return handler

            if method == "POST":
                app.post(path)(make_handler(tool_name))
            elif method == "GET":
                app.get(path)(make_handler(tool_name))

    async def run_server(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Run the FastAPI server (blocking)."""
        import uvicorn
        config = uvicorn.Config(
            self._app_instance, host=host, port=port, log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def stop_server(self) -> None:
        """Stop the HTTP server."""
        self._app_instance = None

    def translate_inbound(self, raw_request: Any) -> Any:
        """Not used -- FastAPI handles request parsing."""
        pass

    def translate_outbound(self, result: Any) -> Any:
        """Not used -- FastAPI handles response serialization."""
        pass

    async def get_tool_manifest(self, actor_id: ActorId | None = None) -> list[dict]:
        """Delegate to gateway."""
        return await self._gateway.get_tool_manifest(protocol="http")

    @property
    def fastapi_app(self) -> Any:
        """Access the underlying FastAPI app instance (for testing)."""
        return self._app_instance
