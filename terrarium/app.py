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
        self._provider_registry: Any = None
        self._llm_router: Any = None
        self._started = False

    async def start(self) -> None:
        """Bootstrap the full system: persistence, bus, ledger, LLM, engines, pipeline."""
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

            # 4. LLM infrastructure (before engines — engines may need it)
            self._llm_router = await self._initialize_llm()

            # 5. Engine registry + wiring
            self._registry = create_default_registry()
            await wire_engines(self._registry, self._bus, self._config)

            # 6. Post-wiring dependency injection
            await self._inject_cross_engine_deps()

            # 7. Build pipeline (bus and ledger passed via constructor)
            steps = self._registry.get_pipeline_steps()
            steps["validation"] = ValidationStep()
            self._pipeline = build_pipeline_from_config(
                self._config.pipeline, steps, bus=self._bus, ledger=self._ledger,
            )

            # 8. Side-effect processor
            self._side_effects = SideEffectProcessor(self._pipeline)

            # 9. Health
            self._health = HealthAggregator(self._registry)

            self._started = True
            logger.info(
                "TerrariumApp started with %d engines",
                len(self._registry.list_engines()),
            )
        except Exception:
            await self.stop()
            raise

    async def _initialize_llm(self) -> Any:
        """Initialize LLM providers from terrarium.toml config.

        Uses: ProviderRegistry.initialize_all() (terrarium/llm/registry.py:54)
        Uses: LLMRouter(config, registry) (terrarium/llm/router.py:19)
        Uses: EnvVarResolver (terrarium/llm/secrets.py:32)

        Returns LLMRouter or None if no providers configured.
        """
        from terrarium.llm.registry import ProviderRegistry
        from terrarium.llm.router import LLMRouter
        from terrarium.llm.secrets import EnvVarResolver

        llm_config = self._config.llm
        if not llm_config.providers:
            logger.info("No LLM providers configured — LLM features disabled")
            return None

        self._provider_registry = ProviderRegistry()
        resolver = EnvVarResolver()
        await self._provider_registry.initialize_all(llm_config, resolver)

        router = LLMRouter(config=llm_config, registry=self._provider_registry)
        active = [p.name for p in self._provider_registry.list_providers()]
        logger.info(
            "LLM initialized: providers=%s, default=%s/%s",
            active,
            llm_config.defaults.type,
            llm_config.defaults.default_model,
        )
        return router

    async def _inject_cross_engine_deps(self) -> None:
        """Inject cross-engine dependencies after wiring.

        Uses: ActorRegistry (terrarium/actors/registry.py)
        Uses: CompilerServiceResolver (terrarium/engines/world_compiler/service_resolution.py)
        Uses: NLParser (terrarium/engines/world_compiler/nl_parser.py)
        """
        from terrarium.actors.registry import ActorRegistry
        from terrarium.engines.world_compiler.service_resolution import (
            CompilerServiceResolver,
        )

        # Ledger → state engine
        state_engine = self._registry.get("state")
        state_engine._ledger = self._ledger

        # LLM router → ALL engines that need it
        if self._llm_router:
            for engine_name in self._registry.list_engines():
                engine = self._registry.get(engine_name)
                engine._config["_llm_router"] = self._llm_router

        # Pack registry + state + actor registry → world compiler
        compiler = self._registry.get("world_compiler")
        responder = self._registry.get("responder")

        if hasattr(responder, "_pack_registry"):
            pack_reg = responder._pack_registry
            compiler._config["_pack_registry"] = pack_reg
            # Preserve kernel/resolver from _on_initialize (engine.py:54-64)
            existing = getattr(compiler, "_compiler_resolver", None)
            compiler._compiler_resolver = CompilerServiceResolver(
                pack_registry=pack_reg,
                kernel=(
                    getattr(existing, "_kernel", None) if existing else None
                ),
                resolver=(
                    getattr(existing, "_resolver", None) if existing else None
                ),
            )

        compiler._config["_state_engine"] = state_engine
        compiler._config["_actor_registry"] = ActorRegistry()
        compiler._ledger = self._ledger  # Same pattern as state_engine

        # Re-initialize compiler's LLM-dependent components with wired router
        if self._llm_router:
            compiler._llm_router = self._llm_router
            from terrarium.engines.world_compiler.nl_parser import NLParser

            compiler._nl_parser = NLParser(self._llm_router)

    async def stop(self) -> None:
        """Graceful shutdown in reverse order."""
        if self._provider_registry:
            await self._provider_registry.shutdown_all()
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
        """Execute a single action through the full 7-step pipeline."""
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
            return {
                "error": f"Pipeline short-circuited at step '{step}'",
                "step": step,
            }

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
