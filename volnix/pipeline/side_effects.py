"""Side-effect processor for the Volnix pipeline.

Handles deferred side effects generated during pipeline execution,
re-injecting them as new pipeline runs with bounded recursion depth.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from volnix.core.context import ActionContext
from volnix.core.types import SideEffect
from volnix.pipeline.dag import PipelineDAG

logger = logging.getLogger(__name__)


class SideEffectProcessor:
    """Processes queued side effects by re-running them through the pipeline.

    Supports bounded recursion to prevent infinite side-effect chains and
    can operate in both synchronous (process-all) and background modes.
    """

    def __init__(
        self,
        pipeline: PipelineDAG,
        max_depth: int = 10,
        max_total: int = 1000,
        poll_interval: float = 0.05,
    ) -> None:
        """Initialize the side-effect processor.

        Args:
            pipeline: The pipeline DAG to execute side effects through.
            max_depth: Maximum recursion depth for nested side effects.
                Callers should inject from ``PipelineConfig.side_effect_max_depth``
                when available; the default of 10 is a reasonable fallback.
            max_total: Maximum total side effects to process in one ``process_all`` call.
            poll_interval: Seconds to sleep between background loop iterations when
                the queue is empty.
        """
        self._pipeline = pipeline
        self._max_depth = max_depth
        self._max_total = max_total
        self._poll_interval = poll_interval
        self._queue: asyncio.Queue[tuple[SideEffect, ActionContext, int]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def enqueue(
        self,
        side_effect: SideEffect,
        parent_ctx: ActionContext,
        depth: int = 0,
    ) -> None:
        """Enqueue a side effect for processing.

        If *depth* has reached *max_depth*, the side effect is silently
        dropped to prevent infinite recursion.

        Args:
            side_effect: The side effect to process.
            parent_ctx: The action context that produced this side effect.
            depth: Current recursion depth (0 for top-level).
        """
        if depth >= self._max_depth:
            return
        self._queue.put_nowait((side_effect, parent_ctx, depth))

    async def process_all(self) -> int:
        """Process all queued side effects synchronously.

        Returns:
            The number of side effects processed.
        """
        count = 0
        while not self._queue.empty() and count < self._max_total:
            se, parent_ctx, depth = self._queue.get_nowait()
            ctx = self._side_effect_to_context(se, parent_ctx)
            try:
                result_ctx = await self._pipeline.execute(ctx)
            except Exception:
                # One failing side effect must not kill all processing.
                # The error is captured as an ERROR StepResult within the
                # pipeline's own exception handling, but if something
                # unexpected happens at a higher level, we skip and continue.
                continue
            count += 1

            # If the result has a response_proposal with proposed_side_effects,
            # re-enqueue them at depth + 1
            if result_ctx.response_proposal is not None:
                for nested_se in result_ctx.response_proposal.proposed_side_effects:
                    await self.enqueue(nested_se, result_ctx, depth=depth + 1)

        return count

    async def start_background(self) -> None:
        """Start processing side effects in a background task."""
        self._running = True
        self._task = asyncio.create_task(self._background_loop())

    async def stop(self) -> None:
        """Stop background side-effect processing."""
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _side_effect_to_context(self, se: SideEffect, parent_ctx: ActionContext) -> ActionContext:
        """Convert a side effect into an action context for pipeline execution.

        Args:
            se: The side effect to convert.
            parent_ctx: The parent action context for lineage tracking.

        Returns:
            A new :class:`ActionContext` representing the side effect.
        """
        return ActionContext(
            request_id=f"se_{uuid.uuid4().hex[:12]}",
            actor_id=parent_ctx.actor_id,
            service_id=se.target_service or parent_ctx.service_id,
            action=se.effect_type,
            input_data=dict(se.parameters),
            target_entity=se.target_entity,
            world_time=parent_ctx.world_time,
            wall_time=parent_ctx.wall_time,
            tick=parent_ctx.tick,
            run_id=parent_ctx.run_id,
            world_mode=parent_ctx.world_mode,
            reality_preset=parent_ctx.reality_preset,
            fidelity=parent_ctx.fidelity,
            computed_cost=parent_ctx.computed_cost,
            policy_flags=list(parent_ctx.policy_flags),
        )

    async def _background_loop(self) -> None:
        """Background loop: drain the queue continuously."""
        while self._running:
            if not self._queue.empty():
                try:
                    await self.process_all()
                except Exception:
                    logger.exception("Side effect processing failed")
            else:
                try:
                    await asyncio.sleep(self._poll_interval)
                except asyncio.CancelledError:
                    break
