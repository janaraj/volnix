"""Tests for event enrichment (causal_child_ids, actor_role) in the run events API.

Validates that GET /api/v1/runs/{run_id}/events correctly enriches raw events
with backward causal references and actor role from world_def, and that
original event dicts are not mutated.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_gateway(run_data: dict, events: list[dict]):
    """Build a mock gateway for endpoint testing."""
    gateway = MagicMock()
    gateway._app = MagicMock()
    gateway._app.run_manager = AsyncMock()
    gateway._app.run_manager.get_run = AsyncMock(return_value=run_data)
    gateway._app.artifact_store = AsyncMock()
    gateway._app.artifact_store.load_artifact = AsyncMock(return_value=events)
    gateway._app.registry = MagicMock()
    gateway._app.registry.get = MagicMock(return_value=None)
    gateway._app.bus = MagicMock()
    gateway._app.bus.subscribe = AsyncMock()
    gateway.get_tool_manifest = AsyncMock(return_value=[])
    return gateway


async def test_causal_child_ids_populated():
    """Event A causes B -> A.causal_child_ids should contain B's id."""
    events = [
        {"event_id": "evt-a", "event_type": "world.send", "actor_id": "agent-1",
         "caused_by": None, "causes": []},
        {"event_id": "evt-b", "event_type": "world.reply", "actor_id": "agent-1",
         "caused_by": "evt-a", "causes": []},
    ]
    run_data = {"run_id": "run-1", "world_def": {"actors": []}}
    gateway = _make_gateway(run_data, events)

    from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)
    resp = client.get("/api/v1/runs/run-1/events")
    assert resp.status_code == 200
    data = resp.json()
    evt_a = next(e for e in data["events"] if e["event_id"] == "evt-a")
    evt_b = next(e for e in data["events"] if e["event_id"] == "evt-b")
    assert "evt-b" in evt_a["causal_child_ids"]
    assert evt_b["causal_child_ids"] == []


async def test_causal_child_ids_via_causes_field():
    """Event B lists A in its 'causes' -> A.causal_child_ids should contain B."""
    events = [
        {"event_id": "evt-a", "event_type": "world.send", "actor_id": "agent-1",
         "caused_by": None, "causes": []},
        {"event_id": "evt-b", "event_type": "world.reply", "actor_id": "agent-1",
         "caused_by": None, "causes": ["evt-a"]},
    ]
    run_data = {"run_id": "run-1", "world_def": {"actors": []}}
    gateway = _make_gateway(run_data, events)

    from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)
    resp = client.get("/api/v1/runs/run-1/events")
    data = resp.json()
    evt_a = next(e for e in data["events"] if e["event_id"] == "evt-a")
    assert "evt-b" in evt_a["causal_child_ids"]


async def test_actor_role_from_world_def():
    """Actor role should be populated from world_def actors."""
    events = [
        {"event_id": "evt-1", "event_type": "world.send", "actor_id": "agent-1",
         "caused_by": None, "causes": []},
    ]
    run_data = {
        "run_id": "run-1",
        "world_def": {"actors": [{"id": "agent-1", "role": "support_agent"}]},
    }
    gateway = _make_gateway(run_data, events)

    from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)
    resp = client.get("/api/v1/runs/run-1/events")
    data = resp.json()
    assert data["events"][0]["actor_role"] == "support_agent"


async def test_actor_role_empty_for_unknown():
    """Unknown actor_id -> actor_role should be empty string."""
    events = [
        {"event_id": "evt-1", "event_type": "world.send", "actor_id": "unknown-actor",
         "caused_by": None, "causes": []},
    ]
    run_data = {
        "run_id": "run-1",
        "world_def": {"actors": [{"id": "agent-1", "role": "support"}]},
    }
    gateway = _make_gateway(run_data, events)

    from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)
    resp = client.get("/api/v1/runs/run-1/events")
    data = resp.json()
    assert data["events"][0]["actor_role"] == ""


async def test_enrichment_does_not_mutate_originals():
    """Regression: original event dicts should not be modified by enrichment."""
    original_events = [
        {"event_id": "evt-1", "event_type": "world.send", "actor_id": "agent-1",
         "caused_by": None, "causes": []},
    ]
    frozen_copy = copy.deepcopy(original_events)

    run_data = {"run_id": "run-1", "world_def": {"actors": [{"id": "agent-1", "role": "x"}]}}
    gateway = _make_gateway(run_data, original_events)

    from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)
    client.get("/api/v1/runs/run-1/events")

    # Original events should NOT have been mutated
    assert "causal_child_ids" not in original_events[0]
    assert "actor_role" not in original_events[0]
    assert original_events == frozen_copy


async def test_multiple_children_collected():
    """An event with multiple causal children should list all of them."""
    events = [
        {"event_id": "root", "event_type": "world.trigger", "actor_id": "agent-1",
         "caused_by": None, "causes": []},
        {"event_id": "child-1", "event_type": "world.a", "actor_id": "agent-1",
         "caused_by": "root", "causes": []},
        {"event_id": "child-2", "event_type": "world.b", "actor_id": "agent-1",
         "caused_by": "root", "causes": []},
        {"event_id": "child-3", "event_type": "world.c", "actor_id": "agent-1",
         "caused_by": "root", "causes": []},
    ]
    run_data = {"run_id": "run-1", "world_def": {"actors": []}}
    gateway = _make_gateway(run_data, events)

    from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()

    from starlette.testclient import TestClient

    client = TestClient(adapter._app_instance)
    resp = client.get("/api/v1/runs/run-1/events")
    data = resp.json()
    root_evt = next(e for e in data["events"] if e["event_id"] == "root")
    assert sorted(root_evt["causal_child_ids"]) == ["child-1", "child-2", "child-3"]
