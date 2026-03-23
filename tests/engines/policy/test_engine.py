"""Tests for the PolicyEngine — real policy evaluation."""
import pytest

from terrarium.core.context import ActionContext
from terrarium.core.types import ActorId, ActorType, ServiceId, StepVerdict
from terrarium.core.events import (
    PolicyBlockEvent,
    PolicyFlagEvent,
    PolicyHoldEvent,
    PolicyEscalateEvent,
)
from terrarium.actors.definition import ActorDefinition
from terrarium.actors.registry import ActorRegistry
from terrarium.engines.policy.engine import PolicyEngine


def _make_ctx(
    action: str = "email_send",
    actor_id: str = "agent-1",
    service_id: str = "email",
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
) -> ActorDefinition:
    return ActorDefinition(
        id=ActorId(actor_id),
        type=ActorType.AGENT,
        role=role,
        permissions=permissions or {},
    )


@pytest.fixture
def engine():
    """Create a PolicyEngine with default state."""
    e = PolicyEngine()
    e._world_mode = "governed"
    return e


class TestNoPolicies:
    """When no policies are configured, everything is allowed."""

    @pytest.mark.asyncio
    async def test_no_policies_returns_allow(self, engine):
        engine._policies = []
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert not result.events


class TestPolicyBlock:
    """Test policy with enforcement=block."""

    @pytest.mark.asyncio
    async def test_block_on_match(self, engine):
        engine._policies = [
            {
                "name": "Block payments",
                "trigger": {"action": "payment_create"},
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(action="payment_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert len(result.events) == 1
        assert isinstance(result.events[0], PolicyBlockEvent)

    @pytest.mark.asyncio
    async def test_block_with_condition(self, engine):
        engine._policies = [
            {
                "name": "Block large refunds",
                "trigger": {
                    "action": "refund_create",
                    "condition": "input.amount > 5000",
                },
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(action="refund_create", input_data={"amount": 10000})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_no_block_when_condition_false(self, engine):
        engine._policies = [
            {
                "name": "Block large refunds",
                "trigger": {
                    "action": "refund_create",
                    "condition": "input.amount > 5000",
                },
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(action="refund_create", input_data={"amount": 100})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW


class TestPolicyHold:
    """Test policy with enforcement=hold."""

    @pytest.mark.asyncio
    async def test_hold_on_match(self, engine):
        engine._policies = [
            {
                "name": "Refund approval",
                "trigger": {"action": "refund_create"},
                "enforcement": "hold",
                "hold_config": {
                    "approver_role": "supervisor",
                    "timeout": "30m",
                },
            }
        ]
        ctx = _make_ctx(action="refund_create", input_data={"amount": 100})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.HOLD
        assert len(result.events) == 1
        assert isinstance(result.events[0], PolicyHoldEvent)
        assert result.events[0].approver_role == "supervisor"
        assert result.events[0].timeout_seconds == 1800.0


class TestPolicyEscalate:
    """Test policy with enforcement=escalate."""

    @pytest.mark.asyncio
    async def test_escalate_on_match(self, engine):
        engine._policies = [
            {
                "name": "Escalate VIP",
                "trigger": {"action": "vip_request"},
                "enforcement": "escalate",
                "escalate_config": {"target_role": "manager"},
            }
        ]
        ctx = _make_ctx(action="vip_request")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ESCALATE
        assert len(result.events) == 1
        assert isinstance(result.events[0], PolicyEscalateEvent)
        assert result.events[0].target_role == "manager"


class TestPolicyLog:
    """Test policy with enforcement=log."""

    @pytest.mark.asyncio
    async def test_log_on_match(self, engine):
        engine._policies = [
            {
                "name": "Log email sends",
                "trigger": {"action": "email_send"},
                "enforcement": "log",
            }
        ]
        ctx = _make_ctx(action="email_send")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert len(result.events) == 1
        assert isinstance(result.events[0], PolicyFlagEvent)


class TestStrictestEnforcement:
    """Test that the strictest enforcement wins among multiple policies."""

    @pytest.mark.asyncio
    async def test_block_wins_over_log(self, engine):
        engine._policies = [
            {
                "name": "Log all",
                "trigger": {"action": "refund_create"},
                "enforcement": "log",
            },
            {
                "name": "Block refunds",
                "trigger": {"action": "refund_create"},
                "enforcement": "block",
            },
        ]
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_hold_wins_over_log(self, engine):
        engine._policies = [
            {
                "name": "Log all",
                "trigger": {"action": "refund_create"},
                "enforcement": "log",
            },
            {
                "name": "Hold refunds",
                "trigger": {"action": "refund_create"},
                "enforcement": "hold",
                "hold_config": {"approver_role": "supervisor", "timeout": "30m"},
            },
        ]
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.HOLD

    @pytest.mark.asyncio
    async def test_block_wins_over_hold(self, engine):
        engine._policies = [
            {
                "name": "Hold refunds",
                "trigger": {"action": "refund_create"},
                "enforcement": "hold",
                "hold_config": {"approver_role": "supervisor"},
            },
            {
                "name": "Block refunds",
                "trigger": {"action": "refund_create"},
                "enforcement": "block",
            },
        ]
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY


class TestUngovernedMode:
    """Test that ungoverned mode turns all enforcement into LOG."""

    @pytest.mark.asyncio
    async def test_ungoverned_block_becomes_allow(self, engine):
        engine._world_mode = "ungoverned"
        engine._policies = [
            {
                "name": "Block payments",
                "trigger": {"action": "payment_create"},
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(action="payment_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert len(result.events) == 1
        assert isinstance(result.events[0], PolicyFlagEvent)
        assert "ungoverned" in result.message

    @pytest.mark.asyncio
    async def test_ungoverned_hold_becomes_allow(self, engine):
        engine._world_mode = "ungoverned"
        engine._policies = [
            {
                "name": "Hold refunds",
                "trigger": {"action": "refund_create"},
                "enforcement": "hold",
            }
        ]
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert len(result.events) >= 1


class TestStringTrigger:
    """Test string-based trigger matching."""

    @pytest.mark.asyncio
    async def test_string_trigger_keyword_match(self, engine):
        engine._policies = [
            {
                "name": "Refund policy",
                "trigger": "refund amount exceeds agent authority",
                "enforcement": "hold",
                "hold_config": {"approver_role": "supervisor"},
            }
        ]
        # "refund" is in the trigger, and also in the action name
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.HOLD

    @pytest.mark.asyncio
    async def test_string_trigger_no_match(self, engine):
        engine._policies = [
            {
                "name": "Refund policy",
                "trigger": "refund amount exceeds agent authority",
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(action="email_send")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW


class TestActorContext:
    """Test that actor info is available in condition context."""

    @pytest.mark.asyncio
    async def test_actor_role_in_condition(self, engine):
        reg = _make_registry(_make_agent(role="supervisor"))
        engine._actor_registry = reg
        engine._policies = [
            {
                "name": "Agent-only block",
                "trigger": {
                    "action": "refund_create",
                    "condition": 'actor.role != "supervisor"',
                },
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        # Actor is supervisor, so condition is False → no block
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_non_supervisor_blocked(self, engine):
        reg = _make_registry(_make_agent(role="agent"))
        engine._actor_registry = reg
        engine._policies = [
            {
                "name": "Agent-only block",
                "trigger": {
                    "action": "refund_create",
                    "condition": 'actor.role != "supervisor"',
                },
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
