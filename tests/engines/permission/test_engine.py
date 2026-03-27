"""Tests for the PermissionEngine — real permission checks."""
import pytest

from terrarium.core.context import ActionContext
from terrarium.core.types import ActorId, ActorType, ServiceId, StepVerdict
from terrarium.core.events import PermissionDeniedEvent
from terrarium.actors.definition import ActorDefinition
from terrarium.actors.registry import ActorRegistry
from terrarium.engines.permission.engine import PermissionEngine


def _make_ctx(
    action: str = "email_send",
    actor_id: str = "agent-1",
    service_id: str = "gmail",
    input_data: dict | None = None,
) -> ActionContext:
    """Create a minimal ActionContext for testing."""
    return ActionContext(
        request_id="test-req-001",
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        input_data=input_data or {},
    )


def _make_registry(*actors: ActorDefinition) -> ActorRegistry:
    """Create an ActorRegistry with the given actors."""
    reg = ActorRegistry()
    for a in actors:
        reg.register(a)
    return reg


def _make_agent(
    actor_id: str = "agent-1",
    role: str = "support-agent",
    permissions: dict | None = None,
    budget: dict | None = None,
) -> ActorDefinition:
    return ActorDefinition(
        id=ActorId(actor_id),
        type=ActorType.AGENT,
        role=role,
        permissions=permissions or {},
        budget=budget,
    )


@pytest.fixture
def engine():
    """Create a PermissionEngine with default state."""
    e = PermissionEngine()
    e._world_mode = "governed"
    return e


class TestWriteAccess:
    """Test write permission checks."""

    @pytest.mark.asyncio
    async def test_write_access_allowed(self, engine):
        reg = _make_registry(
            _make_agent(permissions={"write": ["gmail", "slack"], "read": ["gmail", "slack"]})
        )
        engine._actor_registry = reg
        ctx = _make_ctx(action="email_send", service_id="gmail")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_write_access_denied(self, engine):
        reg = _make_registry(
            _make_agent(permissions={"write": ["gmail", "slack"], "read": ["gmail", "slack", "stripe"]})
        )
        engine._actor_registry = reg
        ctx = _make_ctx(action="stripe_refunds_create", service_id="stripe")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert len(result.events) == 1
        assert isinstance(result.events[0], PermissionDeniedEvent)
        assert "stripe" in result.events[0].reason

    @pytest.mark.asyncio
    async def test_write_all_access(self, engine):
        reg = _make_registry(
            _make_agent(permissions={"write": "all", "read": "all"})
        )
        engine._actor_registry = reg
        ctx = _make_ctx(action="anything", service_id="any_service")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_empty_write_list_denies(self, engine):
        reg = _make_registry(
            _make_agent(permissions={"write": [], "read": ["gmail"]})
        )
        engine._actor_registry = reg
        ctx = _make_ctx(action="email_send", service_id="gmail")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY


class TestUnknownActor:
    """Test behavior when actor is not in the registry."""

    @pytest.mark.asyncio
    async def test_unknown_actor_denied_governed(self, engine):
        """In governed mode, unknown actors are DENIED."""
        reg = _make_registry()  # empty registry
        engine._actor_registry = reg
        engine._world_mode = "governed"
        ctx = _make_ctx(actor_id="unknown-agent")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert "not registered" in result.message

    @pytest.mark.asyncio
    async def test_unknown_actor_allowed_ungoverned(self, engine):
        """In ungoverned mode, unknown actors are ALLOWED."""
        reg = _make_registry()  # empty registry
        engine._actor_registry = reg
        engine._world_mode = "ungoverned"
        ctx = _make_ctx(actor_id="unknown-agent")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_no_registry_allowed(self, engine):
        engine._actor_registry = None
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW


class TestNoPermissions:
    """Test behavior when actor has no permissions defined."""

    @pytest.mark.asyncio
    async def test_no_permissions_allowed(self, engine):
        reg = _make_registry(_make_agent(permissions={}))
        engine._actor_registry = reg
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW


class TestActionConstraints:
    """Test action-specific authority constraints."""

    @pytest.mark.asyncio
    async def test_action_within_limit(self, engine):
        reg = _make_registry(
            _make_agent(
                permissions={
                    "read": ["stripe"],
                    "write": ["stripe"],
                    "actions": {"refund_create": {"max_amount": 5000}},
                }
            )
        )
        engine._actor_registry = reg
        ctx = _make_ctx(
            action="refund_create",
            service_id="stripe",
            input_data={"amount": 3000},
        )
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_action_exceeds_limit(self, engine):
        reg = _make_registry(
            _make_agent(
                permissions={
                    "read": ["stripe"],
                    "write": ["stripe"],
                    "actions": {"refund_create": {"max_amount": 5000}},
                }
            )
        )
        engine._actor_registry = reg
        ctx = _make_ctx(
            action="refund_create",
            service_id="stripe",
            input_data={"amount": 10000},
        )
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert len(result.events) == 1
        assert isinstance(result.events[0], PermissionDeniedEvent)
        assert "exceeds authority" in result.events[0].reason


class TestReadAccess:
    """Test that READ access is enforced."""

    @pytest.mark.asyncio
    async def test_read_access_allowed(self, engine):
        """Actor with read access to service → ALLOW."""
        actor = ActorDefinition(
            id=ActorId("agent-1"), type=ActorType.AGENT, role="agent",
            permissions={"read": ["gmail", "stripe"], "write": ["gmail"]},
        )
        engine._actor_registry = _make_registry(actor)
        result = await engine.execute(_make_ctx(service_id="gmail"))
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_read_access_denied(self, engine):
        """Actor without read access to service → DENY."""
        actor = ActorDefinition(
            id=ActorId("agent-1"), type=ActorType.AGENT, role="agent",
            permissions={"read": ["gmail"], "write": ["gmail", "stripe"]},
        )
        engine._actor_registry = _make_registry(actor)
        # Agent has WRITE to payments but NOT READ
        result = await engine.execute(_make_ctx(service_id="stripe"))
        assert result.verdict == StepVerdict.DENY
        assert any(isinstance(e, PermissionDeniedEvent) for e in result.events)
        assert "read" in result.message.lower()

    @pytest.mark.asyncio
    async def test_read_all_access(self, engine):
        """Actor with read='all' + write='all' → ALLOW for any service."""
        actor = ActorDefinition(
            id=ActorId("agent-1"), type=ActorType.AGENT, role="agent",
            permissions={"read": "all", "write": "all"},
        )
        engine._actor_registry = _make_registry(actor)
        result = await engine.execute(_make_ctx(service_id="stripe"))
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_invalid_string_access_denied(self, engine):
        """Non-'all' string in write_access → DENY (not a valid config)."""
        actor = ActorDefinition(
            id=ActorId("agent-1"), type=ActorType.AGENT, role="agent",
            permissions={"write": "supervisor", "read": "all"},
        )
        engine._actor_registry = _make_registry(actor)
        result = await engine.execute(_make_ctx(service_id="gmail"))
        # "supervisor" is not "all" and not a list → _has_access returns False → DENY
        assert result.verdict == StepVerdict.DENY


class TestUngovernedMode:
    """Test that ungoverned mode logs but allows."""

    @pytest.mark.asyncio
    async def test_ungoverned_denied_but_allowed(self, engine):
        engine._world_mode = "ungoverned"
        reg = _make_registry(
            _make_agent(permissions={"write": ["gmail"], "read": ["gmail"]})
        )
        engine._actor_registry = reg
        ctx = _make_ctx(action="stripe_refunds_create", service_id="stripe")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert len(result.events) == 1
        assert isinstance(result.events[0], PermissionDeniedEvent)
        assert "ungoverned" in result.message

    @pytest.mark.asyncio
    async def test_ungoverned_constraint_exceeded_but_allowed(self, engine):
        engine._world_mode = "ungoverned"
        reg = _make_registry(
            _make_agent(
                permissions={
                    "write": ["stripe"],
                    "actions": {"refund_create": {"max_amount": 5000}},
                }
            )
        )
        engine._actor_registry = reg
        ctx = _make_ctx(
            action="refund_create",
            service_id="stripe",
            input_data={"amount": 10000},
        )
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert len(result.events) == 1
        assert "ungoverned" in result.message
