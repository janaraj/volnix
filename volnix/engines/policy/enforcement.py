"""Enforcement handlers for policy verdicts.

Dispatches to the correct enforcement action (BLOCK, HOLD, ESCALATE, LOG)
based on the policy's configured enforcement mode. Each handler produces
an appropriate ``StepResult`` with the corresponding governance event.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ActionContext, StepResult
from volnix.core.events import (
    PolicyBlockEvent,
    PolicyEscalateEvent,
    PolicyFlagEvent,
    PolicyHoldEvent,
)
from volnix.core.types import (
    EnforcementMode,
    PolicyId,
    StepVerdict,
    Timestamp,
)


def _now_timestamp() -> Timestamp:
    """Create a Timestamp for the current moment."""
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _policy_id(policy: dict[str, Any]) -> PolicyId:
    """Extract or generate a PolicyId from a policy dict."""
    return PolicyId(policy.get("id", policy.get("name", "unknown")))


class EnforcementHandler:
    """Dispatches enforcement actions based on policy mode."""

    @staticmethod
    def _run_id(ctx: ActionContext) -> str | None:
        return str(ctx.run_id) if ctx.run_id else None

    async def handle_block(self, ctx: ActionContext, policy: dict[str, Any]) -> StepResult:
        """Block the action outright."""
        reason = policy.get("reason", f"Blocked by policy '{policy.get('name', 'unknown')}'")
        event = PolicyBlockEvent(
            event_type="policy.block",
            timestamp=_now_timestamp(),
            policy_id=_policy_id(policy),
            actor_id=ctx.actor_id,
            action=ctx.action,
            reason=reason,
            run_id=self._run_id(ctx),
        )
        return StepResult(
            step_name="policy",
            verdict=StepVerdict.DENY,
            events=[event],
            message=reason,
        )

    async def handle_hold(
        self, ctx: ActionContext, policy: dict[str, Any], config: dict[str, Any]
    ) -> StepResult:
        """Place the action on hold pending approval."""
        approver_role = config.get("approver_role", "supervisor")

        # Auto-approve if the acting agent already holds the approver role.
        # Actor IDs follow the format "{role}-{hash}", so rsplit extracts the role.
        actor_role = str(ctx.actor_id).rsplit("-", 1)[0]
        if actor_role == approver_role:
            event = PolicyFlagEvent(
                event_type="policy.flag",
                timestamp=_now_timestamp(),
                policy_id=_policy_id(policy),
                actor_id=ctx.actor_id,
                action=ctx.action,
                run_id=self._run_id(ctx),
            )
            return StepResult(
                step_name="policy",
                verdict=StepVerdict.ALLOW,
                events=[event],
                message=(
                    f"Hold auto-approved — '{ctx.actor_id}' "
                    f"has approver role '{approver_role}'"
                ),
            )

        hold_id = f"hold-{uuid.uuid4().hex[:12]}"
        timeout_str = config.get("timeout", "30m")
        timeout_seconds = _parse_timeout(timeout_str)

        event = PolicyHoldEvent(
            event_type="policy.hold",
            timestamp=_now_timestamp(),
            policy_id=_policy_id(policy),
            actor_id=ctx.actor_id,
            action=ctx.action,
            approver_role=approver_role,
            timeout_seconds=timeout_seconds,
            hold_id=hold_id,
            run_id=self._run_id(ctx),
        )
        return StepResult(
            step_name="policy",
            verdict=StepVerdict.HOLD,
            events=[event],
            message=f"Action held by policy '{policy.get('name', 'unknown')}' — awaiting approval from '{approver_role}'",
        )

    async def handle_escalate(
        self, ctx: ActionContext, policy: dict[str, Any], config: dict[str, Any]
    ) -> StepResult:
        """Escalate the action to a higher authority."""
        target_role = config.get("target_role", "supervisor")
        event = PolicyEscalateEvent(
            event_type="policy.escalate",
            timestamp=_now_timestamp(),
            policy_id=_policy_id(policy),
            actor_id=ctx.actor_id,
            action=ctx.action,
            target_role=target_role,
            original_actor=ctx.actor_id,
            run_id=self._run_id(ctx),
        )
        return StepResult(
            step_name="policy",
            verdict=StepVerdict.ESCALATE,
            events=[event],
            message=f"Action escalated to '{target_role}' by policy '{policy.get('name', 'unknown')}'",
        )

    async def handle_log(self, ctx: ActionContext, policy: dict[str, Any]) -> StepResult:
        """Log the policy match without enforcement."""
        event = PolicyFlagEvent(
            event_type="policy.flag",
            timestamp=_now_timestamp(),
            policy_id=_policy_id(policy),
            actor_id=ctx.actor_id,
            action=ctx.action,
            run_id=self._run_id(ctx),
        )
        return StepResult(
            step_name="policy",
            verdict=StepVerdict.ALLOW,
            events=[event],
            message=f"Policy '{policy.get('name', 'unknown')}' flagged (log only)",
        )

    async def dispatch(
        self, ctx: ActionContext, policy: dict[str, Any], mode: EnforcementMode | str
    ) -> StepResult:
        """Route to the appropriate handler based on enforcement mode."""
        mode_str = str(mode).lower()

        if mode_str == EnforcementMode.BLOCK:
            return await self.handle_block(ctx, policy)
        elif mode_str == EnforcementMode.HOLD:
            config = policy.get("hold_config", {})
            return await self.handle_hold(ctx, policy, config)
        elif mode_str == EnforcementMode.ESCALATE:
            config = policy.get("escalate_config", {})
            return await self.handle_escalate(ctx, policy, config)
        else:
            return await self.handle_log(ctx, policy)


def _parse_timeout(timeout_str: str | int | float) -> float:
    """Parse a timeout string like '30m', '1h', '60s' into seconds."""
    if isinstance(timeout_str, (int, float)):
        return float(timeout_str)

    s = str(timeout_str).strip().lower()
    if s.endswith("m"):
        return float(s[:-1]) * 60
    if s.endswith("h"):
        return float(s[:-1]) * 3600
    if s.endswith("s"):
        return float(s[:-1])
    try:
        return float(s)
    except ValueError:
        return 1800.0  # default 30 minutes
