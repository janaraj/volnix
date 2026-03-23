"""Tests for the BudgetEngine — real budget tracking and enforcement."""
import pytest

from terrarium.core.context import ActionContext
from terrarium.core.types import ActorId, ActorType, ServiceId, StepVerdict
from terrarium.core.events import (
    BudgetDeductionEvent,
    BudgetExhaustedEvent,
    BudgetWarningEvent,
)
from terrarium.actors.definition import ActorDefinition
from terrarium.actors.registry import ActorRegistry
from terrarium.engines.budget.engine import BudgetEngine


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
    budget: dict | None = None,
) -> ActorDefinition:
    return ActorDefinition(
        id=ActorId(actor_id),
        type=ActorType.AGENT,
        role=role,
        budget=budget,
    )


@pytest.fixture
def engine():
    """Create a BudgetEngine with default state."""
    e = BudgetEngine()
    e._world_mode = "governed"
    return e


class TestNoBudget:
    """When no budget is defined, everything is allowed."""

    @pytest.mark.asyncio
    async def test_no_budget_returns_allow(self, engine):
        reg = _make_registry(_make_agent(budget=None))
        engine._actor_registry = reg
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_unknown_actor_returns_allow(self, engine):
        reg = _make_registry()  # empty
        engine._actor_registry = reg
        ctx = _make_ctx(actor_id="unknown-agent")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_no_registry_returns_allow(self, engine):
        engine._actor_registry = None
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_empty_budget_returns_allow(self, engine):
        reg = _make_registry(_make_agent(budget={}))
        engine._actor_registry = reg
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW


class TestBasicDeduction:
    """Test that actions deduct from the budget."""

    @pytest.mark.asyncio
    async def test_first_action_deducts_one(self, engine):
        reg = _make_registry(_make_agent(budget={"api_calls": 10}))
        engine._actor_registry = reg
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        # Check for deduction event
        deduction_events = [e for e in result.events if isinstance(e, BudgetDeductionEvent)]
        assert len(deduction_events) == 1
        assert deduction_events[0].amount == 1.0
        assert deduction_events[0].remaining == 9.0

    @pytest.mark.asyncio
    async def test_multiple_actions_deduct(self, engine):
        reg = _make_registry(_make_agent(budget={"api_calls": 5}))
        engine._actor_registry = reg

        for i in range(4):
            ctx = _make_ctx()
            result = await engine.execute(ctx)
            assert result.verdict == StepVerdict.ALLOW

        # After 4 deductions, 1 remaining
        deduction_events = [e for e in result.events if isinstance(e, BudgetDeductionEvent)]
        assert deduction_events[0].remaining == 1.0


class TestBudgetExhaustion:
    """Test budget exhaustion behavior."""

    @pytest.mark.asyncio
    async def test_exhausted_denies(self, engine):
        reg = _make_registry(_make_agent(budget={"api_calls": 2}))
        engine._actor_registry = reg

        # Use up all budget
        for _ in range(2):
            ctx = _make_ctx()
            result = await engine.execute(ctx)
            assert result.verdict == StepVerdict.ALLOW

        # Next action should be denied
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        exhausted_events = [e for e in result.events if isinstance(e, BudgetExhaustedEvent)]
        assert len(exhausted_events) == 1
        assert exhausted_events[0].budget_type == "api_calls"


class TestThresholds:
    """Test warning and critical threshold events."""

    @pytest.mark.asyncio
    async def test_warning_at_80_percent(self, engine):
        reg = _make_registry(_make_agent(budget={"api_calls": 10}))
        engine._actor_registry = reg

        # Use 8 of 10 = 80% used
        warning_found = False
        for i in range(8):
            ctx = _make_ctx()
            result = await engine.execute(ctx)
            for e in result.events:
                if isinstance(e, BudgetWarningEvent):
                    warning_found = True

        assert warning_found, "Expected BudgetWarningEvent at 80% threshold"

    @pytest.mark.asyncio
    async def test_critical_at_95_percent(self, engine):
        # Use 100 calls to get precise thresholds
        reg = _make_registry(_make_agent(budget={"api_calls": 100}))
        engine._actor_registry = reg

        warnings = []
        for i in range(96):
            ctx = _make_ctx()
            result = await engine.execute(ctx)
            for e in result.events:
                if isinstance(e, BudgetWarningEvent):
                    warnings.append(e)

        # Should have at least a warning and a critical
        assert len(warnings) >= 2
        thresholds = {w.threshold_pct for w in warnings}
        assert 80.0 in thresholds
        assert 95.0 in thresholds


class TestUngovernedMode:
    """Test that ungoverned mode logs but allows exhausted budgets."""

    @pytest.mark.asyncio
    async def test_ungoverned_exhausted_but_allowed(self, engine):
        engine._world_mode = "ungoverned"
        reg = _make_registry(_make_agent(budget={"api_calls": 1}))
        engine._actor_registry = reg

        # Use up budget
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        # Exhausted — should still ALLOW in ungoverned mode
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        exhausted_events = [e for e in result.events if isinstance(e, BudgetExhaustedEvent)]
        assert len(exhausted_events) == 1
        assert "ungoverned" in result.message


class TestMultipleActors:
    """Test that budgets are tracked independently per actor."""

    @pytest.mark.asyncio
    async def test_independent_tracking(self, engine):
        agent1 = _make_agent(actor_id="agent-1", budget={"api_calls": 3})
        agent2 = _make_agent(actor_id="agent-2", budget={"api_calls": 3})
        reg = _make_registry(agent1, agent2)
        engine._actor_registry = reg

        # Exhaust agent-1's budget
        for _ in range(3):
            ctx = _make_ctx(actor_id="agent-1")
            await engine.execute(ctx)

        # agent-1 should be denied
        ctx = _make_ctx(actor_id="agent-1")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY

        # agent-2 should still be allowed
        ctx = _make_ctx(actor_id="agent-2")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
