"""Tests for terrarium.engines.adapter.protocols.http_rest -- HTTP/REST endpoints.

Tests use REAL httpx.AsyncClient with ASGITransport against the FastAPI app.
No server is started -- httpx connects directly to the ASGI app.
"""
import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from starlette.testclient import TestClient

from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter


def _make_mock_gateway(tools=None, handle_result=None, entity_result=None):
    """Create a mock Gateway for testing HTTP adapter."""
    from terrarium.core.context import StepResult
    from terrarium.core.types import StepVerdict

    gateway = MagicMock()

    http_tools = tools or [
        {"method": "POST", "path": "/email/v1/messages/send",
         "content_type": "application/json", "tool_name": "email_send"},
    ]
    gateway.get_tool_manifest = AsyncMock(return_value=http_tools)

    result = handle_result or {"email_id": "email-abc123", "status": "sent"}
    gateway.handle_request = AsyncMock(return_value=result)

    # Mock app for entity queries
    state = AsyncMock()
    state.query_entities = AsyncMock(return_value=entity_result or [])

    # Mock permission engine that always allows
    permission_engine = AsyncMock()
    permission_engine.execute = AsyncMock(return_value=StepResult(
        step_name="permission", verdict=StepVerdict.ALLOW,
    ))

    registry = MagicMock()
    def _registry_get(name):
        if name == "permission":
            return permission_engine
        return state
    registry.get = MagicMock(side_effect=_registry_get)

    bus = MagicMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()

    mock_app = MagicMock()
    mock_app.registry = registry
    mock_app.bus = bus
    gateway._app = mock_app

    return gateway


@pytest.mark.asyncio
async def test_http_adapter_creates_fastapi_app():
    """start_server() creates a FastAPI app instance."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    assert adapter.fastapi_app is not None


@pytest.mark.asyncio
async def test_http_health_endpoint():
    """GET /api/v1/health returns status ok."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_http_list_tools():
    """GET /api/v1/tools returns tool manifest."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/tools")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    gateway.get_tool_manifest.assert_awaited()


@pytest.mark.asyncio
async def test_http_call_tool():
    """POST /api/v1/actions/{tool_name} executes via gateway."""
    expected = {"email_id": "email-abc123", "status": "sent"}
    gateway = _make_mock_gateway(handle_result=expected)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/actions/email_send",
            json={
                "actor_id": "http-agent",
                "arguments": {
                    "from_addr": "a@b.com",
                    "to_addr": "c@d.com",
                    "subject": "test",
                    "body": "hello",
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json() == expected
    gateway.handle_request.assert_awaited_once()
    call_kwargs = gateway.handle_request.call_args.kwargs
    assert call_kwargs["protocol"] == "http"
    assert call_kwargs["tool_name"] == "email_send"


@pytest.mark.asyncio
async def test_http_call_tool_capability_gap():
    """POST to unknown tool returns capability_gap response from gateway."""
    gap_response = {
        "status": "capability_not_available",
        "message": "Tool 'nonexistent' is not available in this world.",
        "available_tools": ["email_send"],
    }
    gateway = _make_mock_gateway(handle_result=gap_response)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/actions/nonexistent",
            json={"arguments": {}},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "capability_not_available"


@pytest.mark.asyncio
async def test_http_query_entities():
    """GET /api/v1/entities/{type} queries state engine."""
    entities = [{"email_id": "e1", "status": "sent"}]
    gateway = _make_mock_gateway(entity_result=entities)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/entities/email")

    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "email"
    assert data["count"] == 1
    assert data["entities"] == entities


@pytest.mark.asyncio
async def test_http_stop_server():
    """stop_server() clears the FastAPI app."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()
    assert adapter.fastapi_app is not None

    await adapter.stop_server()
    assert adapter.fastapi_app is None


@pytest.mark.asyncio
async def test_http_translate_passthrough():
    """translate_inbound/outbound are no-ops (FastAPI handles it)."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    assert adapter.translate_inbound("anything") is None
    assert adapter.translate_outbound("anything") is None


@pytest.mark.asyncio
async def test_http_default_actor_id():
    """Default actor_id in ToolCallRequest is 'http-agent'."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/actions/email_send",
            json={"arguments": {}},
        )

    assert resp.status_code == 200
    call_kwargs = gateway.handle_request.call_args.kwargs
    assert call_kwargs["actor_id"] == "http-agent"


# ── P0-1: WebSocket event streaming tests ─────────────────────────


def _make_event(event_type="world.email_sent", event_id="evt-001"):
    """Create a mock event with model_dump support."""
    event = MagicMock()
    event.event_type = event_type
    event.event_id = event_id
    event.model_dump.return_value = {
        "event_type": event_type,
        "event_id": event_id,
        "data": {"email_id": "email-abc123"},
    }
    return event


@pytest.mark.asyncio
async def test_websocket_event_stream_endpoint_exists():
    """The /api/v1/events/stream WebSocket endpoint is registered on the FastAPI app."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    app = adapter.fastapi_app
    ws_routes = [
        r.path for r in app.routes
        if hasattr(r, "path") and "events/stream" in getattr(r, "path", "")
    ]
    assert "/api/v1/events/stream" in ws_routes


@pytest.mark.asyncio
async def test_websocket_subscribes_to_bus_and_receives_event():
    """WebSocket connects, bus.subscribe is called, and events are delivered as JSON."""
    gateway = _make_mock_gateway()

    # Track the subscriber callback registered by the WebSocket endpoint
    captured_callbacks = []

    async def tracking_subscribe(event_type, callback, **kwargs):
        captured_callbacks.append((event_type, callback))

    gateway._app.bus.subscribe = AsyncMock(side_effect=tracking_subscribe)

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    test_event = _make_event("world.email_sent", "evt-ws-001")

    # Use Starlette's sync TestClient for WebSocket testing
    client = TestClient(adapter.fastapi_app)
    with client.websocket_connect("/api/v1/events/stream") as ws:
        # The subscribe call should have happened during connect
        assert len(captured_callbacks) == 1
        assert captured_callbacks[0][0] == "*"

        # Simulate an event arriving on the bus by calling the registered callback
        on_event = captured_callbacks[0][1]
        # The callback is async and puts events into a queue;
        # we need to run it in the event loop that the endpoint uses.
        # Since TestClient runs in a thread, we push the event directly
        # via the asyncio queue the endpoint created.
        # Instead, just send to the callback -- TestClient bridges async/sync.
        import threading

        async def push_event():
            await on_event(test_event)

        # Run the async callback in a new event loop on a separate thread
        def run_push():
            loop = asyncio.new_event_loop()
            loop.run_until_complete(push_event())
            loop.close()

        t = threading.Thread(target=run_push)
        t.start()
        t.join(timeout=5)

        data = ws.receive_json()
        assert data["event_type"] == "world.email_sent"
        assert data["event_id"] == "evt-ws-001"
        assert "data" in data


@pytest.mark.asyncio
async def test_websocket_event_serialization():
    """Events sent over WebSocket are serialized with event_type, event_id, and data."""
    gateway = _make_mock_gateway()
    captured_callbacks = []

    async def tracking_subscribe(event_type, callback, **kwargs):
        captured_callbacks.append((event_type, callback))

    gateway._app.bus.subscribe = AsyncMock(side_effect=tracking_subscribe)

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    # Event WITHOUT model_dump (falls back to empty dict)
    event_no_model = MagicMock(spec=[])
    event_no_model.event_type = "world.test"
    event_no_model.event_id = "evt-no-model"

    client = TestClient(adapter.fastapi_app)
    with client.websocket_connect("/api/v1/events/stream") as ws:
        on_event = captured_callbacks[0][1]

        import threading

        async def push_event():
            await on_event(event_no_model)

        t = threading.Thread(
            target=lambda: asyncio.new_event_loop().run_until_complete(push_event())
        )
        t.start()
        t.join(timeout=5)

        data = ws.receive_json()
        assert data["event_type"] == "world.test"
        assert data["event_id"] == "evt-no-model"
        # No model_dump -> empty dict
        assert data["data"] == {}


# ── P1-4: Pack route mounting integration test ─────────────────────


@pytest.mark.asyncio
async def test_http_pack_route_mounted():
    """Pack HTTP routes are auto-mounted and callable via their real paths."""
    expected = {"email_id": "email-abc123", "status": "sent"}
    gateway = _make_mock_gateway(
        tools=[
            {
                "method": "POST",
                "path": "/email/v1/messages/send",
                "content_type": "application/json",
                "tool_name": "email_send",
            },
        ],
        handle_result=expected,
    )
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/email/v1/messages/send",
            json={
                "from_addr": "a@b.com",
                "to_addr": "c@d.com",
                "subject": "test",
                "body": "hello",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == expected
    # Verify the gateway.handle_request was called with the correct tool_name
    gateway.handle_request.assert_awaited()
    call_kwargs = gateway.handle_request.call_args.kwargs
    assert call_kwargs["tool_name"] == "email_send"
    assert call_kwargs["protocol"] == "http"


@pytest.mark.asyncio
async def test_http_pack_route_get_mounted():
    """GET pack routes are auto-mounted correctly."""
    expected = {"emails": []}
    gateway = _make_mock_gateway(
        tools=[
            {
                "method": "GET",
                "path": "/email/v1/messages/list",
                "content_type": "application/json",
                "tool_name": "email_list",
            },
        ],
        handle_result=expected,
    )
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/email/v1/messages/list")

    assert resp.status_code == 200
    assert resp.json() == expected


@pytest.mark.asyncio
async def test_http_pack_routes_multiple_packs():
    """Routes from multiple packs are all mounted and callable."""
    gateway = _make_mock_gateway(
        tools=[
            {
                "method": "POST",
                "path": "/email/v1/messages/send",
                "content_type": "application/json",
                "tool_name": "email_send",
            },
            {
                "method": "POST",
                "path": "/calendar/v1/events/create",
                "content_type": "application/json",
                "tool_name": "calendar_create",
            },
        ],
        handle_result={"id": "result-001"},
    )
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp1 = await client.post("/email/v1/messages/send", json={})
        resp2 = await client.post("/calendar/v1/events/create", json={})

    assert resp1.status_code == 200
    assert resp2.status_code == 200


# ── P1-6: Error path tests for HTTP adapter ───────────────────────


@pytest.mark.asyncio
async def test_http_call_tool_malformed_request_no_json_body():
    """POST with non-JSON body returns 422 with structured error."""
    gateway = _make_mock_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/actions/email_send",
            content=b"this is not json",
            headers={"content-type": "application/json"},
        )

    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert "Malformed JSON" in data["error"]
    # Gateway's handle_request should NOT have been called
    gateway.handle_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_call_tool_empty_arguments():
    """POST with empty arguments dict is accepted and forwarded to gateway."""
    expected = {"email_id": "email-empty", "status": "draft"}
    gateway = _make_mock_gateway(handle_result=expected)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/actions/email_send",
            json={"arguments": {}},
        )

    assert resp.status_code == 200
    assert resp.json() == expected
    call_kwargs = gateway.handle_request.call_args.kwargs
    assert call_kwargs["arguments"] == {}


@pytest.mark.asyncio
async def test_http_call_tool_pipeline_error_response():
    """Pipeline returning an error dict is forwarded to the HTTP client."""
    error_result = {"error": "Pipeline short-circuited at step 'validation'", "step": "validation"}
    gateway = _make_mock_gateway(handle_result=error_result)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/actions/email_send",
            json={"arguments": {"from_addr": "a@b.com"}},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data
    assert "validation" in data["error"]
