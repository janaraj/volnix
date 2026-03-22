"""Validation pipeline step -- wraps ValidationPipeline as a PipelineStep."""
from __future__ import annotations

import logging

from terrarium.core.context import ActionContext, StepResult
from terrarium.core.types import StepVerdict
from terrarium.pipeline.step import BasePipelineStep
from terrarium.validation.schema import SchemaValidator
from terrarium.validation.state_machine import StateMachineValidator

logger = logging.getLogger(__name__)


class ValidationStep(BasePipelineStep):
    """Pipeline step that validates the ResponseProposal."""

    step_name = "validation"

    def __init__(self) -> None:
        self._schema_validator = SchemaValidator()
        self._sm_validator = StateMachineValidator()

    async def execute(self, ctx: ActionContext) -> StepResult:
        if ctx.response_proposal is None:
            return self._make_result(StepVerdict.ALLOW, message="No proposal to validate")

        # Validate entity deltas against basic structural rules.
        # Full schema+state-machine validation is already done by PackRuntime (step 5).
        # This step is a safety net that catches malformed proposals.
        errors: list[str] = []
        proposal = ctx.response_proposal

        for delta in (proposal.proposed_state_deltas or []):
            if not delta.entity_type:
                errors.append("StateDelta missing entity_type")
            if not delta.entity_id:
                errors.append("StateDelta missing entity_id")
            if delta.operation not in ("create", "update", "delete"):
                errors.append(f"Unknown operation: {delta.operation}")

        if errors:
            return self._make_result(StepVerdict.ERROR, message="; ".join(errors))

        return self._make_result(StepVerdict.ALLOW)
