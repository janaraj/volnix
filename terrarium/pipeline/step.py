"""Base pipeline step class for the Terrarium framework.

Provides a concrete ABC that implements the :class:`~terrarium.core.protocols.PipelineStep`
protocol, adding timing helpers and a convenience method for constructing
:class:`~terrarium.core.context.StepResult` instances.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from terrarium.core.context import ActionContext, StepResult
from terrarium.core.types import EventId, StepVerdict


class BasePipelineStep(ABC):
    """Abstract base class for pipeline steps.

    Subclasses must override :attr:`step_name` and :meth:`execute`.
    The :meth:`_make_result` helper provides timing and consistent
    result construction.
    """

    step_name: ClassVar[str] = ""

    @abstractmethod
    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute this pipeline step.

        Args:
            ctx: The mutable action context.

        Returns:
            A :class:`StepResult` describing the outcome.
        """
        ...

    def _make_result(
        self,
        verdict: StepVerdict,
        message: str = "",
        events: list[EventId] | None = None,
        metadata: dict[str, Any] | None = None,
        duration_ms: float = 0.0,
    ) -> StepResult:
        """Construct a :class:`StepResult` with timing information.

        Args:
            verdict: The step outcome verdict.
            message: Human-readable explanation.
            events: Optional list of event IDs generated.
            metadata: Optional metadata dictionary.
            duration_ms: Wall-clock milliseconds the step took.

        Returns:
            A populated :class:`StepResult`.
        """
        return StepResult(
            step_name=self.step_name,
            verdict=verdict,
            message=message,
            events=events or [],
            metadata=metadata or {},
            duration_ms=duration_ms,
        )
