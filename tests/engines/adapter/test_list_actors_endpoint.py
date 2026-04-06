"""Tests for the list-actors endpoint.

Validates GET /api/v1/runs/{run_id}/actors returns correct actor data,
handles missing runs with 404, and returns empty lists properly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def _make_gateway(run_data):
    """Build a mock gateway that returns the given run data."""
    gateway = MagicMock()
    gateway._app = MagicMock()
    gateway._app.run_manager = AsyncMock()
    gateway._app.run_manager.get_run = AsyncMock(return_value=run_data)
    gateway._app.artifact_store = AsyncMock()
    gateway._app.artifact_store.load_artifact = AsyncMock(return_value=None)
    gateway._app.registry = MagicMock()
    gateway._app.registry.get = MagicMock(return_value=None)
    gateway._app.bus = MagicMock()
    gateway._app.bus.subscribe = AsyncMock()
    gateway.get_tool_manifest = AsyncMock(return_value=[])
    return gateway


async def test_list_actors_returns_actors():
    """GET /runs/{id}/actors should return actors from world_def."""
    from volnix.engines.adapter.protocols.http_rest import HTTPRestAdapter

    run_data = {
        "run_id": "run-1",
        "status": "completed",
        "world_def": {
            "actors": [
                {"id": "agent-1", "role": "support", "type": "agent"},
                {"id": "agent-2", "role": "manager", "type": "agent"},
            ],
        },
    }
    gateway = _make_gateway(run_data)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)

    response = client.get("/api/v1/runs/run-1/actors")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["actors"]) == 2
    assert data["actors"][0]["id"] == "agent-1"
    assert data["actors"][1]["id"] == "agent-2"
    assert data["run_id"] == "run-1"


async def test_list_actors_missing_run():
    """GET /runs/{id}/actors with missing run -> 404."""
    from volnix.engines.adapter.protocols.http_rest import HTTPRestAdapter

    gateway = _make_gateway(None)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)

    response = client.get("/api/v1/runs/nonexistent/actors")
    assert response.status_code == 404


async def test_list_actors_no_actors():
    """GET /runs/{id}/actors with no actors -> empty list."""
    from volnix.engines.adapter.protocols.http_rest import HTTPRestAdapter

    run_data = {
        "run_id": "run-1",
        "status": "completed",
        "world_def": {"actors": []},
    }
    gateway = _make_gateway(run_data)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)

    response = client.get("/api/v1/runs/run-1/actors")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["actors"] == []


async def test_list_actors_preserves_actor_fields():
    """All actor definition fields should be preserved in the response."""
    from volnix.engines.adapter.protocols.http_rest import HTTPRestAdapter

    run_data = {
        "run_id": "run-2",
        "world_def": {
            "actors": [
                {"id": "agent-x", "role": "analyst", "type": "agent", "budget": {"api_calls": 100}},
            ],
        },
    }
    gateway = _make_gateway(run_data)
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)

    response = client.get("/api/v1/runs/run-2/actors")
    assert response.status_code == 200
    data = response.json()
    actor = data["actors"][0]
    assert actor["role"] == "analyst"
    assert actor["budget"]["api_calls"] == 100
