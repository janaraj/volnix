"""Tests for dashboard API endpoints in http_rest.py.

Tests use REAL httpx.AsyncClient with ASGITransport against the FastAPI app.
No server is started -- httpx connects directly to the ASGI app.
"""

import asyncio

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_EVENTS = [
    {
        "event_id": "evt-001",
        "event_type": "world.zendesk_tickets_create",
        "actor_id": "agent-1",
        "service_id": "tickets",
        "target_service": "tickets",
        "outcome": "success",
        "timestamp": "2025-01-01T00:00:00Z",
        "parent_event_ids": [],
        "state_deltas": [
            {
                "entity_id": "ticket-001",
                "entity_type": "ticket",
                "operation": "create",
                "fields": {"id": "ticket-001", "subject": "Test", "status": "new"},
                "previous_fields": None,
            }
        ],
    },
    {
        "event_id": "evt-002",
        "event_type": "world.zendesk_tickets_update",
        "actor_id": "agent-1",
        "service_id": "tickets",
        "target_service": "tickets",
        "outcome": "success",
        "timestamp": "2025-01-01T00:01:00Z",
        "parent_event_ids": ["evt-001"],
        "state_deltas": [
            {
                "entity_id": "ticket-001",
                "entity_type": "ticket",
                "operation": "update",
                "fields": {"status": "open"},
                "previous_fields": {"status": "new"},
            }
        ],
    },
    {
        "event_id": "evt-003",
        "event_type": "world.zendesk_ticket_comments_create",
        "actor_id": "agent-2",
        "service_id": "tickets",
        "target_service": "tickets",
        "outcome": "success",
        "timestamp": "2025-01-01T00:02:00Z",
        "parent_event_ids": ["evt-002"],
        "state_deltas": [],
    },
]

SAMPLE_REPORT = {
    "entities": {
        "ticket": [
            {"id": "ticket-001", "subject": "Test", "status": "open"},
            {"id": "ticket-002", "subject": "Other", "status": "new"},
        ],
        "user": [
            {"id": "user-001", "name": "Alice", "role": "agent"},
        ],
    },
    "capability_gaps": [
        {"tick": 5, "agent": "agent-1", "tool": "calendar_create", "response": "skipped"},
    ],
    "gap_summary": {"total": 1, "by_response": {"skipped": 1}},
}

SAMPLE_SCORECARD = {
    "per_actor": {
        "agent-1": {
            "overall_score": 0.85,
            "policy_compliance": 1.0,
            "budget_discipline": 0.7,
        },
    },
    "collective": {
        "overall_score": 0.85,
    },
}

SAMPLE_RUN = {
    "run_id": "run_abc123",
    "status": "completed",
    "mode": "governed",
    "reality_preset": "messy",
    "fidelity_mode": "auto",
    "tag": "test-run",
    "created_at": "2025-01-01T00:00:00Z",
    "started_at": "2025-01-01T00:00:01Z",
    "completed_at": "2025-01-01T00:10:00Z",
    "world_def": {
        "actors": [
            {"id": "agent-1", "type": "external", "role": "support_agent"},
            {"id": "agent-2", "type": "external", "role": "escalation_agent"},
        ],
    },
    "config_snapshot": {},
}


def _make_dashboard_gateway():
    """Create a mock gateway wired for dashboard endpoint testing."""
    from terrarium.core.context import StepResult
    from terrarium.core.types import StepVerdict

    gateway = MagicMock()
    gateway.get_tool_manifest = AsyncMock(return_value=[])
    gateway.handle_request = AsyncMock(return_value={})

    # Mock permission engine
    permission_engine = AsyncMock()
    permission_engine.execute = AsyncMock(
        return_value=StepResult(step_name="permission", verdict=StepVerdict.ALLOW)
    )

    # Mock state engine
    state = AsyncMock()
    state.query_entities = AsyncMock(return_value=[])

    # Mock reporter
    reporter = AsyncMock()
    reporter.generate_scorecard = AsyncMock(return_value=SAMPLE_SCORECARD)

    registry = MagicMock()

    def _registry_get(name):
        if name == "permission":
            return permission_engine
        if name == "reporter":
            return reporter
        return state

    registry.get = MagicMock(side_effect=_registry_get)

    # Mock bus
    bus = MagicMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()

    # Mock run_manager
    run_manager = AsyncMock()
    run_manager.list_runs = AsyncMock(
        return_value=[SAMPLE_RUN, {**SAMPLE_RUN, "run_id": "run_def456", "status": "running", "tag": None}]
    )
    run_manager.get_run = AsyncMock(return_value=SAMPLE_RUN)

    # Mock artifact_store
    artifact_store = AsyncMock()

    async def _load_artifact(run_id, artifact_type):
        if artifact_type == "event_log":
            return SAMPLE_EVENTS
        if artifact_type == "scorecard":
            return SAMPLE_SCORECARD
        if artifact_type == "report":
            return SAMPLE_REPORT
        return None

    artifact_store.load_artifact = AsyncMock(side_effect=_load_artifact)
    artifact_store.list_artifacts = AsyncMock(return_value=[])

    # Mock diff_runs
    diff_result = {"run_ids": ["run_abc123", "run_def456"], "scores": {}}

    async def _diff_runs(run_ids):
        return diff_result

    # Wire app
    mock_app = MagicMock()
    mock_app.registry = registry
    mock_app.bus = bus
    mock_app.run_manager = run_manager
    mock_app.artifact_store = artifact_store
    mock_app.diff_runs = AsyncMock(side_effect=_diff_runs)
    mock_app.end_run = AsyncMock(return_value={"status": "completed"})

    gateway._app = mock_app
    return gateway


async def _make_client():
    """Create adapter + httpx client for testing."""
    gateway = _make_dashboard_gateway()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()
    transport = httpx.ASGITransport(app=adapter.fastapi_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client, gateway


# ---------------------------------------------------------------------------
# Endpoint 1: GET /api/v1/runs (enhanced)
# ---------------------------------------------------------------------------


async def test_list_runs_returns_paginated():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "runs" in body
    assert "total" in body
    assert body["total"] == 2


async def test_list_runs_filter_by_status():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs?status=completed")
    body = resp.json()
    assert body["total"] == 1
    assert body["runs"][0]["status"] == "completed"


async def test_list_runs_filter_by_tag():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs?tag=test-run")
    body = resp.json()
    assert body["total"] == 1


async def test_list_runs_offset():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs?limit=1&offset=1")
    body = resp.json()
    assert len(body["runs"]) == 1
    assert body["total"] == 2


async def test_list_runs_invalid_pagination():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs?limit=-1")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Endpoint 2: GET /api/v1/runs/:id (already tested elsewhere, sanity check)
# ---------------------------------------------------------------------------


async def test_get_run_found():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123")
    assert resp.status_code == 200


async def test_get_run_not_found():
    client, gw = await _make_client()
    gw._app.run_manager.get_run = AsyncMock(return_value=None)
    async with client:
        resp = await client.get("/api/v1/runs/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint 3: GET /api/v1/runs/:id/events
# ---------------------------------------------------------------------------


async def test_get_run_events_all():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["events"]) == 3


async def test_get_run_events_filter_actor():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events?actor_id=agent-2")
    body = resp.json()
    assert body["total"] == 1
    assert body["events"][0]["actor_id"] == "agent-2"


async def test_get_run_events_filter_service():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events?service_id=tickets")
    body = resp.json()
    assert body["total"] == 3


async def test_get_run_events_filter_event_type():
    client, gw = await _make_client()
    async with client:
        resp = await client.get(
            "/api/v1/runs/run_abc123/events?event_type=world.zendesk_tickets_create"
        )
    body = resp.json()
    assert body["total"] == 1


async def test_get_run_events_pagination():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events?limit=2&offset=0")
    body = resp.json()
    assert len(body["events"]) == 2
    assert body["total"] == 3


async def test_get_run_events_empty():
    client, gw = await _make_client()
    gw._app.artifact_store.load_artifact = AsyncMock(return_value=[])
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events")
    body = resp.json()
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# Endpoint 4: GET /api/v1/runs/:id/events/:eid
# ---------------------------------------------------------------------------


async def test_get_event_detail_found():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events/evt-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["event"]["event_id"] == "evt-001"


async def test_get_event_detail_not_found():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events/nonexistent")
    assert resp.status_code == 404


async def test_get_event_detail_ancestors():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events/evt-003")
    body = resp.json()
    # evt-003 parent is evt-002, evt-002 parent is evt-001
    assert "evt-002" in body["causal_ancestors"]
    assert "evt-001" in body["causal_ancestors"]


async def test_get_event_detail_descendants():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events/evt-001")
    body = resp.json()
    # evt-001 is parent of evt-002, which is parent of evt-003
    assert "evt-002" in body["causal_descendants"]
    assert "evt-003" in body["causal_descendants"]


# ---------------------------------------------------------------------------
# Endpoint 5: GET /api/v1/runs/:id/scorecard
# ---------------------------------------------------------------------------


async def test_get_run_scorecard():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/scorecard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run_abc123"
    assert "per_actor" in body
    assert "collective" in body


async def test_get_run_scorecard_not_found():
    client, gw = await _make_client()
    gw._app.artifact_store.load_artifact = AsyncMock(return_value=None)
    gw._app.registry.get = MagicMock(return_value=None)
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/scorecard")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint 6: GET /api/v1/runs/:id/entities
# ---------------------------------------------------------------------------


async def test_get_run_entities_all():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/entities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3  # 2 tickets + 1 user


async def test_get_run_entities_filter_type():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/entities?entity_type=ticket")
    body = resp.json()
    assert body["total"] == 2
    assert all(e["entity_type"] == "ticket" for e in body["entities"])


async def test_get_run_entities_pagination():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/entities?limit=1&offset=0")
    body = resp.json()
    assert len(body["entities"]) == 1
    assert body["total"] == 3


# ---------------------------------------------------------------------------
# Endpoint 7: GET /api/v1/runs/:id/entities/:eid
# ---------------------------------------------------------------------------


async def test_get_entity_detail_found():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/entities/ticket-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_id"] == "ticket-001"
    assert body["entity_type"] == "ticket"
    assert body["current_state"]["subject"] == "Test"


async def test_get_entity_detail_state_history():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/entities/ticket-001")
    body = resp.json()
    # ticket-001 has 2 state deltas (create in evt-001, update in evt-002)
    assert len(body["state_history"]) == 2
    assert body["state_history"][0]["operation"] == "create"
    assert body["state_history"][1]["operation"] == "update"


async def test_get_entity_detail_not_found():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/entities/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint 8: GET /api/v1/runs/:id/gaps
# ---------------------------------------------------------------------------


async def test_get_run_gaps():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/gaps")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run_abc123"
    assert len(body["gaps"]) == 1
    assert body["summary"]["total"] == 1


async def test_get_run_gaps_no_report():
    client, gw = await _make_client()
    gw._app.artifact_store.load_artifact = AsyncMock(return_value=None)
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/gaps")
    body = resp.json()
    assert body["gaps"] == []


# ---------------------------------------------------------------------------
# Endpoint 9: GET /api/v1/runs/:id/actors/:aid
# ---------------------------------------------------------------------------


async def test_get_actor_detail():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/actors/agent-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["actor_id"] == "agent-1"
    assert body["definition"]["role"] == "support_agent"
    assert body["action_count"] == 2  # agent-1 has evt-001 and evt-002
    assert body["scorecard"]["overall_score"] == 0.85


async def test_get_actor_detail_not_found():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/actors/nonexistent")
    assert resp.status_code == 404


async def test_get_actor_detail_run_not_found():
    client, gw = await _make_client()
    gw._app.run_manager.get_run = AsyncMock(return_value=None)
    async with client:
        resp = await client.get("/api/v1/runs/nonexistent/actors/agent-1")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint 10: GET /api/v1/compare
# ---------------------------------------------------------------------------


async def test_compare_runs():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/compare?runs=run_abc123,run_def456")
    assert resp.status_code == 200
    body = resp.json()
    assert "run_ids" in body


async def test_compare_runs_too_few():
    client, gw = await _make_client()
    async with client:
        resp = await client.get("/api/v1/compare?runs=run_abc123")
    assert resp.status_code == 400


async def test_compare_runs_error():
    client, gw = await _make_client()
    gw._app.diff_runs = AsyncMock(side_effect=ValueError("Run not found"))
    async with client:
        resp = await client.get("/api/v1/compare?runs=run_abc123,bad_id")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_events_no_artifact_returns_empty():
    """When artifact_store returns None and no live engine, events are empty."""
    client, gw = await _make_client()
    gw._app.artifact_store.load_artifact = AsyncMock(return_value=None)
    gw._app.registry.get = MagicMock(return_value=None)
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/events")
    body = resp.json()
    assert body["total"] == 0
    assert body["events"] == []


async def test_entities_report_none():
    """When report artifact is None, entities return empty."""
    client, gw = await _make_client()
    gw._app.artifact_store.load_artifact = AsyncMock(return_value=None)
    async with client:
        resp = await client.get("/api/v1/runs/run_abc123/entities")
    body = resp.json()
    assert body["total"] == 0


async def test_complete_run_error_handling():
    """complete_run returns 400 on ValueError."""
    client, gw = await _make_client()
    gw._app.end_run = AsyncMock(side_effect=ValueError("Not running"))
    async with client:
        resp = await client.post("/api/v1/runs/run_abc123/complete")
    assert resp.status_code == 400
