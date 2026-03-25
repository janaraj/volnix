"""HTTP REST Adapter -- exposes Terrarium world tools as REST API endpoints.

Routes:
  GET  /api/v1/tools                          -- list available tools
  POST /api/v1/actions/{tool}                 -- execute a tool call
  GET  /api/v1/health                         -- health check
  GET  /api/v1/entities/{type}                -- query entities (read-only)
  WS   /api/v1/events/stream                  -- WebSocket for event streaming
  GET  /api/v1/report                         -- full evaluation report
  GET  /api/v1/report/scorecard               -- governance scorecard
  GET  /api/v1/report/gaps                    -- capability gap log
  GET  /api/v1/report/causal/{event_id}       -- causal trace
  GET  /api/v1/report/challenges              -- condition report
  POST /api/v1/runs                           -- create run
  GET  /api/v1/runs                           -- list runs (paginated, filterable)
  GET  /api/v1/runs/{run_id}                  -- run detail
  POST /api/v1/runs/{run_id}/complete         -- complete a run
  GET  /api/v1/runs/{run_id}/artifacts        -- list artifacts
  GET  /api/v1/runs/{run_id}/artifacts/{type} -- get artifact
  GET  /api/v1/runs/{run_id}/events           -- run events (paginated, filterable)
  GET  /api/v1/runs/{run_id}/events/{eid}     -- event detail with causal chain
  GET  /api/v1/runs/{run_id}/scorecard        -- run-scoped scorecard
  GET  /api/v1/runs/{run_id}/entities         -- run entities (paginated)
  GET  /api/v1/runs/{run_id}/entities/{eid}   -- entity with state history
  GET  /api/v1/runs/{run_id}/gaps             -- run-scoped capability gaps
  GET  /api/v1/runs/{run_id}/actors/{aid}     -- actor detail with budgets
  GET  /api/v1/compare                        -- compare runs
  GET  /api/v1/diff                           -- compare runs (original)
  WS   /ws/runs/{run_id}/live                 -- run-scoped live event stream

Uses: FastAPI + Uvicorn
Uses: Gateway.handle_request() for all tool calls
"""

import asyncio
import logging
from typing import Any, ClassVar

from terrarium.core import ActorId
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

        # CORS for dashboard frontend (Vite dev server on port 3000)
        from starlette.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        gateway = self._gateway

        @app.get("/api/v1/tools")
        async def list_tools(
            actor_id: str = fastapi.Query(default="http-agent"),
        ):
            """List all tools available in this world."""
            return await gateway.get_tool_manifest(actor_id=actor_id, protocol="http")

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
            from terrarium.core.context import ActionContext as _ActCtx
            from terrarium.core.types import ActorId as _ActId
            from terrarium.core.types import ServiceId as _SvcId
            from terrarium.core.types import StepVerdict as _Verdict

            permission_engine = gateway._app.registry.get("permission")
            ctx = _ActCtx(
                request_id="entity-query",
                actor_id=_ActId(actor_id),
                service_id=_SvcId(entity_type),
                action=f"query_{entity_type}",
                input_data={},
            )
            result = await permission_engine.execute(ctx)
            if result.verdict != _Verdict.ALLOW:
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
            bus = gateway._app.bus
            queue: asyncio.Queue = asyncio.Queue()

            async def _on_event(event: Any) -> None:
                await queue.put(event)

            await bus.subscribe("*", _on_event)
            try:
                while True:
                    event = await queue.get()
                    try:
                        data = event.model_dump(mode="json") if hasattr(event, "model_dump") else {}
                    except Exception:
                        data = {}
                    await websocket.send_json(
                        {
                            "event_type": getattr(event, "event_type", "unknown"),
                            "event_id": str(getattr(event, "event_id", "")),
                            "data": data,
                        }
                    )
            except WebSocketDisconnect:
                logger.debug("WebSocket client disconnected")
            finally:
                try:
                    await bus.unsubscribe("*", _on_event)
                except Exception:
                    logger.debug("Failed to unsubscribe from event bus")

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
                "world_def",
                "config_snapshot",
                "mode",
                "reality_preset",
                "fidelity_mode",
                "tag",
            }
            unexpected = set(body.keys()) - allowed_keys
            if unexpected:
                return JSONResponse(
                    status_code=422,
                    content={"error": f"Unexpected fields: {', '.join(sorted(unexpected))}"},
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
            limit: int = fastapi.Query(default=20, ge=1, le=1000),
            offset: int = fastapi.Query(default=0, ge=0),
            status: str | None = fastapi.Query(default=None),
            preset: str | None = fastapi.Query(default=None),
            tag: str | None = fastapi.Query(default=None),
        ):
            """List runs, newest first. Supports pagination and filtering."""
            runs = await gateway._app.run_manager.list_runs()
            if status:
                runs = [r for r in runs if r.get("status") == status]
            if preset:
                runs = [r for r in runs if r.get("reality_preset") == preset]
            if tag:
                runs = [r for r in runs if r.get("tag") == tag]
            total = len(runs)
            paginated = runs[offset : offset + limit]
            return {"runs": paginated, "total": total}

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
            from starlette.responses import JSONResponse

            from terrarium.core.types import RunId as _RId

            try:
                return await gateway._app.end_run(_RId(run_id))
            except (KeyError, ValueError) as exc:
                return JSONResponse(
                    status_code=400,
                    content={"error": str(exc)},
                )

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
                _RId(run_id),
                artifact_type,
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
                ...,
                description="Comma-separated run IDs or tags",
            ),
        ):
            """Compare multiple runs."""
            from starlette.responses import JSONResponse

            run_ids = [r.strip() for r in runs.split(",")]
            try:
                return await gateway._app.diff_runs(run_ids)
            except (KeyError, ValueError) as exc:
                return JSONResponse(
                    status_code=400,
                    content={"error": str(exc)},
                )

        @app.get("/api/v1/diff/governed")
        async def diff_governed_endpoint(
            gov: str = fastapi.Query(...),
            ungov: str = fastapi.Query(...),
        ):
            """Specialized governed vs ungoverned comparison."""
            return await gateway._app.diff_governed_ungoverned(gov, ungov)

        # -- Run-scoped endpoints (dashboard frontend) -------------------------

        async def _load_run_events(run_id: str) -> list[dict]:
            """Load events from artifact (completed) or live engine (active)."""
            from terrarium.core.types import RunId as _RId

            events = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "event_log",
            )
            if events is not None:
                return events
            # Active run — query live state engine
            state_eng = gateway._app.registry.get("state")
            if state_eng:
                raw = await state_eng.get_timeline()
                return [e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in raw]
            return []

        @app.get("/api/v1/runs/{run_id}/events")
        async def get_run_events(
            run_id: str,
            limit: int = fastapi.Query(default=100, ge=1, le=1000),
            offset: int = fastapi.Query(default=0, ge=0),
            actor_id: str | None = fastapi.Query(default=None),
            service_id: str | None = fastapi.Query(default=None),
            event_type: str | None = fastapi.Query(default=None),
            outcome: str | None = fastapi.Query(default=None),
        ):
            """Paginated events for a run, filterable by actor/service/type/outcome."""
            events = await _load_run_events(run_id)
            if actor_id:
                events = [e for e in events if e.get("actor_id") == actor_id]
            if service_id:
                events = [
                    e
                    for e in events
                    if e.get("service_id") == service_id or e.get("target_service") == service_id
                ]
            if event_type:
                events = [e for e in events if e.get("event_type") == event_type]
            if outcome:
                events = [e for e in events if e.get("outcome") == outcome]
            total = len(events)
            paginated = events[offset : offset + limit]
            return {"run_id": run_id, "events": paginated, "total": total}

        @app.get("/api/v1/runs/{run_id}/events/{event_id}")
        async def get_event_detail(run_id: str, event_id: str):
            """Single event with full causal chain."""
            from starlette.responses import JSONResponse

            events = await _load_run_events(run_id)
            event = next(
                (e for e in events if e.get("event_id") == event_id),
                None,
            )
            if event is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Event not found: {event_id}"},
                )

            # Build causal chain by walking parent_event_ids
            event_map = {e.get("event_id"): e for e in events}
            ancestors: list[str] = []
            descendants: list[str] = []

            # Walk backward (ancestors via BFS)
            queue = list(event.get("parent_event_ids", []))
            visited: set[str] = set()
            while queue:
                pid = queue.pop(0)
                if pid in visited:
                    continue
                visited.add(pid)
                ancestors.append(pid)
                parent = event_map.get(pid)
                if parent:
                    queue.extend(parent.get("parent_event_ids", []))

            # Walk forward (descendants via BFS — recursive)
            # Build reverse index: event_id → list of child event_ids
            children_of: dict[str, list[str]] = {}
            for e in events:
                for pid in e.get("parent_event_ids", []):
                    children_of.setdefault(pid, []).append(e.get("event_id", ""))

            visited_fwd: set[str] = set()
            queue_fwd = list(children_of.get(event_id, []))
            while queue_fwd:
                cid = queue_fwd.pop(0)
                if not cid or cid in visited_fwd:
                    continue
                visited_fwd.add(cid)
                descendants.append(cid)
                queue_fwd.extend(children_of.get(cid, []))

            return {
                "event": event,
                "causal_ancestors": ancestors,
                "causal_descendants": descendants,
            }

        @app.get("/api/v1/runs/{run_id}/scorecard")
        async def get_run_scorecard(run_id: str):
            """Governance scorecard for a specific run."""
            from terrarium.core.types import RunId as _RId

            scorecard = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "scorecard",
            )
            if scorecard is None:
                # Try live reporter for active run
                reporter = gateway._app.registry.get("reporter")
                if reporter:
                    scorecard = await reporter.generate_scorecard()
            if scorecard is None:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=404,
                    content={"error": "Scorecard not available for this run"},
                )
            return {"run_id": run_id, **scorecard}

        @app.get("/api/v1/runs/{run_id}/entities")
        async def get_run_entities(
            run_id: str,
            limit: int = fastapi.Query(default=50, ge=1, le=1000),
            offset: int = fastapi.Query(default=0, ge=0),
            entity_type: str | None = fastapi.Query(default=None),
            service_id: str | None = fastapi.Query(default=None),
        ):
            """Paginated entities for a run, filterable by type."""
            from terrarium.core.types import RunId as _RId

            report = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "report",
            )
            entities_by_type = report.get("entities", {}) if report else {}

            all_entities: list[dict] = []
            for etype, elist in entities_by_type.items():
                if entity_type and etype != entity_type:
                    continue
                items = elist if isinstance(elist, list) else [elist]
                for e in items:
                    all_entities.append(
                        {
                            "entity_type": etype,
                            **(e if isinstance(e, dict) else {}),
                        }
                    )

            total = len(all_entities)
            paginated = all_entities[offset : offset + limit]
            return {
                "run_id": run_id,
                "entities": paginated,
                "total": total,
            }

        @app.get("/api/v1/runs/{run_id}/entities/{entity_id}")
        async def get_entity_detail(run_id: str, entity_id: str):
            """Single entity with state change history."""
            from starlette.responses import JSONResponse

            from terrarium.core.types import RunId as _RId

            # Find entity in report
            report = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "report",
            )
            entity = None
            entity_type = None
            if report:
                for etype, elist in report.get("entities", {}).items():
                    items = elist if isinstance(elist, list) else [elist]
                    for e in items:
                        if isinstance(e, dict) and e.get("id") == entity_id:
                            entity = e
                            entity_type = etype
                            break
                    if entity:
                        break

            if entity is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Entity not found: {entity_id}"},
                )

            # Build state history from event log
            events = await _load_run_events(run_id)
            state_history: list[dict] = []
            for ev in events:
                for delta in ev.get("state_deltas", []):
                    if delta.get("entity_id") == entity_id:
                        state_history.append(
                            {
                                "event_id": ev.get("event_id"),
                                "event_type": ev.get("event_type"),
                                "timestamp": ev.get("timestamp"),
                                "operation": delta.get("operation"),
                                "fields": delta.get("fields", {}),
                                "previous_fields": delta.get("previous_fields"),
                            }
                        )

            return {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "current_state": entity,
                "state_history": state_history,
            }

        @app.get("/api/v1/runs/{run_id}/gaps")
        async def get_run_gaps(run_id: str):
            """Capability gap log for a specific run."""
            from terrarium.core.types import RunId as _RId

            report = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "report",
            )
            gaps = report.get("capability_gaps", []) if report else []
            summary = report.get("gap_summary", {}) if report else {}
            return {
                "run_id": run_id,
                "gaps": gaps,
                "summary": summary,
            }

        @app.get("/api/v1/runs/{run_id}/actors/{actor_id}")
        async def get_actor_detail(run_id: str, actor_id: str):
            """Actor detail with definition, scorecard, budget, action history."""
            from starlette.responses import JSONResponse

            from terrarium.core.types import RunId as _RId

            run = await gateway._app.run_manager.get_run(_RId(run_id))
            if run is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Run not found: {run_id}"},
                )

            # Actor definition from world_def
            actors = run.get("world_def", {}).get("actors", [])
            actor_def = next(
                (a for a in actors if a.get("id") == actor_id),
                None,
            )
            if actor_def is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Actor not found: {actor_id}"},
                )

            # Per-actor scorecard
            scorecard = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "scorecard",
            )
            actor_score = {}
            if scorecard:
                actor_score = scorecard.get("per_actor", {}).get(actor_id, {})

            # Action count + last action from event log
            events = await _load_run_events(run_id)
            actor_events = [e for e in events if e.get("actor_id") == actor_id]
            last_event = actor_events[-1] if actor_events else None

            return {
                "actor_id": actor_id,
                "definition": actor_def,
                "scorecard": actor_score,
                "action_count": len(actor_events),
                "last_action_at": (last_event.get("timestamp") if last_event else None),
            }

        @app.get("/api/v1/compare")
        async def compare_runs_endpoint(
            runs: str = fastapi.Query(
                ...,
                description="Comma-separated run IDs or tags",
            ),
        ):
            """Compare multiple runs — alias for /api/v1/diff."""
            from starlette.responses import JSONResponse

            run_ids = [r.strip() for r in runs.split(",")]
            if len(run_ids) < 2:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Need at least 2 run IDs to compare"},
                )
            try:
                return await gateway._app.diff_runs(run_ids)
            except (KeyError, ValueError) as exc:
                return JSONResponse(
                    status_code=400,
                    content={"error": str(exc)},
                )

        @app.websocket("/ws/runs/{run_id}/live")
        async def run_live_stream(
            websocket: WebSocket,
            run_id: str,
        ):
            """Run-scoped WebSocket with 5 message types."""
            await websocket.accept()
            bus = gateway._app.bus
            queue: asyncio.Queue = asyncio.Queue()

            def _classify(event: Any) -> dict:
                """Classify bus event into message type."""
                et = getattr(event, "event_type", "")
                try:
                    data = event.model_dump(mode="json") if hasattr(event, "model_dump") else {}
                except Exception:
                    data = {}
                et_lower = et.lower()
                if "budget" in et_lower:
                    msg_type = "budget_update"
                elif "run_complete" in et_lower or "simulation_end" in et_lower:
                    msg_type = "run_complete"
                elif "entity" in et_lower or "state_mutation" in et_lower:
                    msg_type = "entity_update"
                elif "status" in et_lower:
                    msg_type = "status"
                else:
                    msg_type = "event"
                return {
                    "type": msg_type,
                    "event_type": et,
                    "data": data,
                }

            async def _on_event(event: Any) -> None:
                await queue.put(_classify(event))

            await bus.subscribe("*", _on_event)
            try:
                while True:
                    msg = await queue.get()
                    await websocket.send_json(msg)
            except WebSocketDisconnect:
                logger.debug(
                    "Run WebSocket client disconnected: %s",
                    run_id,
                )
            finally:
                try:
                    await bus.unsubscribe("*", _on_event)
                except Exception:
                    logger.debug("Failed to unsubscribe from event bus")

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

        config = uvicorn.Config(self._app_instance, host=host, port=port, log_level="info")
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
