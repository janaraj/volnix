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
        async def query_entities(
            entity_type: str,
            actor_id: str = fastapi.Query(default="http-agent"),
        ):
            """Query entities — read-only view with permission check."""
            from terrarium.core.context import ActionContext as _AC
            from terrarium.core.types import ActorId as _AId, ServiceId as _SId, StepVerdict as _SV

            permission_engine = gateway._app.registry.get("permission")
            ctx = _AC(
                request_id="entity-query",
                actor_id=_AId(actor_id),
                service_id=_SId(entity_type),
                action=f"query_{entity_type}",
                input_data={},
            )
            result = await permission_engine.execute(ctx)
            if result.verdict != _SV.ALLOW:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=403,
                    content={"error": "Permission denied", "message": result.message},
                )

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

                await bus.subscribe("*", _on_event)

                while True:
                    event = await queue.get()
                    await websocket.send_json({
                        "event_type": getattr(event, "event_type", "unknown"),
                        "event_id": str(getattr(event, "event_id", "")),
                        "data": event.model_dump(mode="json") if hasattr(event, "model_dump") else {},
                    })
            except WebSocketDisconnect:
                logger.debug("WebSocket client disconnected")
                await bus.unsubscribe("*", _on_event)

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

        # -- Run management endpoints ------------------------------------------

        @app.post("/api/v1/runs")
        async def create_run_endpoint(request: StarletteRequest):
            """Create a new run record."""
            from starlette.responses import JSONResponse

            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=422,
                    content={"error": "Malformed JSON in request body"},
                )
            if not isinstance(body, dict):
                return JSONResponse(
                    status_code=422,
                    content={"error": "Request body must be a JSON object"},
                )
            allowed_keys = {
                "world_def", "config_snapshot", "mode",
                "reality_preset", "fidelity_mode", "tag",
            }
            unexpected = set(body.keys()) - allowed_keys
            if unexpected:
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": f"Unexpected fields: {', '.join(sorted(unexpected))}"
                    },
                )
            try:
                run_mgr = gateway._app.run_manager
                run_id = await run_mgr.create_run(**body)
            except TypeError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"error": f"Invalid input: {exc}"},
                )
            return {"run_id": str(run_id)}

        @app.get("/api/v1/runs")
        async def list_runs_endpoint(
            limit: int = fastapi.Query(default=20),
        ):
            """List recent runs, newest first."""
            return await gateway._app.run_manager.list_runs(limit=limit)

        @app.get("/api/v1/runs/{run_id}")
        async def get_run_endpoint(run_id: str):
            """Get metadata for a specific run."""
            from terrarium.core.types import RunId as _RId
            result = await gateway._app.run_manager.get_run(_RId(run_id))
            if result is None:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Run not found: {run_id}"},
                )
            return result

        @app.post("/api/v1/runs/{run_id}/complete")
        async def complete_run_endpoint(run_id: str):
            """Complete a run and save artifacts."""
            from terrarium.core.types import RunId as _RId
            return await gateway._app.end_run(_RId(run_id))

        @app.get("/api/v1/runs/{run_id}/artifacts")
        async def list_artifacts_endpoint(run_id: str):
            """List artifacts saved for a run."""
            from terrarium.core.types import RunId as _RId
            return await gateway._app.artifact_store.list_artifacts(_RId(run_id))

        @app.get("/api/v1/runs/{run_id}/artifacts/{artifact_type}")
        async def get_artifact_endpoint(run_id: str, artifact_type: str):
            """Load a specific artifact."""
            from terrarium.core.types import RunId as _RId
            result = await gateway._app.artifact_store.load_artifact(
                _RId(run_id), artifact_type,
            )
            if result is None:
                from starlette.responses import JSONResponse
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Artifact not found: {artifact_type}"},
                )
            return result

        @app.get("/api/v1/diff")
        async def diff_runs_endpoint(
            runs: str = fastapi.Query(
                ..., description="Comma-separated run IDs or tags",
            ),
        ):
            """Compare multiple runs."""
            run_ids = [r.strip() for r in runs.split(",")]
            return await gateway._app.diff_runs(run_ids)

        @app.get("/api/v1/diff/governed")
        async def diff_governed_endpoint(
            gov: str = fastapi.Query(...),
            ungov: str = fastapi.Query(...),
        ):
            """Specialized governed vs ungoverned comparison."""
            return await gateway._app.diff_governed_ungoverned(gov, ungov)

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

            # Create a closure capturing tool_name AND http_method properly
            def make_handler(tn: str, http_method: str):
                async def handler(request: Request):
                    path_params = dict(request.path_params)
                    if http_method == "GET":
                        # Merge path params + query params as arguments
                        arguments = dict(path_params)
                        arguments.update(dict(request.query_params))
                    else:
                        try:
                            body = await request.json()
                            arguments = body.get("arguments", body)
                        except Exception:
                            arguments = {}
                        # Path params override body values
                        arguments.update(path_params)
                    return await gateway.handle_request(
                        protocol="http",
                        actor_id=arguments.pop("actor_id", "http-agent"),
                        tool_name=tn,
                        arguments=arguments,
                    )
                return handler

            if method == "POST":
                app.post(path)(make_handler(tool_name, "POST"))
            elif method == "GET":
                app.get(path)(make_handler(tool_name, "GET"))

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
