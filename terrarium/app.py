"""TerrariumApp -- bootstrap and orchestration for the full system."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from terrarium.bus.bus import EventBus
from terrarium.config.schema import TerrariumConfig
from terrarium.core.context import ActionContext
from terrarium.core.types import ActorId, ServiceId
from terrarium.ledger.ledger import Ledger
from terrarium.persistence.manager import ConnectionManager
from terrarium.pipeline.builder import build_pipeline_from_config
from terrarium.pipeline.dag import PipelineDAG
from terrarium.pipeline.side_effects import SideEffectProcessor
from terrarium.registry.composition import create_default_registry
from terrarium.registry.health import HealthAggregator
from terrarium.registry.registry import EngineRegistry
from terrarium.registry.wiring import wire_engines, shutdown_engines
from terrarium.validation.step import ValidationStep

logger = logging.getLogger(__name__)


class TerrariumApp:
    """Full Terrarium system bootstrap and lifecycle manager."""

    def __init__(self, config: TerrariumConfig | None = None) -> None:
        self._config = config or TerrariumConfig()
        self._conn_mgr: ConnectionManager | None = None
        self._bus: EventBus | None = None
        self._ledger: Ledger | None = None
        self._registry: EngineRegistry | None = None
        self._pipeline: PipelineDAG | None = None
        self._side_effects: SideEffectProcessor | None = None
        self._health: HealthAggregator | None = None
        self._started = False

    async def start(self) -> None:
        """Bootstrap the full system: persistence, bus, ledger, engines, pipeline."""
        try:
            # 1. Persistence
            self._conn_mgr = ConnectionManager(self._config.persistence)
            await self._conn_mgr.initialize()

            # 2. Event bus
            bus_db = await self._conn_mgr.get_connection("bus")
            self._bus = EventBus(self._config.bus, db=bus_db)
            await self._bus.initialize()

            # 3. Ledger
            ledger_db = await self._conn_mgr.get_connection("ledger")
            self._ledger = Ledger(self._config.ledger, ledger_db)
            await self._ledger.initialize()

            # 4. Engine registry + wiring
            self._registry = create_default_registry()
            await wire_engines(self._registry, self._bus, self._config)

            # Inject ledger into state engine post-wiring
            state_engine = self._registry.get("state")
            state_engine._ledger = self._ledger

            # 5. Build pipeline (bus and ledger passed via constructor)
            steps = self._registry.get_pipeline_steps()
            steps["validation"] = ValidationStep()  # Add standalone validation step
            self._pipeline = build_pipeline_from_config(
                self._config.pipeline, steps, bus=self._bus, ledger=self._ledger,
            )

            # 6. Side-effect processor
            self._side_effects = SideEffectProcessor(self._pipeline)

            # 7. Health
            self._health = HealthAggregator(self._registry)

            self._started = True
            logger.info("TerrariumApp started with %d engines", len(self._registry.list_engines()))
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Graceful shutdown in reverse order."""
        if self._registry:
            await shutdown_engines(self._registry)
        if self._ledger:
            await self._ledger.shutdown()
        if self._bus:
            await self._bus.shutdown()
        if self._conn_mgr:
            await self._conn_mgr.shutdown()
        self._started = False

    async def handle_action(
        self,
        actor_id: str,
        service_id: str,
        action: str,
        input_data: dict[str, Any],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Execute a single action through the full 7-step pipeline.

        This is the primary entry point for all agent interactions.

        Returns:
            The response body from the pack (or error dict on failure).

        Raises:
            RuntimeError: If the app has not been started or has been stopped.
        """
        if not self._started:
            raise RuntimeError("TerrariumApp is not started. Call start() first.")

        now = datetime.now(timezone.utc)
        ctx = ActionContext(
            request_id=f"req-{uuid.uuid4().hex[:12]}",
            actor_id=ActorId(actor_id),
            service_id=ServiceId(service_id),
            action=action,
            input_data=input_data,
            world_time=overrides.get("world_time", now),
            wall_time=now,
            tick=overrides.get("tick", 0),
        )

        await self._pipeline.execute(ctx)

        # Process any side effects proposed by packs
        if ctx.response_proposal and ctx.response_proposal.proposed_side_effects:
            for se in ctx.response_proposal.proposed_side_effects:
                await self._side_effects.enqueue(se, ctx)
            await self._side_effects.process_all()

        if ctx.short_circuited:
            step = ctx.short_circuit_step
            return {"error": f"Pipeline short-circuited at step '{step}'", "step": step}

        if ctx.response_proposal:
            return ctx.response_proposal.response_body
        return {"error": "No response produced"}

    @property
    def registry(self) -> EngineRegistry:
        return self._registry

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    @property
    def pipeline(self) -> PipelineDAG:
        return self._pipeline
