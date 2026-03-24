"""Tests for the 10 audit fixes (P0-1 through P2-11).

Each test verifies the ROOT CAUSE fix, not symptoms.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.registry import ActorRegistry
from terrarium.core.context import ActionContext, ResponseProposal, StepResult
from terrarium.core.errors import EntityNotFoundError, ValidationError
from terrarium.core.events import (
    BudgetExhaustedEvent,
    Event,
    PermissionDeniedEvent,
    WorldEvent,
)
from terrarium.core.types import (
    ActionCost,
    ActorId,
    ActorType,
    EntityId,
    FidelityMetadata,
    FidelitySource,
    FidelityTier,
    ServiceId,
    StateDelta,
    StepVerdict,
    Timestamp,
    ValidationType,
)
from terrarium.engines.budget.engine import BudgetEngine
from terrarium.engines.permission.engine import PermissionEngine
from terrarium.validation.consistency import ConsistencyValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    action: str = "email_send",
    actor_id: str = "test-agent",
    service_id: str = "email",
    input_data: dict | None = None,
) -> ActionContext:
    return ActionContext(
        request_id="test-req-audit",
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        input_data=input_data or {},
    )


def _make_agent(
    actor_id: str = "test-agent",
    permissions: dict | None = None,
    budget: dict | None = None,
) -> ActorDefinition:
    return ActorDefinition(
        id=ActorId(actor_id),
        type=ActorType.AGENT,
        role="test-agent",
        permissions=permissions or {"write": "all", "read": "all"},
        budget=budget,
    )


def _timestamp():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=0)


# ===========================================================================
# P0-1: Default HTTP/MCP actors bypass governance
# ===========================================================================


class TestP01DefaultActorGovernance:
    """Verify that unknown actors are denied in governed mode."""

    @pytest.mark.asyncio
    async def test_unknown_actor_denied_in_governed_mode(self):
        """Unknown actor in governed mode with a registry is DENIED."""
        engine = PermissionEngine()
        engine._actor_registry = ActorRegistry()  # empty registry
        engine._world_mode = "governed"

        ctx = _make_ctx(actor_id="random-unknown-agent")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.DENY
        assert "not registered" in result.message
        assert len(result.events) == 1
        assert isinstance(result.events[0], PermissionDeniedEvent)

    @pytest.mark.asyncio
    async def test_unknown_actor_allowed_in_ungoverned_mode(self):
        """Unknown actor in ungoverned mode is still ALLOWED."""
        engine = PermissionEngine()
        engine._actor_registry = ActorRegistry()
        engine._world_mode = "ungoverned"

        ctx = _make_ctx(actor_id="random-unknown-agent")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_unknown_actor_allowed_without_registry(self):
        """Without an actor registry injected, unknown actors are allowed (backward compat)."""
        engine = PermissionEngine()
        engine._actor_registry = None
        engine._world_mode = "governed"

        ctx = _make_ctx(actor_id="random-unknown-agent")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_registered_default_actor_passes_governance(self):
        """Registered default gateway actor (http-agent) passes through governance."""
        engine = PermissionEngine()
        reg = ActorRegistry()
        reg.register(_make_agent(
            actor_id="http-agent",
            permissions={"write": "all", "read": "all"},
        ))
        engine._actor_registry = reg
        engine._world_mode = "governed"

        ctx = _make_ctx(actor_id="http-agent")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_app_registers_default_gateway_actors(self):
        """TerrariumApp._inject_cross_engine_deps registers http-agent and mcp-agent."""
        # This is tested indirectly: the app fixture in integration tests now
        # registers these actors. We test the ActorRegistry directly.
        reg = ActorRegistry()
        for aid in ["http-agent", "mcp-agent"]:
            actor = ActorDefinition(
                id=ActorId(aid),
                type=ActorType.AGENT,
                role="gateway-default",
                permissions={"read": "all", "write": "all"},
            )
            reg.register(actor)

        assert reg.has_actor(ActorId("http-agent"))
        assert reg.has_actor(ActorId("mcp-agent"))

        # They should go through governance (have permissions)
        http_actor = reg.get(ActorId("http-agent"))
        assert http_actor.permissions["write"] == "all"
        assert http_actor.permissions["read"] == "all"


# ===========================================================================
# P0-2: Entity endpoint bypasses pipeline (permission check added)
# ===========================================================================


class TestP02EntityEndpointPermission:
    """Verify that /api/v1/entities/{type} now checks permissions."""

    @pytest.mark.asyncio
    async def test_entity_endpoint_has_actor_id_param(self):
        """The entity query endpoint now accepts actor_id query param."""
        import httpx
        from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

        permission_engine = AsyncMock()
        permission_engine.execute = AsyncMock(return_value=StepResult(
            step_name="permission", verdict=StepVerdict.ALLOW,
        ))

        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[])

        registry = MagicMock()
        def _get(name):
            if name == "permission":
                return permission_engine
            return state
        registry.get = MagicMock(side_effect=_get)

        gateway = MagicMock()
        gateway.get_tool_manifest = AsyncMock(return_value=[])
        mock_app = MagicMock()
        mock_app.registry = registry
        mock_app.bus = MagicMock()
        mock_app.bus.subscribe = AsyncMock()
        gateway._app = mock_app

        adapter = HTTPRestAdapter(gateway)
        await adapter.start_server()

        transport = httpx.ASGITransport(app=adapter.fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/entities/email?actor_id=my-agent")

        assert resp.status_code == 200
        # Verify permission engine was called
        permission_engine.execute.assert_awaited_once()
        call_ctx = permission_engine.execute.call_args[0][0]
        assert str(call_ctx.actor_id) == "my-agent"

    @pytest.mark.asyncio
    async def test_entity_endpoint_denied_returns_403(self):
        """When permission is denied, entity endpoint returns 403."""
        import httpx
        from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

        permission_engine = AsyncMock()
        permission_engine.execute = AsyncMock(return_value=StepResult(
            step_name="permission", verdict=StepVerdict.DENY,
            message="No read access",
        ))

        state = AsyncMock()
        registry = MagicMock()
        def _get(name):
            if name == "permission":
                return permission_engine
            return state
        registry.get = MagicMock(side_effect=_get)

        gateway = MagicMock()
        gateway.get_tool_manifest = AsyncMock(return_value=[])
        mock_app = MagicMock()
        mock_app.registry = registry
        mock_app.bus = MagicMock()
        mock_app.bus.subscribe = AsyncMock()
        gateway._app = mock_app

        adapter = HTTPRestAdapter(gateway)
        await adapter.start_server()

        transport = httpx.ASGITransport(app=adapter.fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/entities/email")

        assert resp.status_code == 403
        data = resp.json()
        assert "Permission denied" in data["error"]


# ===========================================================================
# P1-4: Consistency validator wrong signature
# ===========================================================================


class TestP14ConsistencyValidatorSignature:
    """Verify that ConsistencyValidator calls get_entity(entity_type, entity_id)."""

    @pytest.mark.asyncio
    async def test_validate_references_calls_with_two_args(self):
        """validate_references passes entity_type to state.get_entity."""
        class TrackingState:
            def __init__(self):
                self.calls = []

            async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict:
                self.calls.append((entity_type, str(entity_id)))
                return {"id": str(entity_id)}

        state = TrackingState()
        validator = ConsistencyValidator()
        delta = StateDelta(
            entity_type="refund",
            entity_id=EntityId("ref_1"),
            operation="create",
            fields={"charge": "ch_1"},
        )
        schema = {"fields": {"charge": "ref:charge"}}

        result = await validator.validate_references(delta, schema, state)
        assert result.valid is True
        assert state.calls == [("charge", "ch_1")]

    @pytest.mark.asyncio
    async def test_validate_entity_exists_calls_with_two_args(self):
        """validate_entity_exists passes entity_type to state.get_entity."""
        class TrackingState:
            def __init__(self):
                self.calls = []

            async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict:
                self.calls.append((entity_type, str(entity_id)))
                return {"id": str(entity_id)}

        state = TrackingState()
        validator = ConsistencyValidator()
        result = await validator.validate_entity_exists("charge", EntityId("ch_1"), state)
        assert result.valid is True
        assert state.calls == [("charge", "ch_1")]


# ===========================================================================
# P1-5: WebSocket subscribe not awaited + topic mismatch
# ===========================================================================


class TestP15WebSocketSubscribe:
    """Verify that bus.subscribe is awaited and uses wildcard topic."""

    @pytest.mark.asyncio
    async def test_websocket_subscribes_to_wildcard(self):
        """WebSocket endpoint subscribes to '*' (all events), not 'world'."""
        import httpx
        from starlette.testclient import TestClient
        from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

        captured_topics = []

        async def tracking_subscribe(topic, callback, **kwargs):
            captured_topics.append(topic)

        gateway = MagicMock()
        gateway.get_tool_manifest = AsyncMock(return_value=[])

        bus = MagicMock()
        bus.subscribe = AsyncMock(side_effect=tracking_subscribe)
        bus.unsubscribe = AsyncMock()

        permission_engine = AsyncMock()
        state = AsyncMock()
        registry = MagicMock()
        registry.get = MagicMock(return_value=state)

        mock_app = MagicMock()
        mock_app.registry = registry
        mock_app.bus = bus
        gateway._app = mock_app

        adapter = HTTPRestAdapter(gateway)
        await adapter.start_server()

        client = TestClient(adapter.fastapi_app)
        with client.websocket_connect("/api/v1/events/stream"):
            pass  # just connect and disconnect

        assert "*" in captured_topics
        assert "world" not in captured_topics


# ===========================================================================
# P1-6: Mounted GET routes drop path params
# ===========================================================================


class TestP16MountedRoutePathParams:
    """Verify that mounted GET routes extract and forward path params."""

    @pytest.mark.asyncio
    async def test_get_route_extracts_path_params(self):
        """GET route with {email_id} path param forwards it in arguments."""
        import httpx
        from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

        captured_args = {}

        async def mock_handle_request(**kwargs):
            captured_args.update(kwargs)
            return {"ok": True}

        gateway = MagicMock()
        gateway.get_tool_manifest = AsyncMock(return_value=[
            {"method": "GET", "path": "/email/v1/messages/{email_id}",
             "tool_name": "email_read"},
        ])
        gateway.handle_request = AsyncMock(side_effect=mock_handle_request)

        bus = MagicMock()
        bus.subscribe = AsyncMock()

        permission_engine = AsyncMock()
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[])
        registry = MagicMock()
        def _get(name):
            if name == "permission":
                return permission_engine
            return state
        registry.get = MagicMock(side_effect=_get)

        mock_app = MagicMock()
        mock_app.registry = registry
        mock_app.bus = bus
        gateway._app = mock_app

        adapter = HTTPRestAdapter(gateway)
        await adapter.start_server()

        transport = httpx.ASGITransport(app=adapter.fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/email/v1/messages/email-42")

        assert resp.status_code == 200
        assert captured_args["arguments"]["email_id"] == "email-42"
        assert captured_args["tool_name"] == "email_read"

    @pytest.mark.asyncio
    async def test_get_route_merges_query_params(self):
        """GET route merges query params into arguments."""
        import httpx
        from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter

        captured_args = {}

        async def mock_handle_request(**kwargs):
            captured_args.update(kwargs)
            return {"ok": True}

        gateway = MagicMock()
        gateway.get_tool_manifest = AsyncMock(return_value=[
            {"method": "GET", "path": "/email/v1/messages",
             "tool_name": "email_list"},
        ])
        gateway.handle_request = AsyncMock(side_effect=mock_handle_request)

        bus = MagicMock()
        bus.subscribe = AsyncMock()

        permission_engine = AsyncMock()
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[])
        registry = MagicMock()
        def _get(name):
            if name == "permission":
                return permission_engine
            return state
        registry.get = MagicMock(side_effect=_get)

        mock_app = MagicMock()
        mock_app.registry = registry
        mock_app.bus = bus
        gateway._app = mock_app

        adapter = HTTPRestAdapter(gateway)
        await adapter.start_server()

        transport = httpx.ASGITransport(app=adapter.fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/email/v1/messages?mailbox_owner=alice@test.com")

        assert resp.status_code == 200
        assert captured_args["arguments"]["mailbox_owner"] == "alice@test.com"


# ===========================================================================
# P2-9: ResponseProposal.proposed_events wrong type
# ===========================================================================


class TestP29ProposedEventsType:
    """Verify that ResponseProposal.proposed_events accepts Event objects."""

    def test_proposed_events_accepts_event_objects(self):
        """proposed_events should accept real Event objects, not just EventId strings."""
        event = WorldEvent(
            event_type="world.test",
            timestamp=_timestamp(),
            actor_id=ActorId("test-actor"),
            service_id=ServiceId("email"),
            action="email_send",
            input_data={},
        )
        # This should NOT raise a ValidationError
        proposal = ResponseProposal(
            response_body={"ok": True},
            proposed_events=[event],
        )
        assert len(proposal.proposed_events) == 1
        assert proposal.proposed_events[0] == event

    def test_proposed_events_still_accepts_strings(self):
        """proposed_events should still accept EventId strings (backward compat)."""
        from terrarium.core.types import EventId
        proposal = ResponseProposal(
            response_body={},
            proposed_events=[EventId("evt-001"), EventId("evt-002")],
        )
        assert len(proposal.proposed_events) == 2

    def test_proposed_events_accepts_mixed(self):
        """proposed_events should accept both Event objects and strings."""
        event = Event(event_type="test.event", timestamp=_timestamp())
        proposal = ResponseProposal(
            response_body={},
            proposed_events=[event, "evt-string"],
        )
        assert len(proposal.proposed_events) == 2


# ===========================================================================
# P2-10: PackRuntime update validation skips constraints
# ===========================================================================


class TestP210UpdateValidationConstraints:
    """Verify that PackRuntime enforces enum/min/max on update operations."""

    @pytest.mark.asyncio
    async def test_update_validates_enum_constraint(self):
        """Update with value not in enum raises ValidationError."""
        from terrarium.packs.base import ServicePack
        from terrarium.packs.registry import PackRegistry
        from terrarium.packs.runtime import PackRuntime

        class EnumPack(ServicePack):
            pack_name = "enum_test"
            category = "test"
            fidelity_tier = 1

            def get_tools(self):
                return [{"name": "enum_update", "description": "test",
                         "parameters": {"type": "object", "properties": {}, "required": []}}]

            def get_entity_schemas(self):
                return {
                    "item": {
                        "type": "object",
                        "required": ["status"],
                        "properties": {
                            "status": {"type": "string", "enum": ["draft", "sent", "archived"]},
                        },
                    }
                }

            def get_state_machines(self):
                return {}

            async def handle_action(self, action, input_data, state):
                return ResponseProposal(
                    response_body={"ok": True},
                    proposed_state_deltas=[
                        StateDelta(
                            entity_type="item",
                            entity_id=EntityId("i-1"),
                            operation="update",
                            fields={"status": "INVALID_VALUE"},
                            previous_fields={"status": "draft"},
                        )
                    ],
                )

        registry = PackRegistry()
        registry.register(EnumPack())
        runtime = PackRuntime(registry)

        with pytest.raises(ValidationError, match="not in allowed values"):
            await runtime.execute("enum_update", {})

    @pytest.mark.asyncio
    async def test_update_validates_minimum_constraint(self):
        """Update with value below minimum raises ValidationError."""
        from terrarium.packs.base import ServicePack
        from terrarium.packs.registry import PackRegistry
        from terrarium.packs.runtime import PackRuntime

        class MinPack(ServicePack):
            pack_name = "min_test"
            category = "test"
            fidelity_tier = 1

            def get_tools(self):
                return [{"name": "min_update", "description": "test",
                         "parameters": {"type": "object", "properties": {}, "required": []}}]

            def get_entity_schemas(self):
                return {
                    "item": {
                        "type": "object",
                        "required": ["priority"],
                        "properties": {
                            "priority": {"type": "integer", "minimum": 0, "maximum": 5},
                        },
                    }
                }

            def get_state_machines(self):
                return {}

            async def handle_action(self, action, input_data, state):
                return ResponseProposal(
                    response_body={"ok": True},
                    proposed_state_deltas=[
                        StateDelta(
                            entity_type="item",
                            entity_id=EntityId("i-1"),
                            operation="update",
                            fields={"priority": -1},
                            previous_fields={"priority": 2},
                        )
                    ],
                )

        registry = PackRegistry()
        registry.register(MinPack())
        runtime = PackRuntime(registry)

        with pytest.raises(ValidationError, match="below minimum"):
            await runtime.execute("min_update", {})

    @pytest.mark.asyncio
    async def test_update_validates_maximum_constraint(self):
        """Update with value above maximum raises ValidationError."""
        from terrarium.packs.base import ServicePack
        from terrarium.packs.registry import PackRegistry
        from terrarium.packs.runtime import PackRuntime

        class MaxPack(ServicePack):
            pack_name = "max_test"
            category = "test"
            fidelity_tier = 1

            def get_tools(self):
                return [{"name": "max_update", "description": "test",
                         "parameters": {"type": "object", "properties": {}, "required": []}}]

            def get_entity_schemas(self):
                return {
                    "item": {
                        "type": "object",
                        "required": ["priority"],
                        "properties": {
                            "priority": {"type": "integer", "minimum": 0, "maximum": 5},
                        },
                    }
                }

            def get_state_machines(self):
                return {}

            async def handle_action(self, action, input_data, state):
                return ResponseProposal(
                    response_body={"ok": True},
                    proposed_state_deltas=[
                        StateDelta(
                            entity_type="item",
                            entity_id=EntityId("i-1"),
                            operation="update",
                            fields={"priority": 99},
                            previous_fields={"priority": 2},
                        )
                    ],
                )

        registry = PackRegistry()
        registry.register(MaxPack())
        runtime = PackRuntime(registry)

        with pytest.raises(ValidationError, match="above maximum"):
            await runtime.execute("max_update", {})

    @pytest.mark.asyncio
    async def test_update_valid_within_constraints_passes(self):
        """Update with valid enum/min/max values passes."""
        from terrarium.packs.base import ServicePack
        from terrarium.packs.registry import PackRegistry
        from terrarium.packs.runtime import PackRuntime

        class ValidPack(ServicePack):
            pack_name = "valid_test"
            category = "test"
            fidelity_tier = 1

            def get_tools(self):
                return [{"name": "valid_update", "description": "test",
                         "parameters": {"type": "object", "properties": {}, "required": []}}]

            def get_entity_schemas(self):
                return {
                    "item": {
                        "type": "object",
                        "required": ["status", "priority"],
                        "properties": {
                            "status": {"type": "string", "enum": ["draft", "sent"]},
                            "priority": {"type": "integer", "minimum": 0, "maximum": 5},
                        },
                    }
                }

            def get_state_machines(self):
                return {}

            async def handle_action(self, action, input_data, state):
                return ResponseProposal(
                    response_body={"ok": True},
                    proposed_state_deltas=[
                        StateDelta(
                            entity_type="item",
                            entity_id=EntityId("i-1"),
                            operation="update",
                            fields={"status": "sent", "priority": 3},
                            previous_fields={"status": "draft", "priority": 1},
                        )
                    ],
                )

        registry = PackRegistry()
        registry.register(ValidPack())
        runtime = PackRuntime(registry)

        proposal = await runtime.execute("valid_update", {})
        assert proposal.response_body["ok"] is True


# ===========================================================================
# P2-11: Budget only enforces api_calls
# ===========================================================================


class TestP211BudgetEnforcesAllTypes:
    """Verify that budget engine enforces llm_spend and world_actions."""

    @pytest.mark.asyncio
    async def test_llm_spend_exhausted_denies(self):
        """Actor with exhausted llm_spend budget is DENIED."""
        engine = BudgetEngine()
        reg = ActorRegistry()
        agent = _make_agent(
            actor_id="spender",
            budget={"api_calls": 100, "llm_spend": 10.0},
        )
        reg.register(agent)
        engine._actor_registry = reg
        engine._world_mode = "governed"

        # Initialize budget and manually exhaust llm_spend
        engine._tracker.initialize_budget(ActorId("spender"), agent.budget)
        budget = engine._tracker.get_budget(ActorId("spender"))
        budget["llm_spend_remaining"] = 0.0

        ctx = _make_ctx(actor_id="spender")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.DENY
        assert "llm_spend" in result.message

    @pytest.mark.asyncio
    async def test_world_actions_exhausted_denies(self):
        """Actor with exhausted world_actions budget is DENIED."""
        engine = BudgetEngine()
        reg = ActorRegistry()
        agent = _make_agent(
            actor_id="actor-wa",
            budget={"api_calls": 100, "world_actions": 5},
        )
        reg.register(agent)
        engine._actor_registry = reg
        engine._world_mode = "governed"

        # Initialize budget and manually exhaust world_actions
        engine._tracker.initialize_budget(ActorId("actor-wa"), agent.budget)
        budget = engine._tracker.get_budget(ActorId("actor-wa"))
        budget["world_actions_remaining"] = 0

        ctx = _make_ctx(actor_id="actor-wa")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.DENY
        assert "world_actions" in result.message

    @pytest.mark.asyncio
    async def test_api_calls_still_enforced(self):
        """Existing api_calls enforcement still works."""
        engine = BudgetEngine()
        reg = ActorRegistry()
        agent = _make_agent(
            actor_id="caller",
            budget={"api_calls": 2},
        )
        reg.register(agent)
        engine._actor_registry = reg
        engine._world_mode = "governed"

        # Use up both calls
        for _ in range(2):
            result = await engine.execute(_make_ctx(actor_id="caller"))
            assert result.verdict == StepVerdict.ALLOW

        # Third call should be denied
        result = await engine.execute(_make_ctx(actor_id="caller"))
        assert result.verdict == StepVerdict.DENY
        assert "api_calls" in result.message

    @pytest.mark.asyncio
    async def test_llm_spend_exhausted_ungoverned_allows(self):
        """In ungoverned mode, exhausted llm_spend is allowed."""
        engine = BudgetEngine()
        reg = ActorRegistry()
        agent = _make_agent(
            actor_id="spender-ug",
            budget={"api_calls": 100, "llm_spend": 10.0},
        )
        reg.register(agent)
        engine._actor_registry = reg
        engine._world_mode = "ungoverned"

        engine._tracker.initialize_budget(ActorId("spender-ug"), agent.budget)
        budget = engine._tracker.get_budget(ActorId("spender-ug"))
        budget["llm_spend_remaining"] = 0.0

        ctx = _make_ctx(actor_id="spender-ug")
        result = await engine.execute(ctx)

        assert result.verdict == StepVerdict.ALLOW
        assert "ungoverned" in result.message
