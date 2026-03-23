"""Runtime-backed HTTP adapter tests using a real TerrariumApp."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.testclient import TestClient

from terrarium.app import TerrariumApp
from terrarium.config.schema import TerrariumConfig
from terrarium.engines.state.config import StateConfig
from terrarium.ledger.query import LedgerQuery
from terrarium.persistence.config import PersistenceConfig
from tests.helpers.guardrails import staged_guardrail
from tests.helpers.runtime import spawn_websocket_receiver, start_http_adapter

pytestmark = [pytest.mark.real_adapter]


def _email_send_payload() -> dict[str, str]:
    return {
        "from_addr": "alice@test.com",
        "to_addr": "bob@test.com",
        "subject": "Hello",
        "body": "World",
    }


@pytest.fixture
async def app(tmp_path):
    """Boot a real TerrariumApp with isolated temporary storage."""
    config = TerrariumConfig().model_copy(
        update={
            "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
            "state": StateConfig(
                db_path=str(tmp_path / "state.db"),
                snapshot_dir=str(tmp_path / "snapshots"),
            ),
        }
    )
    terrarium_app = TerrariumApp(config)
    await terrarium_app.start()
    yield terrarium_app
    await terrarium_app.stop()


@pytest.mark.asyncio
async def test_http_action_route_uses_real_gateway_and_records_ledger(app, monkeypatch):
    adapter = await start_http_adapter(app)

    original_handle_action = app.handle_action
    handle_action_spy = AsyncMock(side_effect=original_handle_action)
    monkeypatch.setattr(app, "handle_action", handle_action_spy)

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/actions/email_send",
            json={"actor_id": "http-agent", "arguments": _email_send_payload()},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    handle_action_spy.assert_awaited_once()

    entries = await app.ledger.query(LedgerQuery(entry_type="gateway_request", limit=20))
    assert any(entry.protocol == "http" and entry.action == "email_send" for entry in entries)


@staged_guardrail(
    reason=(
        "Mounted GET routes still drop query parameters "
        "before reaching Gateway.handle_request"
    )
)
@pytest.mark.asyncio
async def test_http_mounted_get_route_forwards_query_params(app, monkeypatch):
    adapter = await start_http_adapter(app)
    handle_request_spy = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(app.gateway, "handle_request", handle_request_spy)

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/email/v1/messages",
            params={"mailbox_owner": "alice@test.com"},
        )

    assert response.status_code == 200
    call = handle_request_spy.await_args.kwargs
    assert call["tool_name"] == "email_list"
    assert call["arguments"]["mailbox_owner"] == "alice@test.com"


@staged_guardrail(
    reason=(
        "Mounted path-param routes still drop extracted path "
        "variables before reaching Gateway.handle_request"
    )
)
@pytest.mark.asyncio
async def test_http_mounted_path_route_forwards_path_params(app, monkeypatch):
    adapter = await start_http_adapter(app)
    handle_request_spy = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(app.gateway, "handle_request", handle_request_spy)

    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/email/v1/messages/email-123")

    assert response.status_code == 200
    call = handle_request_spy.await_args.kwargs
    assert call["tool_name"] == "email_read"
    assert call["arguments"]["email_id"] == "email-123"


@staged_guardrail(reason="HTTP WebSocket streaming is not yet wired to the real async EventBus")
@pytest.mark.asyncio
async def test_http_websocket_stream_receives_real_world_event(app):
    adapter = await start_http_adapter(app)
    client = TestClient(adapter.fastapi_app)

    with client.websocket_connect("/api/v1/events/stream") as websocket:
        receiver, payload, errors = spawn_websocket_receiver(websocket)

        await app.handle_action(
            actor_id="http-agent",
            service_id="email",
            action="email_send",
            input_data=_email_send_payload(),
        )

        receiver.join(timeout=3)
        assert not receiver.is_alive(), "timed out waiting for websocket event"
        if "exception" in errors:
            raise errors["exception"]

        message = payload["message"]
        assert message["event_type"] == "world.email_send"
