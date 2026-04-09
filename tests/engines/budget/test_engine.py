"""Tests for the BudgetEngine — real budget tracking and enforcement."""

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.actors.registry import ActorRegistry
from volnix.core.context import ActionContext
from volnix.core.events import (
    BudgetDeductionEvent,
    BudgetExhaustedEvent,
    BudgetWarningEvent,
)
from volnix.core.types import ActorId, ActorType, ServiceId, StepVerdict
from volnix.engines.budget.config import BudgetConfig
from volnix.engines.budget.engine import BudgetEngine


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

        # Check for api_calls deduction event
        deduction_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "api_calls"
        ]
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
        deduction_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "api_calls"
        ]
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


class TestSpendUsdBudget:
    """Test spend_usd budget — deducts actual dollar amounts from payload."""

    @pytest.mark.asyncio
    async def test_spend_deducted_from_payload_amount(self, engine):
        """Action with amount in payload deducts from spend_usd."""
        reg = _make_registry(_make_agent(budget={"spend_usd": 1000.0}))
        engine._actor_registry = reg
        ctx = _make_ctx(input_data={"amount": 200})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.spend_usd_remaining == 800.0
        assert state.spend_usd_total == 1000.0

    @pytest.mark.asyncio
    async def test_spend_exhaustion_blocks(self, engine):
        """When spend_usd reaches 0, further actions are denied."""
        reg = _make_registry(_make_agent(budget={"spend_usd": 100.0}))
        engine._actor_registry = reg

        # First action: $100 refund → exhausts budget
        ctx = _make_ctx(input_data={"amount": 100})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        # Second action: any amount → denied
        ctx = _make_ctx(input_data={"amount": 10})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert "spend_usd" in result.message
        assert any(isinstance(e, BudgetExhaustedEvent) for e in result.events)

    @pytest.mark.asyncio
    async def test_no_amount_in_payload_zero_spend(self, engine):
        """Actions without amount field don't deduct from spend_usd."""
        reg = _make_registry(_make_agent(budget={"spend_usd": 500.0}))
        engine._actor_registry = reg
        ctx = _make_ctx(input_data={"query": "search something"})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.spend_usd_remaining == 500.0  # Unchanged

    @pytest.mark.asyncio
    async def test_spend_warning_threshold(self, engine):
        """Warning event emitted at 80% spend."""
        reg = _make_registry(_make_agent(budget={"spend_usd": 100.0}))
        engine._actor_registry = reg

        # Spend $85 → 85% used → warning
        ctx = _make_ctx(input_data={"amount": 85})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        warning_events = [e for e in result.events if isinstance(e, BudgetWarningEvent)]
        assert len(warning_events) == 1
        assert warning_events[0].budget_type == "spend_usd"

    @pytest.mark.asyncio
    async def test_spend_cumulative_across_actions(self, engine):
        """Multiple small actions accumulate toward spend_usd limit."""
        reg = _make_registry(_make_agent(budget={"spend_usd": 500.0}))
        engine._actor_registry = reg

        # 8 x $60 = $480 (under $500)
        for i in range(8):
            ctx = _make_ctx(input_data={"amount": 60})
            result = await engine.execute(ctx)
            assert result.verdict == StepVerdict.ALLOW

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.spend_usd_remaining == 20.0  # 500 - 480

        # 9th action: $60 would exceed → but check is "remaining <= 0"
        # remaining is 20, not 0 yet, so it's allowed but remaining goes to 0
        ctx = _make_ctx(input_data={"amount": 60})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW  # Still allowed (remaining was > 0)

        # 10th action: now remaining is 0 → DENIED
        ctx = _make_ctx(input_data={"amount": 10})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY

    @pytest.mark.asyncio
    async def test_spend_usd_not_defined_unlimited(self, engine):
        """When spend_usd is not in budget_def, spending is unlimited."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100}))
        engine._actor_registry = reg
        ctx = _make_ctx(input_data={"amount": 999999})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_negative_amount_clamped_to_zero(self, engine):
        """Negative amounts in payload cannot add budget back."""
        reg = _make_registry(_make_agent(budget={"spend_usd": 100.0}))
        engine._actor_registry = reg
        ctx = _make_ctx(input_data={"amount": -500})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.spend_usd_remaining == 100.0  # Unchanged — negative clamped to 0

    @pytest.mark.asyncio
    async def test_spend_deduction_event_emitted(self, engine):
        """A BudgetDeductionEvent with budget_type=spend_usd is emitted."""
        reg = _make_registry(_make_agent(budget={"spend_usd": 1000.0}))
        engine._actor_registry = reg
        ctx = _make_ctx(input_data={"amount": 200})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        spend_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "spend_usd"
        ]
        assert len(spend_events) == 1
        assert spend_events[0].amount == 200.0
        assert spend_events[0].remaining == 800.0

    @pytest.mark.asyncio
    async def test_spend_and_api_calls_independent(self, engine):
        """spend_usd and api_calls track independently."""
        reg = _make_registry(_make_agent(budget={"api_calls": 3, "spend_usd": 500.0}))
        engine._actor_registry = reg

        # 3 actions with $100 each
        for _ in range(3):
            ctx = _make_ctx(input_data={"amount": 100})
            result = await engine.execute(ctx)
            assert result.verdict == StepVerdict.ALLOW

        # api_calls exhausted (3/3), but spend_usd still has $200
        ctx = _make_ctx(input_data={"amount": 100})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert "api_calls" in result.message

    @pytest.mark.asyncio
    async def test_ungoverned_spend_exhausted_allowed(self, engine):
        """In ungoverned mode, spend exhaustion is logged but allowed."""
        engine._world_mode = "ungoverned"
        reg = _make_registry(_make_agent(budget={"spend_usd": 50.0}))
        engine._actor_registry = reg

        # Exhaust budget
        ctx = _make_ctx(input_data={"amount": 50})
        await engine.execute(ctx)

        # Next action: exhausted but allowed in ungoverned
        ctx = _make_ctx(input_data={"amount": 10})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW
        assert "ungoverned" in result.message


class TestBudgetResetBetweenRuns:
    """Budget tracker resets when a new run starts."""

    @pytest.mark.asyncio
    async def test_reset_restores_full_budget(self, engine):
        """After reset, budget starts fresh from actor definition."""
        reg = _make_registry(_make_agent(budget={"api_calls": 5, "spend_usd": 100.0}))
        engine._actor_registry = reg

        # Use up some budget
        for _ in range(4):
            ctx = _make_ctx(input_data={"amount": 20})
            await engine.execute(ctx)

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.api_calls_remaining == 1
        assert state.spend_usd_remaining == 20.0

        # Reset (simulates new run)
        engine._tracker.reset()

        # Next call re-initializes from actor definition
        ctx = _make_ctx(input_data={"amount": 10})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.api_calls_remaining == 4  # 5 - 1
        assert state.spend_usd_remaining == 90.0  # 100 - 10


class TestWorldActionsDeductionEvent:
    """Test that world_actions deduction emits BudgetDeductionEvent."""

    @pytest.mark.asyncio
    async def test_world_actions_deduction_event_emitted(self, engine):
        """Verify world_actions deduction emits BudgetDeductionEvent."""
        reg = _make_registry(_make_agent(budget={"api_calls": 10, "world_actions": 10}))
        engine._actor_registry = reg
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        wa_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "world_actions"
        ]
        assert len(wa_events) == 1
        assert wa_events[0].amount == 1.0
        assert wa_events[0].remaining == 9.0

    @pytest.mark.asyncio
    async def test_world_actions_deduction_decrements_each_action(self, engine):
        """Each action decrements world_actions by 1."""
        reg = _make_registry(_make_agent(budget={"api_calls": 10, "world_actions": 5}))
        engine._actor_registry = reg

        for i in range(4):
            ctx = _make_ctx()
            result = await engine.execute(ctx)
            assert result.verdict == StepVerdict.ALLOW

        # After 4 actions, world_actions remaining should be 1
        wa_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "world_actions"
        ]
        assert wa_events[0].remaining == 1.0

    @pytest.mark.asyncio
    async def test_world_actions_and_api_calls_both_emitted(self, engine):
        """Both api_calls and world_actions deduction events are emitted."""
        reg = _make_registry(_make_agent(budget={"api_calls": 10, "world_actions": 10}))
        engine._actor_registry = reg
        ctx = _make_ctx()
        result = await engine.execute(ctx)

        api_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "api_calls"
        ]
        wa_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "world_actions"
        ]
        assert len(api_events) == 1
        assert len(wa_events) == 1


class TestConfigToggleDisablesDimension:
    """Test that track_* config flags suppress events and enforcement."""

    @pytest.mark.asyncio
    async def test_track_world_actions_false_suppresses_event(self):
        """track_world_actions=False suppresses the world_actions deduction event."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_world_actions=False)
        reg = _make_registry(_make_agent(budget={"api_calls": 10, "world_actions": 10}))
        engine._actor_registry = reg

        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        wa_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "world_actions"
        ]
        assert len(wa_events) == 0

        # api_calls event should still be present (track_api_calls defaults to True)
        api_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "api_calls"
        ]
        assert len(api_events) == 1

    @pytest.mark.asyncio
    async def test_track_api_calls_false_suppresses_event(self):
        """track_api_calls=False suppresses the api_calls deduction event."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_api_calls=False)
        reg = _make_registry(_make_agent(budget={"api_calls": 10, "world_actions": 10}))
        engine._actor_registry = reg

        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        api_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "api_calls"
        ]
        assert len(api_events) == 0

    @pytest.mark.asyncio
    async def test_track_spend_usd_false_suppresses_event(self):
        """track_spend_usd=False suppresses the spend_usd deduction event."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_spend_usd=False)
        reg = _make_registry(_make_agent(budget={"spend_usd": 1000.0}))
        engine._actor_registry = reg

        ctx = _make_ctx(input_data={"amount": 200})
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        spend_events = [
            e
            for e in result.events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "spend_usd"
        ]
        assert len(spend_events) == 0

    @pytest.mark.asyncio
    async def test_track_world_actions_false_skips_exhaustion_check(self):
        """track_world_actions=False skips world_actions exhaustion enforcement."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_world_actions=False)
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "world_actions": 5}))
        engine._actor_registry = reg

        # Manually exhaust world_actions
        engine._tracker.initialize_budget(
            ActorId("agent-1"), {"api_calls": 100, "world_actions": 5}
        )
        budget = engine._tracker.get_budget(ActorId("agent-1"))
        budget["world_actions_remaining"] = 0

        ctx = _make_ctx()
        result = await engine.execute(ctx)
        # Should ALLOW because world_actions tracking is disabled
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_track_api_calls_false_skips_exhaustion_check(self):
        """track_api_calls=False skips api_calls exhaustion enforcement."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_api_calls=False)
        reg = _make_registry(_make_agent(budget={"api_calls": 2}))
        engine._actor_registry = reg

        # Manually exhaust api_calls
        engine._tracker.initialize_budget(ActorId("agent-1"), {"api_calls": 2})
        budget = engine._tracker.get_budget(ActorId("agent-1"))
        budget["api_calls_remaining"] = 0

        ctx = _make_ctx()
        result = await engine.execute(ctx)
        # Should ALLOW because api_calls tracking is disabled
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_track_llm_spend_false_skips_exhaustion_check(self):
        """track_llm_spend=False skips llm_spend exhaustion enforcement."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_llm_spend=False)
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "llm_spend": 10.0}))
        engine._actor_registry = reg

        # Manually exhaust llm_spend
        engine._tracker.initialize_budget(ActorId("agent-1"), {"api_calls": 100, "llm_spend": 10.0})
        budget = engine._tracker.get_budget(ActorId("agent-1"))
        budget["llm_spend_remaining"] = 0.0

        ctx = _make_ctx()
        result = await engine.execute(ctx)
        # Should ALLOW because llm_spend tracking is disabled
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_track_spend_usd_false_skips_exhaustion_check(self):
        """track_spend_usd=False skips spend_usd exhaustion enforcement."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_spend_usd=False)
        reg = _make_registry(_make_agent(budget={"spend_usd": 100.0}))
        engine._actor_registry = reg

        # Manually exhaust spend_usd
        engine._tracker.initialize_budget(ActorId("agent-1"), {"spend_usd": 100.0})
        budget = engine._tracker.get_budget(ActorId("agent-1"))
        budget["spend_usd_remaining"] = 0.0

        ctx = _make_ctx(input_data={"amount": 50})
        result = await engine.execute(ctx)
        # Should ALLOW because spend_usd tracking is disabled
        assert result.verdict == StepVerdict.ALLOW


class TestLLMSpendDeduction:
    """Test post-responder LLM spend deduction."""

    @pytest.mark.asyncio
    async def test_deduct_llm_spend_updates_tracker(self, engine):
        """deduct_llm_spend reduces llm_spend_remaining."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "llm_spend": 10.0}))
        engine._actor_registry = reg

        # Initialize budget through a normal execute
        ctx = _make_ctx()
        await engine.execute(ctx)

        # Now deduct LLM spend
        await engine.deduct_llm_spend(ActorId("agent-1"), 3.5)

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.llm_spend_remaining_usd == 6.5

    @pytest.mark.asyncio
    async def test_deduct_llm_spend_emits_event(self, engine):
        """deduct_llm_spend publishes BudgetDeductionEvent to bus."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "llm_spend": 10.0}))
        engine._actor_registry = reg

        # Create a mock bus to capture published events
        published_events = []

        class MockBus:
            async def publish(self, event):
                published_events.append(event)

        engine._bus = MockBus()

        # Initialize budget through a normal execute
        ctx = _make_ctx()
        await engine.execute(ctx)

        # Deduct LLM spend
        await engine.deduct_llm_spend(ActorId("agent-1"), 2.0)

        # Check that a deduction event was published to the bus
        llm_events = [
            e
            for e in published_events
            if isinstance(e, BudgetDeductionEvent) and e.budget_type == "llm_spend"
        ]
        assert len(llm_events) == 1
        assert llm_events[0].amount == 2.0
        assert llm_events[0].remaining == 8.0

    @pytest.mark.asyncio
    async def test_llm_spend_exhausted_denies(self, engine):
        """Exhausted llm_spend budget returns DENY."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "llm_spend": 5.0}))
        engine._actor_registry = reg

        # Initialize and exhaust LLM spend
        ctx = _make_ctx()
        await engine.execute(ctx)

        # Directly exhaust the llm_spend
        budget = engine._tracker.get_budget(ActorId("agent-1"))
        budget["llm_spend_remaining"] = 0.0

        # Next execute should DENY because llm_spend is exhausted
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert "llm_spend" in result.message
        exhausted_events = [e for e in result.events if isinstance(e, BudgetExhaustedEvent)]
        assert len(exhausted_events) == 1
        assert exhausted_events[0].budget_type == "llm_spend"


class TestTimeBudget:
    """Test time budget initialization, tracking, and enforcement."""

    @pytest.mark.asyncio
    async def test_time_budget_initialized(self, engine):
        """time_seconds in budget_def initializes time_remaining."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "time_seconds": 300.0}))
        engine._actor_registry = reg

        ctx = _make_ctx()
        await engine.execute(ctx)

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.time_remaining_seconds == 300.0

    @pytest.mark.asyncio
    async def test_time_budget_exhausted_denies(self, engine):
        """Exhausted time budget returns DENY."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "time_seconds": 60.0}))
        engine._actor_registry = reg

        # Initialize
        ctx = _make_ctx()
        await engine.execute(ctx)

        # Manually exhaust time
        budget = engine._tracker.get_budget(ActorId("agent-1"))
        budget["time_remaining"] = 0.0

        # Next execute should DENY
        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert "time" in result.message
        exhausted_events = [e for e in result.events if isinstance(e, BudgetExhaustedEvent)]
        assert len(exhausted_events) == 1
        assert exhausted_events[0].budget_type == "time"

    @pytest.mark.asyncio
    async def test_time_not_defined_skips(self, engine):
        """No time_seconds in budget -> no time check."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100}))
        engine._actor_registry = reg

        ctx = _make_ctx()
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW

        # time_remaining_seconds should be None
        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.time_remaining_seconds is None

    @pytest.mark.asyncio
    async def test_time_deduction_via_tracker(self, engine):
        """ActionCost with time_seconds deducts from time_remaining."""
        from volnix.core.types import ActionCost

        reg = _make_registry(_make_agent(budget={"api_calls": 100, "time_seconds": 100.0}))
        engine._actor_registry = reg

        # Initialize budget
        ctx = _make_ctx()
        await engine.execute(ctx)

        # Deduct time via tracker
        cost = ActionCost(time_seconds=25.5)
        engine._tracker.deduct(ActorId("agent-1"), cost)

        state = engine._tracker.get_budget_state(ActorId("agent-1"))
        assert state.time_remaining_seconds == pytest.approx(74.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_track_time_false_skips_exhaustion_check(self):
        """track_time=False skips time exhaustion enforcement."""
        engine = BudgetEngine()
        engine._world_mode = "governed"
        engine._budget_config = BudgetConfig(track_time=False)
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "time_seconds": 60.0}))
        engine._actor_registry = reg

        # Initialize and exhaust time
        engine._tracker.initialize_budget(
            ActorId("agent-1"), {"api_calls": 100, "time_seconds": 60.0}
        )
        budget = engine._tracker.get_budget(ActorId("agent-1"))
        budget["time_remaining"] = 0.0

        ctx = _make_ctx()
        result = await engine.execute(ctx)
        # Should ALLOW because time tracking is disabled
        assert result.verdict == StepVerdict.ALLOW

    @pytest.mark.asyncio
    async def test_post_pipeline_time_deduction_via_budget_start_ns(self, engine):
        """budget_start_ns is set during execute() and can be used for post-pipeline deduction."""
        reg = _make_registry(_make_agent(budget={"api_calls": 100, "time_seconds": 100.0}))
        engine._actor_registry = reg

        ctx = _make_ctx()
        await engine.execute(ctx)

        # budget_start_ns should be set by execute()
        assert ctx.budget_start_ns is not None
        assert ctx.budget_start_ns > 0

        # Simulate post-pipeline deduction (as app.py does)
        import time as _time_mod

        elapsed = _time_mod.monotonic() - ctx.budget_start_ns
        assert elapsed >= 0

        from volnix.core.types import ActionCost

        engine._tracker.deduct(ctx.actor_id, ActionCost(time_seconds=elapsed))
        state = engine._tracker.get_budget_state(ctx.actor_id)
        # time was deducted from remaining
        assert state.time_remaining_seconds < 100.0
