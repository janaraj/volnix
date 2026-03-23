"""Budget engine implementation.

Tracks per-actor resource budgets (API calls, LLM spend, world actions)
and enforces limits as a pipeline step. All budget definitions come from
the actor's YAML config — no hardcoded limits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from terrarium.core import (
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
from terrarium.core.events import BudgetDeductionEvent, BudgetExhaustedEvent
from terrarium.core.types import Timestamp
from terrarium.engines.budget.config import BudgetConfig
from terrarium.engines.budget.tracker import BudgetTracker

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
    subscriptions: ClassVar[list[str]] = ["world"]
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

        # Deduct 1 api_call
        cost = ActionCost(api_calls=1)
        self._tracker.deduct(ctx.actor_id, cost)

        # Build events list
        events: list[Event] = []

        # Deduction event
        state_after = self._tracker.get_budget(ctx.actor_id)
        events.append(BudgetDeductionEvent(
            event_type="budget.deduction",
            timestamp=_now_timestamp(),
            actor_id=ctx.actor_id,
            budget_type="api_calls",
            amount=1.0,
            remaining=float(state_after["api_calls_remaining"]),
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

    async def deduct(self, actor_id: ActorId, cost: ActionCost) -> BudgetState:
        """Directly deduct a cost from an actor's budget."""
        self._tracker.deduct(actor_id, cost)
        state = self._tracker.get_budget_state(actor_id)
        if state is None:
            return BudgetState(
                api_calls_remaining=0, api_calls_total=0,
                llm_spend_remaining_usd=0.0, llm_spend_total_usd=0.0,
                world_actions_remaining=0, world_actions_total=0,
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
