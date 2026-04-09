"""HTTP REST Adapter -- exposes Volnix world tools as REST API endpoints.

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
  GET  /api/v1/runs/{run_id}/actors           -- list actors in a run
  GET  /api/v1/runs/{run_id}/actors/{aid}     -- actor detail with budgets
  GET  /api/v1/runs/{run_id}/messages         -- communication messages (chat view)
  GET  /api/v1/runs/{run_id}/deliverable      -- deliverable artifact
  GET  /api/v1/compare                        -- compare runs
  GET  /api/v1/diff                           -- compare runs (original)
  WS   /ws/runs/{run_id}/live                 -- run-scoped live event stream (+chat_message)

Uses: FastAPI + Uvicorn
Uses: Gateway.handle_request() for all tool calls
"""

import asyncio
import json as _json
import logging
from typing import Any, ClassVar

from volnix.core.types import ToolName
from volnix.engines.adapter.protocols._response import unwrap_single_entity
from volnix.engines.adapter.protocols.base import ProtocolAdapter

logger = logging.getLogger(__name__)

# Communication actions across all packs — used by the messages
# endpoint and WebSocket chat_message enrichment.
COMMUNICATION_ACTIONS: frozenset[str] = frozenset(
    {
        # Slack / chat pack (Slack MCP naming convention)
        "chat.postMessage",
        "chat.replyToThread",
        # Email pack (gmail)
        "email_send",
        # Reddit pack
        "submit",
        "comment",
        # Twitter pack
        "create_tweet",
        "reply",
    }
)


class HTTPRestAdapter(ProtocolAdapter):
    """Exposes Volnix world as a REST API."""

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
            title="Volnix World API",
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

        # API surface middleware (Phase E2b)
        from volnix.middleware.config import MiddlewareConfig

        app_config = getattr(gateway._app, "_config", None)
        if app_config and hasattr(app_config, "middleware"):
            mw_cfg = app_config.middleware
        else:
            mw_cfg = MiddlewareConfig()

        # H1 fix: Starlette middleware is LIFO (last added = first inbound).
        # Order: StatusCode added first → Auth added last → Auth runs first
        # inbound. This ensures auth is checked before processing, and
        # status codes are fixed after processing. CORS (added earlier)
        # runs outermost, so it handles preflight before auth.
        if mw_cfg.status_codes_enabled:
            from volnix.middleware.status_codes import (
                StatusCodeMiddleware,
            )

            app.add_middleware(StatusCodeMiddleware, config=mw_cfg)

        if mw_cfg.auth_enabled:
            from volnix.middleware.auth import AuthMiddleware

            app.add_middleware(AuthMiddleware, config=mw_cfg)

        self._middleware_config = mw_cfg

        @app.get("/api/v1/tools")
        async def list_tools(
            actor_id: str = fastapi.Query(default="http-agent"),
            format: str = fastapi.Query(
                default="mcp",
                description="Tool format: mcp, http, openai, anthropic",
            ),
        ):
            """List all tools available in this world."""
            return await gateway.get_tool_manifest(
                actor_id=actor_id,
                protocol=format,
            )

        @app.post("/api/v1/actions/{tool_name}")
        async def call_tool(tool_name: str, request: StarletteRequest):
            """Execute a tool call through the full pipeline.

            Accepts two request body formats (auto-detected):
              Wrapped (Volnix SDK):  {"actor_id": "...", "arguments": {...}}
              Raw (standard transport): {...tool arguments directly...}

            Raw-mode requests receive an envelope response:
              {"structured_content": {...}, "content": "...", "is_error": bool}
            """
            try:
                body = await request.json()
            except Exception:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=422,
                    content={"error": "Malformed JSON in request body"},
                )

            # Resolve agent identity (priority: token > body > header > default)
            auth = request.headers.get("authorization", "")
            token_actor_id = None
            if auth.startswith("Bearer volnix_"):
                token = auth.removeprefix("Bearer ").strip()
                slot_mgr = getattr(gateway, "_slot_manager", None)
                if slot_mgr:
                    resolved = slot_mgr.resolve_token(token)
                    if resolved:
                        token_actor_id = str(resolved)
                    else:
                        from starlette.responses import JSONResponse as _JR401

                        return _JR401(
                            status_code=401,
                            content={"error": "Invalid or expired agent token"},
                        )

            # Detect format: wrapped (SDK) vs raw (standard tool transport)
            if "arguments" in body:
                if isinstance(body["arguments"], dict):
                    actor_id = token_actor_id or body.get("actor_id", "http-agent")
                    arguments = body["arguments"]
                    raw_mode = False
                else:
                    from starlette.responses import JSONResponse as _JR

                    return _JR(
                        status_code=422,
                        content={"error": "arguments must be a dict"},
                    )
            else:
                actor_id = (
                    token_actor_id or request.headers.get("x-actor-id", "").strip() or "http-agent"
                )
                arguments = body
                raw_mode = True

            result = await gateway.handle_request(
                actor_id=actor_id,
                tool_name=tool_name,
                input_data=arguments,
            )

            # Strip internal _event field from responses to external agents
            if isinstance(result, dict):
                result.pop("_event", None)

            if raw_mode:
                if isinstance(result, dict):
                    is_error = "error" in result and result.get("error") is not None
                    unwrapped = unwrap_single_entity(result)
                else:
                    is_error = result is None
                    unwrapped = result
                return {
                    "structured_content": unwrapped,
                    "is_error": is_error,
                }
            return result

        # ── Agent slot management ──────────────────────────────

        @app.get("/api/v1/agents/slots")
        async def list_agent_slots():
            """Discover available actor slots for external agents."""
            slot_mgr = getattr(gateway, "_slot_manager", None)
            if not slot_mgr:
                return {"slots": [], "total": 0, "available": 0}
            slots = slot_mgr.discover_slots()
            return {
                "slots": [s.model_dump() for s in slots],
                "total": len(slots),
                "available": sum(1 for s in slots if s.status == "available"),
            }

        @app.post("/api/v1/agents/register")
        async def register_agent(request: StarletteRequest):
            """Claim an actor slot and receive an agent token.

            Request body:
              {"actor_id": "analyst-abc123", "agent_name": "my-agent"}
              OR {"agent_name": "my-agent", "role_hint": "analyst"}  (auto-assign)
            """
            slot_mgr = getattr(gateway, "_slot_manager", None)
            if not slot_mgr:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=503, content={"error": "Slot manager not initialized"}
                )

            body = await request.json()
            agent_name = body.get("agent_name", "unnamed-agent")
            actor_id = body.get("actor_id")

            if actor_id:
                from volnix.core.types import ActorId as _AId

                reg = slot_mgr.register(_AId(actor_id), agent_name)
            else:
                role_hint = body.get("role_hint")
                reg = slot_mgr.auto_assign(agent_name, role_hint)

            if reg is None:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=409,
                    content={"error": "No available slot or slot already claimed"},
                )
            return reg.model_dump()

        @app.delete("/api/v1/agents/{token}")
        async def release_agent(token: str):
            """Release an actor slot."""
            slot_mgr = getattr(gateway, "_slot_manager", None)
            if not slot_mgr:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=503, content={"error": "Slot manager not initialized"}
                )
            actor_id = slot_mgr.release(token)
            if actor_id is None:
                from starlette.responses import JSONResponse

                return JSONResponse(status_code=404, content={"error": "Token not found"})
            return {"status": "released", "actor_id": str(actor_id)}

        @app.get("/api/v1/agents/whoami")
        async def whoami(request: StarletteRequest):
            """Verify an agent token and return identity."""
            slot_mgr = getattr(gateway, "_slot_manager", None)
            if not slot_mgr:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=503, content={"error": "Slot manager not initialized"}
                )
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer volnix_"):
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=401, content={"error": "Missing or invalid Authorization header"}
                )
            token = auth.removeprefix("Bearer ").strip()
            actor_id = slot_mgr.resolve_token(token)
            if actor_id is None:
                from starlette.responses import JSONResponse

                return JSONResponse(status_code=401, content={"error": "Invalid or expired token"})
            return {
                "actor_id": str(actor_id),
                "agent_name": slot_mgr.get_agent_name(token),
            }

        @app.get("/api/v1/health")
        async def health():
            return {"status": "ok"}

        @app.get("/api/v1/agent-profile")
        async def agent_profile(
            capabilities: str = fastapi.Query(
                default="",
                description="Comma-separated semantic capabilities to map",
            ),
        ):
            """Return target mapping from capabilities to this world's tools.

            External agents call this to discover which tool name to use
            for each semantic capability (e.g., cases.list → tickets.list).
            """
            from volnix.kernel.mapping import generate_target_mapping

            tools = await gateway.get_tool_manifest(protocol="mcp")
            caps = [c.strip() for c in capabilities.split(",") if c.strip()]
            mapping = generate_target_mapping(caps, tools)
            return {
                "target_mapping": mapping,
                "available_tools": [t.get("name", "") for t in tools],
            }

        @app.get("/api/v1/entities/{entity_type}")
        async def query_entities(
            entity_type: str,
            actor_id: str = fastapi.Query(default="http-agent"),
        ):
            """Query entities via app layer (Fix #9).

            State reads go through app.query_entities() — not
            directly to the state engine or through the tool pipeline.
            """
            return await gateway._app.read_entities(actor_id, entity_type)

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

        # -- Webhook endpoints -------------------------------------------------

        webhook_mgr = getattr(gateway._app, "_webhook_manager", None)

        def _check_webhook_auth(request: StarletteRequest) -> bool:
            """C3: Check admin token if configured."""
            if webhook_mgr and webhook_mgr._config.admin_token:
                auth = request.headers.get("authorization", "")
                expected = f"Bearer {webhook_mgr._config.admin_token}"
                return auth == expected
            return True  # No token = open access

        @app.post("/api/v1/webhooks")
        async def register_webhook(request: StarletteRequest):
            """Register a webhook subscription."""
            from starlette.responses import JSONResponse

            # M6: 503 when disabled
            if webhook_mgr is None:
                return JSONResponse(
                    status_code=503,
                    content={"error": "Webhooks not enabled"},
                )
            # C3: admin auth
            if not _check_webhook_auth(request):
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized"},
                )
            # H5: malformed JSON
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=422,
                    content={"error": "Invalid JSON body"},
                )
            try:
                sub_id = webhook_mgr.register(
                    url=body.get("url", ""),
                    events=body.get("events", ["world.*"]),
                    service=body.get("service", ""),
                    secret=body.get("secret", ""),
                )
                return {"id": sub_id, "status": "registered"}
            except ValueError as exc:
                return JSONResponse(
                    status_code=400,
                    content={"error": str(exc)},
                )

        @app.delete("/api/v1/webhooks/{webhook_id}")
        async def unregister_webhook(webhook_id: str, request: StarletteRequest):
            """Remove a webhook subscription."""
            from starlette.responses import JSONResponse

            if webhook_mgr is None:
                return JSONResponse(
                    status_code=503,
                    content={"error": "Webhooks not enabled"},
                )
            if not _check_webhook_auth(request):
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized"},
                )
            removed = webhook_mgr.unregister(webhook_id)
            if removed:
                return {"status": "removed"}
            return JSONResponse(
                status_code=404,
                content={"error": "Webhook not found"},
            )

        @app.get("/api/v1/webhooks")
        async def list_webhooks():
            """List all registered webhooks."""
            if webhook_mgr is None:
                return {"webhooks": [], "enabled": False}
            return {
                "webhooks": webhook_mgr.list_webhooks(),
                "enabled": True,
            }

        @app.get("/api/v1/webhooks/stats")
        async def webhook_stats():
            """Webhook delivery statistics."""
            if webhook_mgr is None:
                return {"enabled": False}
            return webhook_mgr.get_stats()

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
            from volnix.core.types import EventId as EId

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
                "world_id",
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
            world_id: str | None = fastapi.Query(default=None),
        ):
            """List runs, newest first. Supports pagination and filtering."""
            runs = await gateway._app.run_manager.list_runs(world_id=world_id)
            if status:
                runs = [r for r in runs if r.get("status") == status]
            if preset:
                runs = [r for r in runs if r.get("reality_preset") == preset]
            if tag:
                runs = [r for r in runs if r.get("tag") == tag]

            # Enrich each run with live stats from bus (raw JSON)
            try:
                bus = gateway._app.bus
                persistence = getattr(bus, "_persistence", None)
                for r in runs:
                    rid = r.get("run_id", "")
                    run_events = []
                    if persistence:
                        rows = await persistence._log.query(
                            from_sequence=0,
                            filters={"run_id": rid},
                        )
                        for row in rows:
                            try:
                                run_events.append(_json.loads(row["payload"]))
                            except Exception:
                                pass
                    r["event_count"] = len(run_events)
                    r["actor_count"] = len(
                        {
                            e.get("actor_id", "")
                            for e in run_events
                            if e.get("actor_id", "")
                            and e.get("actor_id", "") not in _INTERNAL_ACTORS
                        }
                    )
                    world_def = r.get("world_def", {})
                    services_raw = world_def.get("services", {})
                    if isinstance(services_raw, dict) and "services" not in r:
                        r["services"] = [
                            {"service_id": k, "service_name": k} for k in services_raw.keys()
                        ]
            except Exception:
                pass

            total = len(runs)
            paginated = runs[offset : offset + limit]
            return {"runs": paginated, "total": total}

        # ── World endpoints ────────────────────────────────────

        @app.get("/api/v1/worlds")
        async def list_worlds_endpoint(
            limit: int = fastapi.Query(default=50, ge=1, le=1000),
        ):
            """List all created worlds, newest first."""
            worlds = await gateway._app.world_manager.list_worlds(limit=limit)
            return {"worlds": worlds, "total": len(worlds)}

        @app.get("/api/v1/worlds/{world_id}")
        async def get_world_endpoint(world_id: str):
            """Get metadata for a specific world."""
            from volnix.core.types import WorldId as _WId

            world = await gateway._app.world_manager.get_world(_WId(world_id))
            if not world:
                return fastapi.responses.JSONResponse(
                    status_code=404,
                    content={"error": f"World '{world_id}' not found"},
                )
            return world

        @app.get("/api/v1/worlds/{world_id}/runs")
        async def list_world_runs_endpoint(world_id: str):
            """List all runs that used this world."""
            runs = await gateway._app.run_manager.list_runs(world_id=world_id)
            return {"runs": runs, "total": len(runs)}

        # ── Run endpoints ──────────────────────────────────────

        _INTERNAL_ACTORS = frozenset(
            {
                "world_compiler",
                "animator",
                "system",
                "policy",
                "budget",
                "state",
                "permission",
                "responder",
            }
        )

        @app.get("/api/v1/runs/{run_id}")
        async def get_run_endpoint(run_id: str):
            """Get metadata for a specific run, enriched with live stats."""
            from volnix.core.types import RunId as _RId

            result = await gateway._app.run_manager.get_run(_RId(run_id))
            if result is None:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=404,
                    content={"error": f"Run not found: {run_id}"},
                )

            # Enrich with live stats from bus (filtered by run_id)
            try:
                bus = gateway._app.bus
                persistence = getattr(bus, "_persistence", None)
                run_events = []
                if persistence:
                    rows = await persistence._log.query(
                        from_sequence=0,
                        filters={"run_id": run_id},
                    )
                    for row in rows:
                        try:
                            run_events.append(_json.loads(row["payload"]))
                        except Exception:
                            pass

                # Actor count: distinct external actor_ids
                external_actors = {
                    e.get("actor_id", "")
                    for e in run_events
                    if e.get("actor_id", "") and e.get("actor_id", "") not in _INTERNAL_ACTORS
                }
                result["actor_count"] = len(external_actors)
                result["event_count"] = len(run_events)

                # Current tick
                if run_events:
                    result["current_tick"] = max(
                        (e.get("timestamp", {}).get("tick", 0) for e in run_events),
                        default=0,
                    )

                # Services from world_def
                world_def = result.get("world_def", {})
                services_raw = world_def.get("services", {})
                if isinstance(services_raw, dict):
                    result["services"] = [
                        {"service_id": k, "service_name": k} for k in services_raw.keys()
                    ]
                # Promote summary fields to top level for frontend
                summary = result.get("summary", {})
                if summary:
                    if summary.get("governance_score") is not None:
                        result["governance_score"] = summary["governance_score"]
                    if summary.get("event_count") and not result.get("event_count"):
                        result["event_count"] = summary["event_count"]
                    if summary.get("actor_count") and not result.get("actor_count"):
                        result["actor_count"] = summary["actor_count"]

            except Exception:
                pass  # Stats are best-effort; don't break the endpoint

            return result

        @app.post("/api/v1/runs/{run_id}/complete")
        async def complete_run_endpoint(run_id: str):
            """Complete a run and save artifacts."""
            from starlette.responses import JSONResponse

            from volnix.core.types import RunId as _RId

            try:
                return await gateway._app.end_run(_RId(run_id))
            except (KeyError, ValueError) as exc:
                return JSONResponse(
                    status_code=400,
                    content={"error": str(exc)},
                )

        @app.post("/api/v1/runs/new")
        async def new_run_endpoint(request: StarletteRequest):
            """Start a new run on a world.

            If there is an active run, it is completed first (scorecard
            generated). Then a fresh run is created.

            Body (optional): ``{"world_id": "world_abc"}``
            If no world_id provided, uses the current server world.
            """
            from starlette.responses import JSONResponse

            from volnix.core.types import RunId as _NRId
            from volnix.core.types import WorldId as _NWId

            # Parse optional body
            try:
                body = await request.json()
            except Exception:
                body = {}

            # Complete current run if active
            current = gateway._app._current_run_id
            if current:
                try:
                    await gateway._app.end_run(_NRId(current))
                except (KeyError, ValueError):
                    pass  # Already completed

            # Resolve world: body > current server world
            world_id = body.get("world_id") or gateway._app._current_world_id
            if not world_id:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "No world specified. Provide world_id or start the server with a world."
                    },
                )

            plan = await gateway._app._world_manager.load_plan(_NWId(world_id))
            if plan is None:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"World {world_id} not found"},
                )

            run_id = await gateway._app.create_run(plan, world_id=_NWId(world_id))
            result: dict[str, Any] = {
                "run_id": str(run_id),
                "world_id": world_id,
            }
            if current:
                result["completed_run_id"] = current
            return result

        @app.get("/api/v1/runs/{run_id}/artifacts")
        async def list_artifacts_endpoint(run_id: str):
            """List artifacts saved for a run."""
            from volnix.core.types import RunId as _RId

            return await gateway._app.artifact_store.list_artifacts(_RId(run_id))

        @app.get("/api/v1/runs/{run_id}/artifacts/{artifact_type}")
        async def get_artifact_endpoint(run_id: str, artifact_type: str):
            """Load a specific artifact."""
            from volnix.core.types import RunId as _RId

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

        async def _load_run_events(
            run_id: str,
            order: str = "desc",
            limit: int | None = None,
            offset: int = 0,
        ) -> tuple[list[dict], int]:
            """Load events from artifact (completed) or live bus (active).

            Returns (events_page, total_count). Sorting + pagination
            happens at the DB level via SQL ORDER BY.
            """
            from volnix.core.types import RunId as _RId

            # Completed run — read from saved artifact
            saved = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "event_log",
            )
            if saved is not None:
                events = list(saved)  # Copy — never mutate the artifact
                if order == "desc":
                    events.reverse()
                total = len(events)
                page = events[offset : offset + limit] if limit else events[offset:]
                return page, total

            # Active run — read raw JSON payloads from bus persistence.
            # Use DB-level ordering + pagination for efficiency.
            bus = gateway._app.bus
            persistence = getattr(bus, "_persistence", None)
            if persistence is None:
                return [], 0

            # Query with DB-level run_id filter + ORDER BY + LIMIT
            rows = await persistence._log.query(
                from_sequence=0,
                filters={"run_id": run_id},
                order=order,
                limit=limit,
                offset=offset if offset > 0 else None,
            )
            events = []
            for row in rows:
                try:
                    evt = _json.loads(row["payload"])
                    if "actor_id" in evt:
                        events.append(evt)
                except Exception:
                    pass
            # Total count for this run
            total_count = await persistence._log.count(filters={"run_id": run_id})
            return events, total_count

        @app.get("/api/v1/runs/{run_id}/events")
        async def get_run_events(
            run_id: str,
            limit: int = fastapi.Query(default=100, ge=1, le=1000),
            offset: int = fastapi.Query(default=0, ge=0),
            sort: str = fastapi.Query(
                default="desc",
                description="Sort order: desc (newest first) or asc (oldest first)",
            ),
            actor_id: str | None = fastapi.Query(default=None),
            service_id: str | None = fastapi.Query(default=None),
            event_type: str | None = fastapi.Query(default=None),
            outcome: str | None = fastapi.Query(default=None),
        ):
            """Paginated events for a run. Default: newest first."""
            from volnix.core.types import RunId as _RId

            # When filters are active, load all events first, filter, then paginate.
            # Without filters, paginate at load time for efficiency.
            has_filters = any([actor_id, service_id, event_type, outcome])
            events, total = await _load_run_events(
                run_id,
                order=sort,
                limit=None if has_filters else limit,
                offset=0 if has_filters else offset,
            )

            # Enrich: causal_child_ids
            children: dict[str, list[str]] = {}
            for e in events:
                caused_by = e.get("caused_by")
                eid = e.get("event_id", "")
                if caused_by:
                    children.setdefault(caused_by, []).append(eid)
                for cause in e.get("causes", []):
                    children.setdefault(cause, []).append(eid)

            # Enrich: actor_role
            run_data = await gateway._app.run_manager.get_run(_RId(run_id))
            world_def = run_data.get("world_def", {}) if run_data else {}
            actor_roles = {
                a.get("id", ""): a.get("role", "")
                for a in world_def.get("actor_specs", world_def.get("actors", []))
                if isinstance(a, dict)
            }

            events = [
                {
                    **e,
                    "causal_child_ids": children.get(e.get("event_id", ""), []),
                    "actor_role": actor_roles.get(e.get("actor_id", ""), ""),
                }
                for e in events
            ]

            # Apply in-memory filters (on the already-paginated page)
            if actor_id:
                events = [e for e in events if e.get("actor_id") == actor_id]
            if service_id:
                events = [
                    e
                    for e in events
                    if e.get("service_id") == service_id or e.get("target_service") == service_id
                ]
            if event_type:
                events = [
                    e
                    for e in events
                    if e.get("event_type") == event_type
                    or e.get("event_type", "").startswith(event_type + ".")
                ]
            if outcome:
                events = [e for e in events if e.get("outcome") == outcome]
            # If filters were applied, paginate the filtered results
            if has_filters:
                total = len(events)
                events = events[offset : offset + limit]
            return {"run_id": run_id, "events": events, "total": total}

        @app.get("/api/v1/runs/{run_id}/events/{event_id}")
        async def get_event_detail(run_id: str, event_id: str):
            """Single event with full causal chain."""
            from starlette.responses import JSONResponse

            events, _ = await _load_run_events(run_id, order="asc")
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
            from volnix.core.types import RunId as _RId

            scorecard = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "scorecard",
            )
            if scorecard is None:
                # Regenerate from stored event log — NOT the live bus
                # which may have events from a different run.
                reporter = gateway._app.registry.get("reporter")
                if reporter:
                    stored_events = await gateway._app.artifact_store.load_artifact(
                        _RId(run_id), "event_log"
                    )
                    scorecard = await reporter.generate_scorecard(events=stored_events or [])
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
            from volnix.core.types import RunId as _RId

            config = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "config",
            )
            entities_by_type = config.get("entities", {}) if config else {}

            all_entities: list[dict] = []
            for etype, elist in entities_by_type.items():
                if entity_type and etype != entity_type:
                    continue
                items = elist if isinstance(elist, list) else [elist]
                for idx, e in enumerate(items):
                    if not isinstance(e, dict):
                        continue
                    # Config entities are raw service data (e.g. Zendesk
                    # tickets, Gmail messages) keyed by "id".  Wrap them
                    # into the Entity API shape the frontend expects.
                    eid = e.get("id", "") or f"{etype}_{idx}"
                    all_entities.append(
                        {
                            "entity_id": eid,
                            "entity_type": etype,
                            "current_state": e,
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

            from volnix.core.types import RunId as _RId

            # Find entity in compilation config
            config = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "config",
            )
            entity = None
            entity_type = None
            if config:
                for etype, elist in config.get("entities", {}).items():
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
            events, _ = await _load_run_events(run_id, order="asc")
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

        @app.get("/api/v1/runs/{run_id}/deliverable")
        async def get_run_deliverable(run_id: str):
            """Get the deliverable artifact from a completed run."""
            from starlette.responses import JSONResponse

            from volnix.core.types import RunId as _RId

            deliverable = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "deliverable",
            )
            if deliverable is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": "No deliverable produced for this run"},
                )
            return deliverable

        @app.get("/api/v1/runs/{run_id}/governance-report")
        async def get_governance_report(run_id: str):
            """Get the governance report for a Mode 1 agent testing run."""
            from starlette.responses import JSONResponse

            from volnix.core.types import RunId as _RId

            artifact = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "governance_report",
            )
            if artifact is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": "No governance report for this run"},
                )
            return {"run_id": run_id, **artifact}

        @app.get("/api/v1/runs/{run_id}/gaps")
        async def get_run_gaps(run_id: str):
            """Capability gap log for a specific run."""
            from volnix.core.types import RunId as _RId

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

        @app.get("/api/v1/runs/{run_id}/actors")
        async def list_run_actors(run_id: str):
            """List all actors in a run."""
            from starlette.responses import JSONResponse

            from volnix.core.types import RunId as _RId

            run = await gateway._app.run_manager.get_run(_RId(run_id))
            if run is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Run not found: {run_id}"},
                )
            wd = run.get("world_def", {})
            actors = wd.get("actor_specs", wd.get("actors", []))
            return {"run_id": run_id, "actors": actors, "count": len(actors)}

        @app.get("/api/v1/runs/{run_id}/actors/{actor_id}")
        async def get_actor_detail(run_id: str, actor_id: str):
            """Actor detail with definition, scorecard, budget, action history."""
            from starlette.responses import JSONResponse

            from volnix.core.types import RunId as _RId

            run = await gateway._app.run_manager.get_run(_RId(run_id))
            if run is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Run not found: {run_id}"},
                )

            # Actor definition from world_def
            wd = run.get("world_def", {})
            actors = wd.get("actor_specs", wd.get("actors", []))
            actor_def = next(
                (a for a in actors if a.get("id") == actor_id),
                None,
            )
            if actor_def is None:
                # Internal engines (world_compiler, etc.) aren't actors
                # but appear in events — return stub data instead of 404
                actor_def = {
                    "id": actor_id,
                    "role": "system",
                    "type": "internal",
                }

            # Per-actor scorecard
            scorecard = await gateway._app.artifact_store.load_artifact(
                _RId(run_id),
                "scorecard",
            )
            actor_score = {}
            if scorecard:
                actor_score = scorecard.get("per_actor", {}).get(actor_id, {})

            # Action count + last action from event log
            events, _ = await _load_run_events(run_id, order="asc")
            actor_events = [e for e in events if e.get("actor_id") == actor_id]
            last_event = actor_events[-1] if actor_events else None

            # Get budget from budget engine
            budget_data = {}
            try:
                budget_eng = gateway._app.registry.get("budget")
                if budget_eng:
                    from volnix.core.types import ActorId as _AId

                    budget_state = await budget_eng.get_remaining(_AId(actor_id))
                    if budget_state and hasattr(budget_state, "model_dump"):
                        budget_data = budget_state.model_dump(mode="json")
            except Exception:
                pass

            return {
                "actor_id": actor_id,
                "definition": actor_def,
                "scorecard": actor_score,
                "action_count": len(actor_events),
                "last_action_at": (last_event.get("timestamp") if last_event else None),
                "budget": budget_data,
            }

        # -- Collaborative communication endpoints ----------------------------

        @app.get("/api/v1/runs/{run_id}/messages")
        async def get_run_messages(
            run_id: str,
            channel: str | None = fastapi.Query(default=None),
            limit: int = fastapi.Query(default=50, ge=1, le=1000),
            offset: int = fastapi.Query(default=0, ge=0),
        ):
            """Get communication messages from a run, formatted for chat view.

            Filters events to communication actions (chat, email, social)
            and returns them as chat-style messages.
            """
            from volnix.core.types import RunId as _RId

            # Load all events for the run (ascending order for chat timeline)
            events, total_all = await _load_run_events(
                run_id,
                order="asc",
            )

            # Filter to communication actions only
            comm_events = [e for e in events if e.get("action") in COMMUNICATION_ACTIONS]

            # Apply channel filter if provided
            if channel:
                comm_events = [
                    e for e in comm_events if (e.get("input_data") or {}).get("channel") == channel
                ]

            total = len(comm_events)
            page = comm_events[offset : offset + limit]

            # Build actor role lookup from world_def
            run_data = await gateway._app.run_manager.get_run(_RId(run_id))
            world_def = run_data.get("world_def", {}) if run_data else {}
            actor_roles = {
                a.get("id", ""): a.get("role", "")
                for a in world_def.get("actor_specs", world_def.get("actors", []))
                if isinstance(a, dict)
            }

            messages = []
            for evt in page:
                inp = evt.get("input_data") or {}
                ts = evt.get("timestamp") or {}
                content = inp.get("content") or inp.get("text") or inp.get("body") or ""
                messages.append(
                    {
                        "id": evt.get("event_id", ""),
                        "tick": ts.get("tick", 0),
                        "actor_id": evt.get("actor_id", ""),
                        "actor_role": actor_roles.get(evt.get("actor_id", ""), ""),
                        "channel": inp.get("channel", ""),
                        "content": content,
                        "reply_to": inp.get("reply_to_event_id"),
                        "intended_for": inp.get("intended_for", []),
                        "timestamp": ts.get("wall_time", ""),
                    }
                )

            return {"messages": messages, "count": total}

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

            def _classify(event: Any) -> dict | None:
                """Classify bus event for WebSocket delivery.

                Returns None for events that should not be forwarded to the client
                (e.g., engine lifecycle, pipeline steps). Only world action events
                appear in the event feed to avoid duplicates and phantom entries.
                """
                try:
                    data = event.model_dump(mode="json") if hasattr(event, "model_dump") else {}
                except Exception:
                    logger.warning("Event serialization failed: %s", type(event).__name__)
                    data = {}

                event_type = getattr(event, "event_type", "")

                # Budget events
                if event_type.startswith("budget."):
                    return {"type": "budget_update", "data": data}

                # Simulation lifecycle
                if event_type.startswith("simulation."):
                    status = getattr(event, "status", "")
                    if status == "completed":
                        return {"type": "run_complete", "data": data}
                    return {"type": "status", "data": data}

                # Policy governance events
                if event_type.startswith("policy."):
                    return {"type": "policy", "data": data}

                # Permission events
                if event_type.startswith("permission."):
                    return {"type": "permission", "data": data}

                # Capability gap events
                if event_type.startswith("capability."):
                    return {"type": "capability", "data": data}

                # World action events (tool calls from agents)
                if event_type.startswith("world."):
                    return {"type": "event", "data": data}

                # Animator events
                if event_type.startswith("animator."):
                    return {"type": "event", "data": data}

                # Game lifecycle events
                if event_type.startswith("game."):
                    return {"type": "game", "data": data}

                # Skip engine lifecycle, pipeline steps, etc.
                return None

            def _make_chat_message(event: Any) -> dict | None:
                """Build a chat_message payload if the event is a communication action."""
                action = getattr(event, "action", None)
                if action not in COMMUNICATION_ACTIONS:
                    return None
                inp = getattr(event, "input_data", {}) or {}
                ts = getattr(event, "timestamp", None)
                content = inp.get("content") or inp.get("text") or inp.get("body") or ""
                return {
                    "type": "chat_message",
                    "data": {
                        "id": str(getattr(event, "event_id", "")),
                        "tick": ts.tick if ts and hasattr(ts, "tick") else 0,
                        "actor_id": str(getattr(event, "actor_id", "")),
                        "channel": inp.get("channel", ""),
                        "content": content,
                        "reply_to": inp.get("reply_to_event_id"),
                        "intended_for": inp.get("intended_for", []),
                    },
                }

            async def _on_event(event: Any) -> None:
                # Run-scoped: only forward events for this run
                event_run = getattr(event, "run_id", None)
                if event_run is not None and str(event_run) != run_id:
                    return
                classified = _classify(event)
                if classified is None:
                    return  # skip non-world events
                await queue.put(classified)
                # Also emit a chat_message for communication actions
                chat_msg = _make_chat_message(event)
                if chat_msg is not None:
                    await queue.put(chat_msg)

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

        # -- Hold approval queue endpoints ----------------------------------------

        @app.get("/api/v1/holds")
        async def list_holds(
            approver_role: str | None = fastapi.Query(default=None),
            run_id: str | None = fastapi.Query(default=None),
        ):
            """List pending holds awaiting approval."""
            holds = await gateway._app.list_holds(approver_role=approver_role, run_id=run_id)
            return {"holds": holds, "total": len(holds)}

        @app.get("/api/v1/holds/{hold_id}")
        async def get_hold(hold_id: str):
            """Get details of a specific hold."""
            from starlette.responses import JSONResponse

            hold = await gateway._app.get_hold(hold_id)
            if hold is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Hold '{hold_id}' not found"},
                )
            return hold

        @app.post("/api/v1/holds/{hold_id}/approve")
        async def approve_hold(hold_id: str, request: StarletteRequest):
            """Approve a held action and re-execute it through the pipeline."""
            from starlette.responses import JSONResponse

            try:
                body = await request.json()
            except Exception:
                body = {}
            approver = body.get("approver", "http-approver")
            reason = body.get("reason", "")
            result = await gateway._app.resolve_hold(
                hold_id=hold_id,
                approved=True,
                approver=approver,
                reason=reason,
            )
            if "error" in result:
                return JSONResponse(status_code=404, content=result)
            return result

        @app.post("/api/v1/holds/{hold_id}/reject")
        async def reject_hold(hold_id: str, request: StarletteRequest):
            """Reject a held action."""
            from starlette.responses import JSONResponse

            try:
                body = await request.json()
            except Exception:
                body = {}
            approver = body.get("approver", "http-approver")
            reason = body.get("reason", "")
            result = await gateway._app.resolve_hold(
                hold_id=hold_id,
                approved=False,
                approver=approver,
                reason=reason,
            )
            if "error" in result:
                return JSONResponse(status_code=404, content=result)
            return result

        # Mount real-world API paths from pack http_path definitions
        await self._mount_pack_routes(app, gateway)

        # Mount service-prefixed URL aliases (Phase E2b)
        if mw_cfg.prefixes_enabled and mw_cfg.service_prefixes:
            from volnix.middleware.prefix_router import (
                mount_service_prefixes,
            )

            routes = await gateway.get_tool_manifest(protocol="http")
            mount_service_prefixes(app, routes, mw_cfg.service_prefixes, gateway)

        # G6: Mount MCP SSE/HTTP endpoint for remote MCP clients
        # (Claude Desktop, Cursor, Windsurf, LangGraph MCP adapters)
        await self._mount_mcp_endpoint(app, gateway)

        # Mount dashboard frontend (MUST be last — catches all unmatched routes)
        self._mount_dashboard(app)

        self._app_instance = app
        logger.info("HTTP REST adapter created")

    def _mount_dashboard(self, app: Any) -> None:
        """Mount dashboard static files from ``dashboard.static_dir`` config."""
        from pathlib import Path

        app_config = getattr(self._gateway, "_app", None)
        dashboard_cfg = getattr(getattr(app_config, "_config", None), "dashboard", None)
        static_dir = getattr(dashboard_cfg, "static_dir", "") if dashboard_cfg else ""
        if not static_dir:
            return

        dist = Path(static_dir)
        if not dist.is_dir():
            logger.debug("Dashboard dir not found: %s", dist)
            return

        from starlette.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
        logger.info("Dashboard frontend mounted from %s", dist)

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
                            from starlette.responses import JSONResponse

                            return JSONResponse(
                                status_code=422,
                                content={"error": "Malformed JSON in request body"},
                            )
                        # Path params override body values
                        arguments.update(path_params)
                    # Actor ID from header only (never from body — prevents impersonation)
                    actor_id = request.headers.get("x-actor-id", "").strip() or "http-agent"
                    return await gateway.handle_request(
                        actor_id=actor_id,
                        tool_name=tn,
                        input_data=arguments,
                    )

                return handler

            if method == "POST":
                app.post(path)(make_handler(tool_name, "POST"))
            elif method == "GET":
                app.get(path)(make_handler(tool_name, "GET"))

    async def _mount_mcp_endpoint(self, app: Any, gateway: Any) -> None:
        """Mount MCP SSE/HTTP endpoint for remote MCP clients.

        Uses the MCP SDK's StreamableHTTPSessionManager as a raw ASGI
        app mounted at /mcp. This avoids double-response issues (C4)
        and private attribute access (C5).

        The session manager's run() is started via FastAPI lifespan (C1).
        """
        mcp_adapter = gateway._adapters.get("mcp")
        if mcp_adapter is None or mcp_adapter._server is None:
            logger.debug("No MCP adapter available — skipping /mcp endpoint")
            return

        try:
            from mcp.server.streamable_http_manager import (
                StreamableHTTPSessionManager,
            )

            session_manager = StreamableHTTPSessionManager(
                app=mcp_adapter._server,
                stateless=True,
            )
            self._mcp_session_manager = session_manager

            # C1 fix: start session manager via app lifespan
            original_lifespan = getattr(app, "router", app).lifespan_context

            import contextlib

            @contextlib.asynccontextmanager
            async def lifespan_with_mcp(a: Any):
                async with session_manager.run():
                    if original_lifespan:
                        async with original_lifespan(a):
                            yield
                    else:
                        yield

            app.router.lifespan_context = lifespan_with_mcp

            # C4+C5 fix: mount as raw ASGI app (no double response,
            # no request._send)
            app.mount("/mcp", app=session_manager.handle_request)

            logger.info("MCP SSE endpoint mounted at /mcp")
        except ImportError:
            logger.debug("MCP StreamableHTTP not available — skipping /mcp endpoint")
        except Exception as exc:
            logger.warning("Failed to mount MCP SSE endpoint: %s", exc)

    async def run_server(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Run the FastAPI server (blocking)."""
        import uvicorn

        config = uvicorn.Config(self._app_instance, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    async def stop_server(self) -> None:
        """Stop the HTTP server."""
        self._app_instance = None

    async def translate_inbound(
        self,
        tool_name: ToolName,
        raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate inbound request. FastAPI handles parsing; this is a pass-through."""
        return raw_input

    async def translate_outbound(
        self,
        tool_name: ToolName,
        internal_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate outbound response. FastAPI handles serialization; pass-through."""
        return internal_response

    async def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return tool manifest for the HTTP protocol."""
        return await self._gateway.get_tool_manifest(protocol="http")

    @property
    def fastapi_app(self) -> Any:
        """Access the underlying FastAPI app instance (for testing)."""
        return self._app_instance
