"""Enforcement handlers for policy verdicts."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActionContext, EnforcementMode, StepResult


class EnforcementHandler:
    """Dispatches enforcement actions based on policy mode."""

    async def handle_hold(
        self, ctx: ActionContext, policy: dict[str, Any], config: dict[str, Any]
    ) -> StepResult:
        """Place the action on hold pending approval."""
        ...

    async def handle_block(
        self, ctx: ActionContext, policy: dict[str, Any]
    ) -> StepResult:
        """Block the action outright."""
        ...

    async def handle_escalate(
        self, ctx: ActionContext, policy: dict[str, Any], config: dict[str, Any]
    ) -> StepResult:
        """Escalate the action to a higher authority."""
        ...

    async def handle_log(
        self, ctx: ActionContext, policy: dict[str, Any]
    ) -> StepResult:
        """Log the policy match without enforcement."""
        ...

    async def dispatch(
        self, ctx: ActionContext, policy: dict[str, Any], mode: EnforcementMode
    ) -> StepResult:
        """Route to the appropriate handler based on enforcement mode."""
        ...
