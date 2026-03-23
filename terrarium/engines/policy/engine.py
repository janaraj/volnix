"""Policy engine implementation.

Evaluates governance policies against action contexts, enforcing holds,
blocks, escalations, and logging as configured. All rules come from
user-defined YAML policies — no hardcoded conditions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    EnforcementMode,
    Event,
    PipelineStep,
    PolicyId,
    StepResult,
    StepVerdict,
    WorldMode,
)
from terrarium.core.events import PolicyFlagEvent
from terrarium.core.types import Timestamp
from terrarium.engines.policy.evaluator import ConditionEvaluator
from terrarium.engines.policy.enforcement import EnforcementHandler

logger = logging.getLogger(__name__)

# Enforcement precedence: higher index = stricter
_ENFORCEMENT_RANK: dict[str, int] = {
    "log": 0,
    "escalate": 1,
    "hold": 2,
    "block": 3,
}


class PolicyEngine(BaseEngine):
    """Evaluates user-defined policies against action contexts.

    Also acts as the ``policy`` pipeline step.
    """

    engine_name: ClassVar[str] = "policy"
    subscriptions: ClassVar[list[str]] = ["approval"]
    dependencies: ClassVar[list[str]] = ["state"]

    def __init__(self) -> None:
        super().__init__()
        self._policies: list[dict[str, Any]] = []
        self._actor_registry: Any = None
        self._world_mode: str = "governed"
        self._evaluator = ConditionEvaluator()
        self._enforcement = EnforcementHandler()

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "policy"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Evaluate all active policies against the action.

        For each policy, checks if the trigger matches the action and
        if any condition expression is satisfied. Applies the strictest
        enforcement mode across all triggered policies.

        In ungoverned mode, all enforcement becomes LOG — policies still
        trigger and events are recorded, but nothing is blocked or held.
        """
        if not self._policies:
            return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW)

        triggered: list[tuple[dict[str, Any], str]] = []

        for policy in self._policies:
            if self._matches_action(policy, ctx):
                condition = self._extract_condition(policy)
                eval_context = self._build_eval_context(ctx)
                if self._evaluator.evaluate(condition, eval_context):
                    mode = str(policy.get("enforcement", "log")).lower()
                    triggered.append((policy, mode))

        if not triggered:
            return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW)

        # Ungoverned mode: all enforcement becomes LOG
        if self._world_mode == WorldMode.UNGOVERNED or self._world_mode == "ungoverned":
            now = datetime.now(timezone.utc)
            ts = Timestamp(world_time=now, wall_time=now, tick=0)
            events = [
                PolicyFlagEvent(
                    event_type="policy.flag",
                    timestamp=ts,
                    policy_id=PolicyId(p.get("id", p.get("name", "unknown"))),
                    actor_id=ctx.actor_id,
                    action=ctx.action,
                )
                for p, _ in triggered
            ]
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.ALLOW,
                events=events,
                message="ungoverned: policies triggered but not enforced",
            )

        # Governed mode: apply strictest enforcement
        return await self._apply_strictest(triggered, ctx)

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Process inbound events (e.g. approval resolutions)."""
        logger.debug("%s: received event %s", self.engine_name, event.event_type)

    # -- Policy operations -----------------------------------------------------

    async def evaluate(self, ctx: ActionContext) -> StepResult:
        """Alias for execute — evaluate policies against the context."""
        return await self.execute(ctx)

    async def get_active_policies(self) -> list[dict[str, Any]]:
        """Return all currently active policies."""
        return list(self._policies)

    async def resolve_hold(
        self, hold_id: str, approved: bool, approver: ActorId
    ) -> None:
        """Resolve a held action (stub — full hold queue is Phase G)."""
        logger.info(
            "Hold %s resolved: approved=%s by %s",
            hold_id, approved, approver,
        )

    async def add_policy(self, policy_def: dict[str, Any]) -> PolicyId:
        """Add a new policy to the active set."""
        pid = PolicyId(policy_def.get("id", policy_def.get("name", f"policy-{len(self._policies)}")))
        policy_def.setdefault("id", pid)
        self._policies.append(policy_def)
        return pid

    async def remove_policy(self, policy_id: PolicyId) -> None:
        """Remove a policy from the active set."""
        self._policies = [
            p for p in self._policies
            if p.get("id", p.get("name")) != policy_id
        ]

    # -- Internal helpers ------------------------------------------------------

    def _matches_action(self, policy: dict[str, Any], ctx: ActionContext) -> bool:
        """Check if a policy's trigger matches the current action."""
        trigger = policy.get("trigger")

        if trigger is None:
            # No trigger = matches all actions
            return True

        if isinstance(trigger, str):
            # String trigger: keyword-based matching against action name
            trigger_lower = trigger.lower()
            action_lower = ctx.action.lower()
            # Check if any word from the trigger appears in the action name
            trigger_words = trigger_lower.split()
            for word in trigger_words:
                if word in action_lower:
                    return True
            # Also check if the action appears in the trigger description
            if action_lower in trigger_lower:
                return True
            return False

        if isinstance(trigger, dict):
            # Dict trigger with "action" and optional "condition"
            trigger_action = trigger.get("action", "")
            if trigger_action:
                # Exact match or glob-style (action name contains the pattern)
                if trigger_action == ctx.action:
                    return True
                if trigger_action in ctx.action or ctx.action in trigger_action:
                    return True
                return False
            # No action specified in trigger dict = matches all
            return True

        return False

    def _extract_condition(self, policy: dict[str, Any]) -> str:
        """Extract the condition expression from a policy."""
        trigger = policy.get("trigger")

        if isinstance(trigger, str):
            # String trigger = no formal condition
            return ""

        if isinstance(trigger, dict):
            return trigger.get("condition", "")

        return ""

    def _build_eval_context(self, ctx: ActionContext) -> dict[str, Any]:
        """Build the evaluation context dict for condition expressions."""
        actor_info: dict[str, Any] = {
            "id": str(ctx.actor_id),
        }

        # Enrich with actor definition if available
        if self._actor_registry is not None:
            actor_def = self._actor_registry.get_or_none(ctx.actor_id)
            if actor_def is not None:
                actor_info["role"] = actor_def.role
                actor_info["type"] = str(actor_def.type)
                actor_info["permissions"] = actor_def.permissions

        return {
            "input": ctx.input_data,
            "actor": actor_info,
            "action": ctx.action,
            "service": str(ctx.service_id),
        }

    async def _apply_strictest(
        self,
        triggered: list[tuple[dict[str, Any], str]],
        ctx: ActionContext,
    ) -> StepResult:
        """Apply the strictest enforcement among all triggered policies."""
        # Sort by enforcement rank (strictest last)
        triggered.sort(key=lambda t: _ENFORCEMENT_RANK.get(t[1], 0))
        strictest_policy, strictest_mode = triggered[-1]

        return await self._enforcement.dispatch(ctx, strictest_policy, strictest_mode)
