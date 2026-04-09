"""Tests for hold approval flow -- policy skip and pipeline integration."""

import pytest

from volnix.core.context import ActionContext
from volnix.core.events import PolicyHoldEvent
from volnix.core.types import ActorId, ServiceId, StepVerdict
from volnix.engines.policy.engine import PolicyEngine


def _make_ctx(
    action: str = "refund_create",
    actor_id: str = "agent-1",
    service_id: str = "stripe",
    input_data: dict | None = None,
    policy_flags: list[str] | None = None,
) -> ActionContext:
    """Create a minimal ActionContext for testing."""
    return ActionContext(
        request_id="test-req-hold",
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        input_data=input_data or {},
        policy_flags=policy_flags or [],
    )


@pytest.fixture
def engine():
    """Create a PolicyEngine with a hold policy."""
    e = PolicyEngine()
    e._world_mode = "governed"
    return e


class TestHoldApprovedFlag:
    """Policy engine skips evaluation when hold_approved flag is set."""

    async def test_policy_skips_on_hold_approved_flag(self, engine):
        """Pre-approved actions bypass policy evaluation entirely."""
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
        ctx = _make_ctx(
            action="refund_create",
            policy_flags=["hold_approved"],
        )
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert "pre-approved" in result.message.lower()

    async def test_hold_approved_skips_even_with_block_policy(self, engine):
        """hold_approved flag skips ALL policies, including blocks."""
        engine._policies = [
            {
                "name": "Block everything",
                "trigger": {"action": "refund_create"},
                "enforcement": "block",
            }
        ]
        ctx = _make_ctx(
            action="refund_create",
            policy_flags=["hold_approved"],
        )
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    async def test_without_flag_policy_still_holds(self, engine):
        """Without hold_approved flag, the policy holds as normal."""
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
        ctx = _make_ctx(action="refund_create")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.HOLD


class TestHoldVerdictInPipeline:
    """Hold verdict produces correct events with hold_id."""

    async def test_hold_verdict_produces_hold_event(self, engine):
        """A HOLD verdict should produce a PolicyHoldEvent with hold_id."""
        engine._policies = [
            {
                "name": "Refund approval",
                "trigger": {"action": "refund_create"},
                "enforcement": "hold",
                "hold_config": {
                    "approver_role": "supervisor",
                    "timeout": "1h",
                },
            }
        ]
        ctx = _make_ctx(action="refund_create", input_data={"amount": 500})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.HOLD
        assert len(result.events) == 1

        hold_event = result.events[0]
        assert isinstance(hold_event, PolicyHoldEvent)
        assert hold_event.hold_id.startswith("hold-")
        assert hold_event.approver_role == "supervisor"
        assert hold_event.timeout_seconds == 3600.0
        assert hold_event.actor_id == ActorId("agent-1")
        assert hold_event.action == "refund_create"

    async def test_hold_auto_approves_for_approver_role(self, engine):
        """Actor whose role matches approver_role gets auto-approved."""
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
        # Actor ID format: "role-hash" → rsplit("-", 1) extracts role
        ctx = _make_ctx(
            action="refund_create",
            actor_id="supervisor-abc123",
        )
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert "auto-approved" in result.message.lower()
