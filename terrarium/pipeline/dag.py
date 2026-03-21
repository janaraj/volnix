"""DAG-based pipeline executor for the Terrarium framework.

Executes an ordered sequence of pipeline steps, threading an
:class:`~terrarium.core.ActionContext` through each step and recording
results to the event bus and ledger.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.context import ActionContext, StepResult
from terrarium.core.events import Event
from terrarium.core.protocols import LedgerProtocol, PipelineStep


class PipelineDAG:
    """Ordered pipeline of steps that process an action context.

    Each step is executed in sequence.  If a step returns a terminal verdict,
    the pipeline short-circuits and marks the context accordingly.
    """

    def __init__(
        self,
        steps: list[PipelineStep],
        bus: Any | None = None,
        ledger: LedgerProtocol | None = None,
    ) -> None:
        ...

    @property
    def step_names(self) -> list[str]:
        """Return the ordered list of step names in the pipeline.

        Returns:
            A list of step name strings.
        """
        ...

    async def execute(self, ctx: ActionContext) -> ActionContext:
        """Execute all pipeline steps against the given context.

        Steps are executed in order.  If a step yields a terminal verdict
        the pipeline short-circuits and returns the context immediately.

        Args:
            ctx: The mutable action context to process.

        Returns:
            The enriched action context after all (or short-circuited) steps.
        """
        ...

    def _record_result(self, ctx: ActionContext, step_name: str, result: StepResult) -> None:
        """Record a step result onto the action context.

        Args:
            ctx: The action context to update.
            step_name: The name of the step that produced the result.
            result: The step result to record.
        """
        ...

    async def _publish_step_event(self, event: Event) -> None:
        """Publish a step-lifecycle event to the bus.

        Args:
            event: The event to publish.
        """
        ...
