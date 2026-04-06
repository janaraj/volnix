"""Budget engine implementation.

Tracks per-actor resource budgets (API calls, LLM spend, world actions)
and enforces limits as a pipeline step. All budget definitions come from
the actor's YAML config — no hardcoded limits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from volnix.core import (
    ActionContext,
    ActionCost,
    ActorId,
    BaseEngine,
    BudgetState,
    Event,
    PipelineStep,
    StepResult,
    StepVerdict,
    WorldMode,
)
from volnix.core.events import BudgetDeductionEvent, BudgetExhaustedEvent
from volnix.core.types import Timestamp
from volnix.engines.budget.config import BudgetConfig
from volnix.engines.budget.tracker import BudgetTracker

logger = logging.getLogger(__name__)


def _now_timestamp() -> Timestamp:
    """Create a Timestamp for the current moment."""
    now = datetime.now(timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=0)


class BudgetEngine(BaseEngine):
    """Tracks and enforces per-actor resource budgets.

    Also acts as the ``budget`` pipeline step.
    """

    engine_name: ClassVar[str] = "budget"
    subscriptions: ClassVar[list[str]] = []  # budget checks via pipeline step, not events
    dependencies: ClassVar[list[str]] = ["state"]

    def __init__(self) -> None:
        super().__init__()
        self._actor_registry: Any = None
        self._world_mode: str = "governed"
        self._tracker = BudgetTracker()
        self._budget_config = BudgetConfig()

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "budget"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Check and deduct actor budget.

        Flow:
        1. Look up actor and their budget definition
        2. Initialize budget state if first action
        3. Check if api_calls_remaining > 0
        4. Deduct 1 api_call
        5. Check thresholds (warning/critical)
        6. Emit appropriate events

        In ungoverned mode, budget exhaustion is logged but not enforced.
        """
        actor = self._get_actor(ctx.actor_id)
        if actor is None or actor.budget is None:
            return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW)

        budget_def = actor.budget
        if not budget_def:
            return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW)

        # Ensure budget state is initialized
        if self._tracker.get_budget(ctx.actor_id) is None:
            self._tracker.initialize_budget(ctx.actor_id, budget_def)

        state = self._tracker.get_budget(ctx.actor_id)

        # Check if api_calls budget is exhausted BEFORE deducting
        if "api_calls" in budget_def and budget_def["api_calls"] > 0:
            if state["api_calls_remaining"] <= 0:
                event = BudgetExhaustedEvent(
                    event_type="budget.exhausted",
                    timestamp=_now_timestamp(),
                    actor_id=ctx.actor_id,
                    budget_type="api_calls",
                )
                if self._is_ungoverned():
                    return StepResult(
                        step_name=self.step_name,
                        verdict=StepVerdict.ALLOW,
                        events=[event],
                        message="ungoverned: budget exhausted but allowed",
                    )
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.DENY,
                    events=[event],
                    message="Budget exhausted: api_calls",
                )

        # Check if llm_spend budget is exhausted BEFORE deducting
        if "llm_spend" in budget_def and budget_def["llm_spend"] > 0:
            if state["llm_spend_remaining"] <= 0:
                event = BudgetExhaustedEvent(
                    event_type="budget.exhausted",
                    timestamp=_now_timestamp(),
                    actor_id=ctx.actor_id,
                    budget_type="llm_spend",
                )
                if self._is_ungoverned():
                    return StepResult(
                        step_name=self.step_name,
                        verdict=StepVerdict.ALLOW,
                        events=[event],
                        message="ungoverned: budget exhausted but allowed",
                    )
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.DENY,
                    events=[event],
                    message="Budget exhausted: llm_spend",
                )

        # Check if world_actions budget is exhausted BEFORE deducting
        if "world_actions" in budget_def and budget_def["world_actions"] > 0:
            if state["world_actions_remaining"] <= 0:
                event = BudgetExhaustedEvent(
                    event_type="budget.exhausted",
                    timestamp=_now_timestamp(),
                    actor_id=ctx.actor_id,
                    budget_type="world_actions",
                )
                if self._is_ungoverned():
                    return StepResult(
                        step_name=self.step_name,
                        verdict=StepVerdict.ALLOW,
                        events=[event],
                        message="ungoverned: budget exhausted but allowed",
                    )
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.DENY,
                    events=[event],
                    message="Budget exhausted: world_actions",
                )

        # Check if spend_usd budget is exhausted BEFORE deducting
        if "spend_usd" in budget_def and budget_def["spend_usd"] > 0:
            if state["spend_usd_remaining"] <= 0:
                event = BudgetExhaustedEvent(
                    event_type="budget.exhausted",
                    timestamp=_now_timestamp(),
                    actor_id=ctx.actor_id,
                    budget_type="spend_usd",
                )
                if self._is_ungoverned():
                    return StepResult(
                        step_name=self.step_name,
                        verdict=StepVerdict.ALLOW,
                        events=[event],
                        message="ungoverned: budget exhausted but allowed",
                    )
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.DENY,
                    events=[event],
                    message="Budget exhausted: spend_usd",
                )

        # Extract domain spend from payload.
        # Convention: packs use "amount" for spend-relevant values
        # (same convention as http_method for read/write classification).
        spend_amount = 0.0
        raw_amount = ctx.input_data.get("amount")
        if raw_amount is not None:
            try:
                spend_amount = max(0.0, float(raw_amount))
            except (ValueError, TypeError):
                logger.warning(
                    "Cannot extract spend_usd from payload amount=%r "
                    "(actor=%s, action=%s)",
                    raw_amount, ctx.actor_id, ctx.action,
                )

        # Deduct 1 api_call, 1 world_action, and any spend amount
        cost = ActionCost(api_calls=1, world_actions=1, spend_usd=spend_amount)
        self._tracker.deduct(ctx.actor_id, cost)

        # Build events list
        events: list[Event] = []
        state_after = self._tracker.get_budget(ctx.actor_id)

        # Deduction events for each active dimension
        events.append(BudgetDeductionEvent(
            event_type="budget.deduction",
            timestamp=_now_timestamp(),
            actor_id=ctx.actor_id,
            budget_type="api_calls",
            amount=1.0,
            remaining=float(state_after["api_calls_remaining"]),
        ))
        if spend_amount > 0:
            events.append(BudgetDeductionEvent(
                event_type="budget.deduction",
                timestamp=_now_timestamp(),
                actor_id=ctx.actor_id,
                budget_type="spend_usd",
                amount=spend_amount,
                remaining=float(state_after["spend_usd_remaining"]),
            ))

        # Check thresholds
        threshold_events = self._tracker.check_thresholds(
            ctx.actor_id,
            budget_def,
            warning_pct=self._budget_config.warning_threshold_pct,
            critical_pct=self._budget_config.critical_threshold_pct,
        )
        events.extend(threshold_events)

        return StepResult(
            step_name=self.step_name,
            verdict=StepVerdict.ALLOW,
            events=events,
        )

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Process inbound events."""
        logger.debug("%s: received event %s", self.engine_name, event.event_type)

    # -- Budget operations -----------------------------------------------------

    async def check_budget(self, ctx: ActionContext) -> StepResult:
        """Alias for execute — check budget for the action."""
        return await self.execute(ctx)

    async def deduct(
        self,
        actor_id: ActorId,
        api_calls: int = 0,
        llm_spend_usd: float = 0.0,
        world_actions: int = 0,
        spend_usd: float = 0.0,
    ) -> BudgetState:
        """Directly deduct a cost from an actor's budget."""
        cost = ActionCost(
            api_calls=api_calls,
            llm_spend_usd=llm_spend_usd,
            world_actions=world_actions,
            spend_usd=spend_usd,
        )
        self._tracker.deduct(actor_id, cost)
        state = self._tracker.get_budget_state(actor_id)
        if state is None:
            return BudgetState(
                api_calls_remaining=0, api_calls_total=0,
                llm_spend_remaining_usd=0.0, llm_spend_total_usd=0.0,
                world_actions_remaining=0, world_actions_total=0,
                spend_usd_remaining=0.0, spend_usd_total=0.0,
            )
        return state

    async def get_remaining(self, actor_id: ActorId) -> BudgetState:
        """Get remaining budget for an actor."""
        state = self._tracker.get_budget_state(actor_id)
        if state is None:
            return BudgetState(
                api_calls_remaining=0, api_calls_total=0,
                llm_spend_remaining_usd=0.0, llm_spend_total_usd=0.0,
                world_actions_remaining=0, world_actions_total=0,
                spend_usd_remaining=0.0, spend_usd_total=0.0,
            )
        return state

    async def get_spend_curve(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return spend curve data (stub — Phase G analytics)."""
        return []

    # -- Internal helpers ------------------------------------------------------

    def _get_actor(self, actor_id: ActorId) -> Any:
        """Look up an actor from the registry, returning None if not found."""
        if self._actor_registry is None:
            return None
        return self._actor_registry.get_or_none(actor_id)

    def _is_ungoverned(self) -> bool:
        """Check if the world is in ungoverned mode."""
        return (
            self._world_mode == WorldMode.UNGOVERNED
            or self._world_mode == "ungoverned"
        )
