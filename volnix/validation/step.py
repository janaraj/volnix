"""Validation pipeline step -- wraps ValidationPipeline as a PipelineStep."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ActionContext, StepResult
from volnix.core.events import ValidationFailureEvent
from volnix.core.types import StepVerdict, Timestamp
from volnix.pipeline.step import BasePipelineStep
from volnix.validation.pipeline import ValidationPipeline
from volnix.validation.schema import SchemaValidator
from volnix.validation.state_machine import StateMachineValidator

logger = logging.getLogger(__name__)


class ValidationStep(BasePipelineStep):
    """Pipeline step that validates the ResponseProposal.

    Runs structural checks on state deltas, then delegates to
    :class:`ValidationPipeline` for deep validation when the proposal
    carries ``validation_metadata`` from the responder.

    L1 fix: records ValidationEntry to ledger for audit trail.
    """

    step_name = "validation"

    def __init__(self, ledger: Any = None, state_engine: Any = None) -> None:
        self._schema_validator = SchemaValidator()
        self._sm_validator = StateMachineValidator()
        self._ledger = ledger
        self._state_engine = state_engine
        self._pipeline = ValidationPipeline()

    async def execute(self, ctx: ActionContext) -> StepResult:
        if ctx.response_proposal is None:
            await self._record_validation(
                ctx.action, passed=True, details={"reason": "no proposal"}
            )
            return self._make_result(StepVerdict.ALLOW, message="No proposal to validate")

        proposal = ctx.response_proposal
        errors: list[str] = []

        # 1. Structural checks (always -- backward compat)
        for delta in proposal.proposed_state_deltas or []:
            if not delta.entity_type:
                errors.append("StateDelta missing entity_type")
            if not delta.entity_id:
                errors.append("StateDelta missing entity_id")
            if delta.operation not in ("create", "update", "delete"):
                errors.append(f"Unknown operation: {delta.operation}")

        if errors:
            await self._record_validation(ctx.action, passed=False, details={"errors": errors})
            now = datetime.now(UTC)
            fail_event = ValidationFailureEvent(
                event_type="validation.failure",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                failure_type="pipeline_proposal",
                details={"errors": errors},
            )
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.ERROR,
                events=[fail_event],
                message="; ".join(errors),
            )

        # 2. Deep validation via ValidationPipeline (when metadata available)
        vm = proposal.validation_metadata
        if vm and (proposal.proposed_state_deltas or proposal.response_body):
            try:
                vr = await self._pipeline.validate_response_proposal(
                    proposal,
                    self._state_engine,
                    response_schema=vm.get("response_schema"),
                    state_machines=vm.get("state_machines"),
                    entity_schemas=vm.get("entity_schemas"),
                )
                if not vr.valid:
                    errors.extend(vr.errors)
            except Exception as exc:
                logger.warning("Deep validation failed: %s", exc)
                errors.append(f"Validation error: {exc}")

        passed = len(errors) == 0
        await self._record_validation(
            ctx.action,
            passed=passed,
            details={"errors": errors} if errors else {},
        )

        if errors:
            now = datetime.now(UTC)
            fail_event = ValidationFailureEvent(
                event_type="validation.failure",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                failure_type="pipeline_proposal",
                details={"errors": errors},
            )
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.ERROR,
                events=[fail_event],
                message="; ".join(errors),
            )
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
