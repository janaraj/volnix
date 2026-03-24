"""TerrariumApp -- bootstrap and orchestration for the full system."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from terrarium.bus.bus import EventBus
from terrarium.config.schema import TerrariumConfig
from terrarium.core.context import ActionContext
from terrarium.core.types import ActorId, RunId, ServiceId
from terrarium.ledger.ledger import Ledger
from terrarium.persistence.manager import ConnectionManager
from terrarium.pipeline.builder import build_pipeline_from_config
from terrarium.pipeline.dag import PipelineDAG
from terrarium.pipeline.side_effects import SideEffectProcessor
from terrarium.registry.composition import create_default_registry
from terrarium.registry.health import HealthAggregator
from terrarium.registry.registry import EngineRegistry
from terrarium.registry.wiring import shutdown_engines, wire_engines
from terrarium.validation.step import ValidationStep

if TYPE_CHECKING:
    from terrarium.gateway.gateway import Gateway
    from terrarium.runs.artifacts import ArtifactStore
    from terrarium.runs.manager import RunManager
    from terrarium.scheduling.scheduler import WorldScheduler

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
        self._gateway: Any = None
        self._scheduler: Any = None
        self._run_manager: Any = None
        self._artifact_store: Any = None
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

            # 9.5. Run management
            from terrarium.runs.artifacts import ArtifactStore as RunArtifactStore
            from terrarium.runs.manager import RunManager

            self._run_manager = RunManager(
                config=self._config.runs, persistence=self._conn_mgr,
            )
            self._artifact_store = RunArtifactStore(config=self._config.runs)

            # 10. Gateway
            from terrarium.gateway.gateway import Gateway
            self._gateway = Gateway(app=self, config=self._config.gateway)
            await self._gateway.initialize()

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

            # Pack registry -> adapter engine (for capability checks)
            adapter_engine = self._registry.get("adapter")
            adapter_engine._pack_registry = pack_reg

            # Create kernel for compiler if not already wired by _on_initialize
            from terrarium.kernel.registry import SemanticRegistry

            existing = getattr(compiler, "_compiler_resolver", None)
            existing_kernel = getattr(existing, "_kernel", None) if existing else None
            if existing_kernel is None:
                existing_kernel = SemanticRegistry()
                await existing_kernel.initialize()
                compiler._config["_kernel"] = existing_kernel

            compiler._compiler_resolver = CompilerServiceResolver(
                pack_registry=pack_reg,
                kernel=existing_kernel,
                resolver=(
                    getattr(existing, "_resolver", None) if existing else None
                ),
            )

        compiler._config["_state_engine"] = state_engine
        actor_registry = ActorRegistry()
        compiler._config["_actor_registry"] = actor_registry
        compiler._ledger = self._ledger  # Same pattern as state_engine

        # Register default gateway actors so HTTP/MCP defaults go through governance
        from terrarium.actors.definition import ActorDefinition
        from terrarium.core.types import ActorType

        default_gateway_actors = [
            ActorDefinition(
                id=ActorId("http-agent"),
                type=ActorType.AGENT,
                role="gateway-default",
                permissions={"read": "all", "write": "all"},
            ),
            ActorDefinition(
                id=ActorId("mcp-agent"),
                type=ActorType.AGENT,
                role="gateway-default",
                permissions={"read": "all", "write": "all"},
            ),
        ]
        for actor_def in default_gateway_actors:
            if not actor_registry.has_actor(actor_def.id):
                actor_registry.register(actor_def)

        # Governance engines need actor_registry for permission/budget lookups
        policy_engine = self._registry.get("policy")
        permission_engine = self._registry.get("permission")
        budget_engine = self._registry.get("budget")

        policy_engine._actor_registry = actor_registry
        permission_engine._actor_registry = actor_registry
        budget_engine._actor_registry = actor_registry

        # Re-initialize compiler's LLM-dependent components with wired router
        if self._llm_router:
            compiler._llm_router = self._llm_router
            from terrarium.engines.world_compiler.nl_parser import NLParser

            compiler._nl_parser = NLParser(self._llm_router)

        # Reporter engine wiring
        reporter = self._registry.get("reporter")
        reporter._ledger = self._ledger
        reporter._config["_actor_registry"] = actor_registry

        # Shared scheduler + animator wiring
        from terrarium.scheduling.scheduler import WorldScheduler

        self._scheduler = WorldScheduler()
        animator = self._registry.get("animator")
        animator._config["_app"] = self
        animator._config["_actor_registry"] = actor_registry

    async def stop(self) -> None:
        """Graceful shutdown in reverse order."""
        if self._gateway:
            await self._gateway.shutdown()
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
        self._run_manager = None
        self._artifact_store = None
        self._scheduler = None
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

        now = datetime.now(UTC)
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

    def configure_governance(self, plan: Any) -> None:
        """Inject governance state from a WorldPlan after world compilation.

        Sets policies, world_mode, and actor_registry on governance engines.
        Call this after generate_world() completes.

        Args:
            plan: A WorldPlan object with policies, mode, and actor_specs.
        """
        policy_engine = self._registry.get("policy")
        permission_engine = self._registry.get("permission")
        budget_engine = self._registry.get("budget")

        mode = getattr(plan, "mode", "governed")

        if hasattr(policy_engine, "_policies"):
            policy_engine._policies = getattr(plan, "policies", [])
        if hasattr(policy_engine, "_world_mode"):
            policy_engine._world_mode = mode
        if hasattr(permission_engine, "_world_mode"):
            permission_engine._world_mode = mode
        if hasattr(budget_engine, "_world_mode"):
            budget_engine._world_mode = mode

    async def configure_animator(self, plan: Any) -> None:
        """Configure the animator engine from a compiled WorldPlan.

        Creates the AnimatorContext, registers scheduled events from YAML,
        and creates the organic generator if LLM is available.

        Call this after generate_world() and configure_governance().

        Args:
            plan: A WorldPlan object with conditions, behavior, and animator_settings.
        """
        animator = self._registry.get("animator")
        await animator.configure(plan, self._scheduler)

    async def compile_and_run(self, plan: Any) -> dict:
        """Compile world + configure all runtime engines in one call.

        Convenience wrapper that does:
        1. generate_world(plan) — LLM generation + validation + snapshot
        2. configure_governance(plan) — policies + permissions + budgets
        3. configure_animator(plan) — behavior mode + dimensions + scheduler

        This is the recommended single entry point for users.
        """
        compiler = self._registry.get("world_compiler")
        result = await compiler.generate_world(plan)
        self.configure_governance(plan)
        await self.configure_animator(plan)
        return result

    # ── Run management ─────────────────────────────────────────

    async def create_run(
        self, plan: Any, mode: str = "governed", tag: str | None = None,
    ) -> RunId:
        """Create a run record, compile the world, and start the run."""
        run_id = await self._run_manager.create_run(
            world_def=(
                plan.model_dump(mode="json") if hasattr(plan, "model_dump") else {}
            ),
            config_snapshot={
                "seed": plan.seed,
                "behavior": plan.behavior,
                "mode": getattr(plan, "mode", mode),
            },
            mode=mode,
            reality_preset=getattr(plan, "reality_preset", ""),
            fidelity_mode=getattr(plan, "fidelity", "auto"),
            tag=tag,
        )

        result = await self.compile_and_run(plan)
        await self._run_manager.start_run(run_id)
        await self._artifact_store.save_config(run_id, result)
        return run_id

    async def end_run(self, run_id: RunId) -> dict:
        """Complete a run: generate report, save artifacts, optional snapshot."""
        run = await self._run_manager.get_run(run_id)
        if run is None or run.get("status") != "running":
            raise ValueError(
                f"Cannot end run {run_id}: run is not in 'running' state"
            )
        reporter = self._registry.get("reporter")
        report = await reporter.generate_full_report()
        scorecard = await reporter.generate_scorecard()

        await self._artifact_store.save_report(run_id, report)
        await self._artifact_store.save_scorecard(run_id, scorecard)

        state = self._registry.get("state")
        events = await state.get_timeline()
        await self._artifact_store.save_event_log(run_id, events)

        if self._config.runs.snapshot_on_complete:
            try:
                await state.snapshot(f"run_complete_{run_id}")
            except Exception as exc:
                logger.warning("Auto-snapshot failed for run %s: %s", run_id, exc)

        await self._run_manager.complete_run(run_id)
        return {"run_id": str(run_id), "report": report, "scorecard": scorecard}

    async def diff_runs(self, run_ids: list[str]) -> dict:
        """Compare multiple runs using saved artifacts."""
        from terrarium.runs.comparison import RunComparator

        comparator = RunComparator(self._artifact_store)
        return await comparator.compare([RunId(rid) for rid in run_ids])

    async def diff_governed_ungoverned(
        self, gov_tag: str, ungov_tag: str,
    ) -> dict:
        """Specialized governed vs ungoverned comparison."""
        from terrarium.runs.comparison import RunComparator

        comparator = RunComparator(self._artifact_store)
        gov_run = await self._run_manager.get_run(RunId(gov_tag))
        ungov_run = await self._run_manager.get_run(RunId(ungov_tag))
        if not gov_run or not ungov_run:
            raise ValueError(
                f"Could not resolve run tags: {gov_tag}, {ungov_tag}"
            )
        return await comparator.compare_governed_ungoverned(
            RunId(gov_run["run_id"]), RunId(ungov_run["run_id"]),
        )

    # ── Properties ──────────────────────────────────────────────

    @property
    def scheduler(self) -> WorldScheduler:
        """The shared WorldScheduler instance."""
        return self._scheduler

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
    def gateway(self) -> Gateway:
        return self._gateway

    @property
    def pipeline(self) -> PipelineDAG:
        return self._pipeline

    @property
    def run_manager(self) -> RunManager:
        return self._run_manager

    @property
    def artifact_store(self) -> ArtifactStore:
        return self._artifact_store
