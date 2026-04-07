"""Policy engine implementation.

Evaluates governance policies against action contexts, enforcing holds,
blocks, escalations, and logging as configured. All rules come from
user-defined YAML policies — no hardcoded conditions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from volnix.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    Event,
    PolicyId,
    StepResult,
    StepVerdict,
    WorldMode,
)
from volnix.core.events import PolicyFlagEvent
from volnix.core.types import ServiceId, Timestamp
from volnix.engines.policy.enforcement import EnforcementHandler
from volnix.engines.policy.evaluator import ConditionEvaluator

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
    subscriptions: ClassVar[list[str]] = []  # policy checks via pipeline step, not events
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
                    logger.info(
                        "Policy '%s' triggered: action=%s, enforcement=%s, actor=%s",
                        policy.get("name", "unknown"),
                        ctx.action,
                        mode,
                        ctx.actor_id,
                    )

        if not triggered:
            return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW)

        # Ungoverned mode: all enforcement becomes LOG
        if self._world_mode == WorldMode.UNGOVERNED or self._world_mode == "ungoverned":
            now = datetime.now(UTC)
            ts = Timestamp(world_time=now, wall_time=now, tick=0)
            run_id = str(ctx.run_id) if ctx.run_id else None
            events = [
                PolicyFlagEvent(
                    event_type="policy.flag",
                    timestamp=ts,
                    policy_id=PolicyId(p.get("id", p.get("name", "unknown"))),
                    actor_id=ctx.actor_id,
                    action=ctx.action,
                    run_id=run_id,
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

    async def get_active_policies(self, service_id: ServiceId | None = None) -> list[PolicyId]:
        """Return identifiers of currently active policies.

        Args:
            service_id: If given, filter to policies relevant to this service.
        """
        policies = self._policies
        if service_id is not None:
            policies = [
                p
                for p in policies
                if str(service_id) in str(p.get("services", "")) or not p.get("services")
            ]
        return [PolicyId(p.get("id", p.get("name", f"policy-{i}"))) for i, p in enumerate(policies)]

    async def resolve_hold(
        self,
        hold_id: str,
        approved: bool,
        approver: ActorId,
        reason: str | None = None,
    ) -> Event:
        """Resolve a held action by approving or rejecting it."""
        now = datetime.now(UTC)
        logger.info(
            "Hold %s resolved: approved=%s by %s reason=%s",
            hold_id,
            approved,
            approver,
            reason,
        )
        return PolicyFlagEvent(
            event_type="policy.hold_resolved",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            policy_id=PolicyId(hold_id),
            actor_id=approver,
            action=f"hold_{'approved' if approved else 'rejected'}",
            reason=reason or ("approved" if approved else "rejected"),
        )

    async def add_policy(self, policy_def: dict[str, Any]) -> PolicyId:
        """Add a new policy to the active set."""
        pid = PolicyId(
            policy_def.get("id", policy_def.get("name", f"policy-{len(self._policies)}"))
        )
        policy_def.setdefault("id", pid)
        self._policies.append(policy_def)
        return pid

    async def remove_policy(self, policy_id: PolicyId) -> None:
        """Remove a policy from the active set."""
        self._policies = [p for p in self._policies if p.get("id", p.get("name")) != policy_id]

    # -- Internal helpers ------------------------------------------------------

    def _matches_action(self, policy: dict[str, Any], ctx: ActionContext) -> bool:
        """Check if a policy's trigger matches the current action.

        String triggers are compiled to dict triggers during world compilation.
        Dict triggers use exact/prefix matching against the ``action`` field.
        """
        trigger = policy.get("trigger")

        if trigger is None:
            # No trigger = no automatic match; policies need an explicit trigger
            return False

        if isinstance(trigger, str):
            # String triggers are compiled to dict triggers during world
            # compilation (_compile_policy_triggers). If a string trigger
            # reaches runtime, it was either unresolvable or compilation
            # was skipped. No heuristic matching — return False.
            logger.warning(
                "Uncompiled NL trigger at runtime for policy '%s' — "
                "string triggers must be compiled to dict triggers "
                "during world compilation (trigger: %.100s)",
                policy.get("name", "unknown"),
                trigger,
            )
            return False

        if isinstance(trigger, dict):
            trigger_action = trigger.get("action", "")
            trigger_service = trigger.get("service", "")

            # Check action match (if specified)
            if trigger_action:
                action_match = (
                    trigger_action == ctx.action
                    or ctx.action.startswith(trigger_action + ".")
                    or ctx.action.startswith(trigger_action + "_")
                )
                if not action_match:
                    return False

            # Check service match (if specified)
            if trigger_service:
                if str(ctx.service_id) != trigger_service:
                    return False

            # At least one filter must be specified to match
            if trigger_action or trigger_service:
                return True

            # No action AND no service = matches all
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
