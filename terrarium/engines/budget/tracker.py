"""Budget tracker -- per-actor budget state management.

Manages in-memory budget state for each actor and provides threshold
checking against configured warning/critical levels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from terrarium.core.events import (
    BudgetDeductionEvent,
    BudgetExhaustedEvent,
    BudgetWarningEvent,
    Event,
)
from terrarium.core.types import ActionCost, ActorId, BudgetState, Timestamp

logger = logging.getLogger(__name__)


def _now_timestamp() -> Timestamp:
    """Create a Timestamp for the current moment."""
    now = datetime.now(timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=0)


class BudgetTracker:
    """Manages per-actor budget state and threshold checks.

    Budget state is stored in memory as a mutable dict keyed by actor_id.
    Each actor's state tracks remaining api_calls, llm_spend, and
    world_actions.
    """

    def __init__(self) -> None:
        self._budgets: dict[str, dict[str, Any]] = {}
        self._warned: dict[str, set[str]] = {}  # actor_id -> set of warned thresholds

    def reset(self) -> None:
        """Clear all budget state. Called between runs."""
        self._budgets.clear()
        self._warned.clear()

    def initialize_budget(self, actor_id: ActorId, budget_def: dict[str, Any]) -> None:
        """Create initial budget state from an actor's YAML budget definition.

        Args:
            actor_id: The actor whose budget to initialize.
            budget_def: Raw budget dict from YAML (e.g. {"api_calls": 500, "llm_spend": 10.0}).
        """
        aid = str(actor_id)
        self._budgets[aid] = {
            "api_calls_remaining": budget_def.get("api_calls", 0),
            "api_calls_total": budget_def.get("api_calls", 0),
            "llm_spend_remaining": budget_def.get("llm_spend", 0.0),
            "llm_spend_total": budget_def.get("llm_spend", 0.0),
            "world_actions_remaining": budget_def.get("world_actions", 0),
            "world_actions_total": budget_def.get("world_actions", 0),
            "spend_usd_remaining": budget_def.get("spend_usd", 0.0),
            "spend_usd_total": budget_def.get("spend_usd", 0.0),
        }
        self._warned[aid] = set()

    def get_budget(self, actor_id: ActorId) -> dict[str, Any] | None:
        """Retrieve the current budget state for an actor.

        Returns None if the actor has no budget initialized.
        """
        return self._budgets.get(str(actor_id))

    def get_budget_state(self, actor_id: ActorId) -> BudgetState | None:
        """Retrieve the current budget as a frozen BudgetState object."""
        state = self._budgets.get(str(actor_id))
        if state is None:
            return None
        return BudgetState(
            api_calls_remaining=state["api_calls_remaining"],
            api_calls_total=state["api_calls_total"],
            llm_spend_remaining_usd=state["llm_spend_remaining"],
            llm_spend_total_usd=state["llm_spend_total"],
            world_actions_remaining=state["world_actions_remaining"],
            world_actions_total=state["world_actions_total"],
            spend_usd_remaining=state["spend_usd_remaining"],
            spend_usd_total=state["spend_usd_total"],
        )

    def deduct(self, actor_id: ActorId, cost: ActionCost) -> dict[str, Any]:
        """Subtract a cost and return the updated budget state.

        Args:
            actor_id: The actor whose budget to deduct from.
            cost: The cost to deduct.

        Returns:
            The updated mutable budget state dict.
        """
        aid = str(actor_id)
        state = self._budgets.get(aid)
        if state is None:
            return {}

        state["api_calls_remaining"] = max(0, state["api_calls_remaining"] - cost.api_calls)
        state["llm_spend_remaining"] = max(0.0, state["llm_spend_remaining"] - cost.llm_spend_usd)
        state["world_actions_remaining"] = max(0, state["world_actions_remaining"] - cost.world_actions)
        state["spend_usd_remaining"] = max(0.0, state["spend_usd_remaining"] - cost.spend_usd)

        return state

    def check_thresholds(
        self,
        actor_id: ActorId,
        budget_def: dict[str, Any],
        warning_pct: float = 80.0,
        critical_pct: float = 95.0,
    ) -> list[Event]:
        """Check budget thresholds and return warning/exhausted events.

        Args:
            actor_id: The actor to check.
            budget_def: The original budget definition.
            warning_pct: Percentage at which to emit a warning.
            critical_pct: Percentage at which to emit a critical warning.

        Returns:
            List of threshold events (BudgetWarningEvent, BudgetExhaustedEvent).
        """
        aid = str(actor_id)
        state = self._budgets.get(aid)
        if state is None:
            return []

        events: list[Event] = []

        # Check api_calls thresholds
        if "api_calls" in budget_def and budget_def["api_calls"] > 0:
            total = state["api_calls_total"]
            remaining = state["api_calls_remaining"]
            if total > 0:
                used_pct = ((total - remaining) / total) * 100.0
                events.extend(
                    self._check_dimension_threshold(
                        actor_id, "api_calls", used_pct, remaining,
                        warning_pct, critical_pct,
                    )
                )

        # Check llm_spend thresholds
        if "llm_spend" in budget_def and budget_def["llm_spend"] > 0:
            total = state["llm_spend_total"]
            remaining = state["llm_spend_remaining"]
            if total > 0:
                used_pct = ((total - remaining) / total) * 100.0
                events.extend(
                    self._check_dimension_threshold(
                        actor_id, "llm_spend", used_pct, remaining,
                        warning_pct, critical_pct,
                    )
                )

        # Check world_actions thresholds
        if "world_actions" in budget_def and budget_def["world_actions"] > 0:
            total = state["world_actions_total"]
            remaining = state["world_actions_remaining"]
            if total > 0:
                used_pct = ((total - remaining) / total) * 100.0
                events.extend(
                    self._check_dimension_threshold(
                        actor_id, "world_actions", used_pct, remaining,
                        warning_pct, critical_pct,
                    )
                )

        # Check spend_usd thresholds
        if "spend_usd" in budget_def and budget_def["spend_usd"] > 0:
            total = state["spend_usd_total"]
            remaining = state["spend_usd_remaining"]
            if total > 0:
                used_pct = ((total - remaining) / total) * 100.0
                events.extend(
                    self._check_dimension_threshold(
                        actor_id, "spend_usd", used_pct, remaining,
                        warning_pct, critical_pct,
                    )
                )

        return events

    def _check_dimension_threshold(
        self,
        actor_id: ActorId,
        budget_type: str,
        used_pct: float,
        remaining: float,
        warning_pct: float,
        critical_pct: float,
    ) -> list[Event]:
        """Check a single budget dimension against thresholds."""
        aid = str(actor_id)
        events: list[Event] = []
        warned = self._warned.get(aid, set())

        ts = _now_timestamp()

        # Check exhaustion (100%)
        if remaining <= 0:
            key = f"{budget_type}_exhausted"
            if key not in warned:
                events.append(BudgetExhaustedEvent(
                    event_type="budget.exhausted",
                    timestamp=ts,
                    actor_id=actor_id,
                    budget_type=budget_type,
                ))
                warned.add(key)

        # Check critical threshold
        elif used_pct >= critical_pct:
            key = f"{budget_type}_critical"
            if key not in warned:
                events.append(BudgetWarningEvent(
                    event_type="budget.warning",
                    timestamp=ts,
                    actor_id=actor_id,
                    budget_type=budget_type,
                    threshold_pct=critical_pct,
                    remaining=remaining,
                ))
                warned.add(key)

        # Check warning threshold
        elif used_pct >= warning_pct:
            key = f"{budget_type}_warning"
            if key not in warned:
                events.append(BudgetWarningEvent(
                    event_type="budget.warning",
                    timestamp=ts,
                    actor_id=actor_id,
                    budget_type=budget_type,
                    threshold_pct=warning_pct,
                    remaining=remaining,
                ))
                warned.add(key)

        self._warned[aid] = warned
        return events
