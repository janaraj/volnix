"""Validation pipeline step -- wraps ValidationPipeline as a PipelineStep."""

from __future__ import annotations

import logging
from typing import Any

from volnix.core.context import ActionContext, StepResult
from volnix.core.types import StepVerdict
from volnix.pipeline.step import BasePipelineStep
from volnix.validation.schema import SchemaValidator
from volnix.validation.state_machine import StateMachineValidator

logger = logging.getLogger(__name__)


class ValidationStep(BasePipelineStep):
    """Pipeline step that validates the ResponseProposal.

    L1 fix: records ValidationEntry to ledger for audit trail.
    """

    step_name = "validation"

    def __init__(self, ledger: Any = None) -> None:
        self._schema_validator = SchemaValidator()
        self._sm_validator = StateMachineValidator()
        self._ledger = ledger

    async def execute(self, ctx: ActionContext) -> StepResult:
        if ctx.response_proposal is None:
            await self._record_validation(
                ctx.action, passed=True, details={"reason": "no proposal"}
            )
            return self._make_result(StepVerdict.ALLOW, message="No proposal to validate")

        # Validate entity deltas against basic structural rules.
        errors: list[str] = []
        proposal = ctx.response_proposal

        for delta in proposal.proposed_state_deltas or []:
            if not delta.entity_type:
                errors.append("StateDelta missing entity_type")
            if not delta.entity_id:
                errors.append("StateDelta missing entity_id")
            if delta.operation not in ("create", "update", "delete"):
                errors.append(f"Unknown operation: {delta.operation}")

        passed = len(errors) == 0
        await self._record_validation(
            ctx.action,
            passed=passed,
            details={"errors": errors} if errors else {},
        )

        if errors:
            return self._make_result(StepVerdict.ERROR, message="; ".join(errors))

        return self._make_result(StepVerdict.ALLOW)

    async def _record_validation(self, target: str, passed: bool, details: dict[str, Any]) -> None:
        """L1: Record ValidationEntry to ledger."""
        if self._ledger is None:
            return
        from volnix.ledger.entries import ValidationEntry

        entry = ValidationEntry(
            validation_type="pipeline_proposal",
            target=target,
            passed=passed,
            details=details,
        )
        try:
            await self._ledger.append(entry)
        except Exception as exc:
            logger.warning("Validation ledger entry failed: %s", exc)
