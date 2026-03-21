"""Side-effect processor for the Terrarium pipeline.

Handles deferred side effects generated during pipeline execution,
re-injecting them as new pipeline runs with bounded recursion depth.
"""

from __future__ import annotations

from terrarium.core.context import ActionContext
from terrarium.core.types import SideEffect
from terrarium.pipeline.dag import PipelineDAG


class SideEffectProcessor:
    """Processes queued side effects by re-running them through the pipeline.

    Supports bounded recursion to prevent infinite side-effect chains and
    can operate in both synchronous (process-all) and background modes.
    """

    def __init__(self, pipeline: PipelineDAG, max_depth: int = 10) -> None:
        ...

    async def enqueue(self, side_effect: SideEffect, parent_ctx: ActionContext) -> None:
        """Enqueue a side effect for processing.

        Args:
            side_effect: The side effect to process.
            parent_ctx: The action context that produced this side effect.
        """
        ...

    async def process_all(self) -> int:
        """Process all queued side effects synchronously.

        Returns:
            The number of side effects processed.
        """
        ...

    async def start_background(self) -> None:
        """Start processing side effects in a background task."""
        ...

    async def stop(self) -> None:
        """Stop background side-effect processing."""
        ...

    def _side_effect_to_context(
        self, se: SideEffect, parent_ctx: ActionContext
    ) -> ActionContext:
        """Convert a side effect into an action context for pipeline execution.

        Args:
            se: The side effect to convert.
            parent_ctx: The parent action context for lineage tracking.

        Returns:
            A new :class:`ActionContext` representing the side effect.
        """
        ...
