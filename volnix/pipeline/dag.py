"""DAG-based pipeline executor for the Volnix framework.

Executes an ordered sequence of pipeline steps, threading an
:class:`~volnix.core.ActionContext` through each step and recording
results to the event bus and ledger.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from volnix.core.context import ActionContext, StepResult
from volnix.core.events import Event
from volnix.core.protocols import LedgerProtocol, PipelineStep
from volnix.core.types import StepVerdict
from volnix.ledger.entries import PipelineStepEntry


class PipelineDAG:
    """Ordered pipeline of steps that process an action context.

    Each step is executed in sequence.  If a step returns a terminal verdict,
    the pipeline short-circuits and marks the context accordingly.
    """

    # Field mapping from step name to ActionContext attribute
    _FIELD_MAP: dict[str, str] = {
        "permission": "permission_result",
        "policy": "policy_result",
        "budget": "budget_result",
        "capability": "capability_result",
        "responder": "responder_result",
        "validation": "validation_result",
        "commit": "commit_result",
    }

    def __init__(
        self,
        steps: list[PipelineStep],
        bus: Any | None = None,
        ledger: LedgerProtocol | None = None,
    ) -> None:
        self._steps = list(steps)
        self._bus = bus
        self._ledger = ledger

    @property
    def step_names(self) -> list[str]:
        """Return the ordered list of step names in the pipeline.

        Returns:
            A list of step name strings.
        """
        return [s.step_name for s in self._steps]

    async def execute(self, ctx: ActionContext) -> ActionContext:
        """Execute all pipeline steps against the given context.

        Steps are executed in order.  If a step yields a terminal verdict
        the pipeline short-circuits and returns the context immediately.

        Args:
            ctx: The mutable action context to process.

        Returns:
            The enriched action context after all (or short-circuited) steps.
        """
        for step in self._steps:
            t0 = time.monotonic()
            try:
                result = await step.execute(ctx)
            except Exception as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                logger.error(
                    "Pipeline step '%s' raised: %s", step.step_name, exc, exc_info=True,
                )
                result = StepResult(
                    step_name=step.step_name,
                    verdict=StepVerdict.ERROR,
                    message=str(exc),
                    duration_ms=elapsed_ms,
                )
            else:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                # DAG always measures its own wall-clock duration (overrides step's value)
                result = StepResult(
                    step_name=result.step_name,
                    verdict=result.verdict,
                    message=result.message,
                    events=result.events,
                    metadata=result.metadata,
                    duration_ms=elapsed_ms,
                )

            self._record_result(ctx, step.step_name, result)

            await self._record_to_ledger(ctx, result)

            for event in result.events:
                # Stamp context fields so governance events carry full
                # lineage: which run, which action, which service.
                updates: dict[str, Any] = {}
                if ctx.run_id and not event.run_id:
                    updates["run_id"] = str(ctx.run_id)
                if ctx.action and not event.action:
                    updates["action"] = ctx.action
                if ctx.service_id and not event.service_id:
                    updates["service_id"] = str(ctx.service_id)
                if updates:
                    event = event.model_copy(update=updates)
                await self._publish_step_event(event)

            if result.is_terminal:
                ctx.short_circuited = True
                ctx.short_circuit_step = step.step_name
                break

        return ctx

    def _record_result(self, ctx: ActionContext, step_name: str, result: StepResult) -> None:
        """Record a step result onto the action context.

        Args:
            ctx: The action context to update.
            step_name: The name of the step that produced the result.
            result: The step result to record.
        """
        field_name = self._FIELD_MAP.get(step_name)
        if field_name is not None:
            setattr(ctx, field_name, result)

    async def _record_to_ledger(self, ctx: ActionContext, result: StepResult) -> None:
        """Record a step execution to the ledger.

        Args:
            ctx: The action context for lineage data.
            result: The step result to record.
        """
        if self._ledger is None:
            return

        entry = PipelineStepEntry(
            step_name=result.step_name,
            request_id=ctx.request_id,
            actor_id=ctx.actor_id,
            action=ctx.action,
            verdict=str(result.verdict),
            duration_ms=result.duration_ms,
            message=result.message or "",
        )
        # Non-blocking: ledger is observability, must not block the pipeline.
        # Blocking here causes WAL checkpoint contention after ~5 events.
        ledger = self._ledger

        async def _write():
            try:
                await ledger.append(entry)
            except Exception:
                pass

        asyncio.create_task(_write())

    async def _publish_step_event(self, event: Event) -> None:
        """Publish a step-lifecycle event to the bus.

        Args:
            event: The event to publish.
        """
        if self._bus is None:
            return
        await self._bus.publish(event)
