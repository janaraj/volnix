"""TerrariumApp -- bootstrap and orchestration for the full system."""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terrarium.bus.bus import EventBus
from terrarium.config.schema import TerrariumConfig
from terrarium.core.context import ActionContext
from terrarium.core.errors import TerrariumError
from terrarium.core.types import ActorId, RunId, ServiceId, WorldId
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
        self._current_run_id: str | None = None
        self._current_world_id: str | None = None
        self._world_manager: Any = None
        self._actor_registry: Any = None
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

            # 5. Run management + artifacts (before engine wiring — engines need these)
            from terrarium.runs.artifacts import ArtifactStore as RunArtifactStore
            from terrarium.runs.manager import RunManager

            self._run_manager = RunManager(
                config=self._config.runs, persistence=self._conn_mgr,
            )
            self._artifact_store = RunArtifactStore(config=self._config.runs)

            from terrarium.worlds.manager import WorldManager
            self._world_manager = WorldManager(
                data_dir=self._config.worlds.data_dir,
            )

            # 6. Engine registry + wiring
            # Fix #8: inject state DB via ConnectionManager instead of
            # letting StateEngine construct SQLiteDatabase directly
            state_db = await self._conn_mgr.get_connection("state")
            self._registry = create_default_registry()
            await wire_engines(
                self._registry, self._bus, self._config,
                engine_overrides={"state": {"_db": state_db}},
            )

            # 7. Post-wiring dependency injection
            await self._inject_cross_engine_deps()

            # 7. Build pipeline (bus and ledger passed via constructor)
            steps = self._registry.get_pipeline_steps()
            steps["validation"] = ValidationStep(ledger=self._ledger)
            self._pipeline = build_pipeline_from_config(
                self._config.pipeline, steps, bus=self._bus, ledger=self._ledger,
            )

            # 8. Side-effect processor
            self._side_effects = SideEffectProcessor(self._pipeline)

            # 9. Health
            self._health = HealthAggregator(self._registry)

            # 10. Gateway
            from terrarium.gateway.gateway import Gateway
            self._gateway = Gateway(app=self, config=self._config.gateway)
            await self._gateway.initialize()

            # 11. Webhook delivery (optional — bus subscriber)
            self._webhook_manager = None
            if self._config.webhook.enabled:
                from terrarium.webhook.manager import WebhookManager

                self._webhook_manager = WebhookManager(
                    self._config.webhook
                )
                await self._webhook_manager.start(self._bus)

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

            # Pack registry + profile registry -> adapter engine (for capability checks)
            adapter_engine = self._registry.get("adapter")
            adapter_engine._pack_registry = pack_reg

            # Pack registry → permission engine (for read/write classification)
            permission_eng = self._registry.get("permission")
            permission_eng._pack_registry = pack_reg
            profile_reg = getattr(responder, "_profile_registry", None)
            if profile_reg is not None:
                adapter_engine._profile_registry = profile_reg

            # Create kernel for compiler if not already wired by _on_initialize
            from terrarium.kernel.registry import SemanticRegistry

            existing = getattr(compiler, "_compiler_resolver", None)
            existing_kernel = getattr(existing, "_kernel", None) if existing else None
            if existing_kernel is None:
                existing_kernel = SemanticRegistry()
                await existing_kernel.initialize()
                compiler._config["_kernel"] = existing_kernel

            # Gather profile loader from responder for Tier 2 resolution
            profile_loader = getattr(responder, "_profile_loader", None)

            # Build profile inferrer if LLM is available and infer is enabled
            profile_inferrer = None
            if self._llm_router and self._config.profiles.infer_on_missing:
                try:
                    from terrarium.kernel.context_hub import ContextHubProvider
                    from terrarium.kernel.openapi_provider import OpenAPIProvider
                    from terrarium.packs.profile_infer import ProfileInferrer

                    context_hub = ContextHubProvider()
                    openapi_provider = OpenAPIProvider()

                    profile_inferrer = ProfileInferrer(
                        llm_router=self._llm_router,
                        context_hub=context_hub if await context_hub.is_available() else None,
                        openapi_provider=openapi_provider,
                        kernel=existing_kernel,
                    )
                except Exception as exc:
                    logger.debug("ProfileInferrer not available: %s", exc)

            # Profile registry is shared across responder, adapter, and compiler
            # so that profiles inferred at compile time are immediately
            # available for runtime capability checks and response generation.
            profile_registry = getattr(responder, "_profile_registry", None)

            compiler._compiler_resolver = CompilerServiceResolver(
                pack_registry=pack_reg,
                kernel=existing_kernel,
                resolver=(
                    getattr(existing, "_resolver", None) if existing else None
                ),
                profile_loader=profile_loader,
                profile_inferrer=profile_inferrer,
                profile_registry=profile_registry,
                ledger=self._ledger,
                bus=self._bus,
            )

        compiler._config["_state_engine"] = state_engine
        actor_registry = ActorRegistry()
        self._actor_registry = actor_registry
        compiler._config["_actor_registry"] = actor_registry

        # Slot manager for external agent identity
        from terrarium.actors.slot_manager import SlotManager
        self._slot_manager = SlotManager(
            actor_registry=actor_registry,
            config=self._config.agents,
        )
        # Pass to gateway for HTTP/MCP token resolution
        if self._gateway:
            self._gateway._slot_manager = self._slot_manager
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
            ActorDefinition(
                id=ActorId("system"),
                type=ActorType.SYSTEM,
                role="animator",
                permissions={"read": "all", "write": "all"},
            ),
            ActorDefinition(
                id=ActorId("environment"),
                type=ActorType.SYSTEM,
                role="environment",
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
        reporter._dependencies["bus"] = self._bus

        # Shared scheduler + animator wiring
        from terrarium.scheduling.scheduler import WorldScheduler

        self._scheduler = WorldScheduler()
        animator = self._registry.get("animator")
        animator._config["_app"] = self
        animator._config["_actor_registry"] = actor_registry

        # Agency engine wiring
        agency = self._registry.get("agency")
        agency._config["_actor_registry"] = actor_registry
        if self._llm_router:
            agency._config["_llm_router"] = self._llm_router
        agency._ledger = self._ledger

        # Feedback engine wiring
        feedback = self._registry.get("feedback")
        feedback._config["_conn_mgr"] = self._conn_mgr
        feedback._ledger = self._ledger
        feedback._config["_artifact_store"] = self._artifact_store
        feedback._config["_profile_registry"] = getattr(
            responder, "_profile_registry", None
        )
        feedback._config["_profile_loader"] = getattr(
            responder, "_profile_loader", None
        )
        feedback._config["_run_manager"] = self._run_manager

    async def stop(self) -> None:
        """Graceful shutdown in reverse order."""
        if hasattr(self, "_webhook_manager") and self._webhook_manager:
            await self._webhook_manager.stop()
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
        self._world_manager = None
        self._current_world_id = None
        self._started = False

    async def build_kickstart_envelope(self, plan: Any) -> Any:
        """Build the initial mission envelope for internal-only simulations.

        Uses the state engine, actor registry, and pack registry to build
        a valid envelope with real entity IDs and correct tool names.
        Returns None if no communication service or no internal actors.
        """
        from terrarium.core.envelope import ActionEnvelope
        from terrarium.core.types import ActionSource, EnvelopePriority, ServiceId

        mission = getattr(plan, "mission", "")
        if not mission:
            return None

        # Find lead actor from registry
        lead_id = None
        if self._actor_registry:
            for actor in self._actor_registry.list_actors():
                if str(actor.type) in ("human", "system") and actor.role:
                    lead_id = actor.id
                    if actor.metadata.get("lead"):
                        break
        if lead_id is None:
            return None

        # Find postMessage tool from pack registry
        responder = self._registry.get("responder")
        service_id, action = None, None
        if hasattr(responder, "_pack_registry"):
            for tool in responder._pack_registry.list_tools():
                name = tool.get("name", "").lower()
                if "postmessage" in name:
                    service_id = tool.get("pack_name", "")
                    action = tool.get("name", "")
                    break
        if not service_id or not action:
            return None

        # Find the best channel for kickstart — prefer channels actors
        # are subscribed to (so the message triggers activations)
        from collections import Counter
        channel_counts: Counter = Counter()
        agency = self._registry.get("agency")
        if agency:
            for actor_state in getattr(agency, "_actor_states", {}).values():
                for sub in actor_state.subscriptions:
                    ch = sub.filter.get("channel") if hasattr(sub, "filter") else (sub.get("filter", {}).get("channel") if isinstance(sub, dict) else None)
                    if ch:
                        channel_counts[ch] += 1

        if channel_counts:
            channel_id = channel_counts.most_common(1)[0][0]
        else:
            # Fallback: query state engine for a general/team channel
            state = self._registry.get("state")
            channels = await state.query_entities("channel")
            channel_id = None
            for ch in channels:
                name = ch.get("name", "").lower()
                if name in ("general", "team"):
                    channel_id = ch.get("id")
                    break
            if channel_id is None and channels:
                channel_id = channels[0].get("id")

        if channel_id is None:
            return None

        logger.info(
            "Kickstart: actor=%s, action=%s, service=%s, channel=%s",
            lead_id, action, service_id, channel_id,
        )

        return ActionEnvelope(
            actor_id=lead_id,
            source=ActionSource.ENVIRONMENT,
            action_type=action,
            target_service=ServiceId(service_id),
            payload={
                "channel_id": channel_id,
                "channel": channel_id,  # subscription filters match on "channel"
                "text": f"[MISSION] {mission}",
                "intended_for": ["all"],
            },
            logical_time=0.0,
            priority=EnvelopePriority.ENVIRONMENT,
            metadata={"activation_reason": "kickstart"},
        )

    async def read_entities(
        self, actor_id: str, entity_type: str
    ) -> dict[str, Any]:
        """Read entities — read-only state access.

        Used by HTTP adapter for entity query endpoint.
        Keeps state access in the app layer (not in adapters).
        """
        state = self._registry.get("state")
        entities = await state.query_entities(entity_type)
        return {
            "entity_type": entity_type,
            "count": len(entities),
            "entities": entities,
        }

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

        # Resolve actor identity — auto-register unknown agents with defaults
        if self._slot_manager:
            actor_id = self._slot_manager.resolve_actor_id(actor_id)

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
            run_id=RunId(self._current_run_id) if self._current_run_id else None,
        )

        await self._pipeline.execute(ctx)

        # Publish event for short-circuited actions only. Successful actions
        # are already published by the commit step in StateEngine via the
        # pipeline DAG — publishing again here would create duplicates.
        # Also publish if no commit_result (pipeline had no commit step).
        if self._bus and (ctx.short_circuited or not ctx.commit_result):
            from terrarium.core.events import WorldEvent
            from terrarium.core.types import ActionSource, EntityId, EventId, Timestamp

            # Determine target_entity: prefer explicit, else from state deltas
            target = ctx.target_entity
            if target is None and ctx.response_proposal:
                deltas = ctx.response_proposal.proposed_state_deltas or []
                if deltas:
                    target = EntityId(str(deltas[0].entity_id))

            # Determine outcome from pipeline result
            outcome = "success"
            if ctx.short_circuited:
                sc_step = getattr(ctx, "short_circuit_step", "")
                outcome = f"blocked_at_{sc_step}" if sc_step else "blocked"

            # Copy reply_to_event_id from payload to causes for causal linking
            causes: list[EventId] = []
            reply_to = input_data.get("reply_to_event_id")
            if reply_to:
                causes.append(EventId(str(reply_to)))

            # Include response body on the event so downstream consumers
            # (agency notify, reporter) can see the service response
            response = (
                ctx.response_proposal.response_body
                if ctx.response_proposal and not ctx.short_circuited
                else None
            )

            event = WorldEvent(
                event_type=f"world.{action}",
                timestamp=Timestamp(
                    world_time=ctx.world_time or now,
                    wall_time=now,
                    tick=ctx.tick,
                ),
                actor_id=ActorId(actor_id),
                service_id=ServiceId(service_id),
                action=action,
                target_entity=target,
                input_data=input_data,
                response_body=response,
                source=ActionSource(ctx.source) if ctx.source else ActionSource.EXTERNAL,
                outcome=outcome,
                run_id=self._current_run_id,
                causes=causes,
            )
            try:
                await self._bus.publish(event)
            except Exception:
                pass  # Bus publish failure is non-fatal

        # Process any side effects proposed by packs
        if ctx.response_proposal and ctx.response_proposal.proposed_side_effects:
            for se in ctx.response_proposal.proposed_side_effects:
                await self._side_effects.enqueue(se, ctx)
            await self._side_effects.process_all()

        # Include the committed WorldEvent in the return so callers
        # (e.g. SimulationRunner) can pass it to agency.notify().
        # External callers (HTTP gateway) use only the response body.
        # For successful actions: get from commit step result.
        # For short-circuited actions: get from the event we just created above.
        committed_event = None
        if ctx.short_circuited and self._bus:
            committed_event = event  # created in the short_circuited block above
        elif ctx.commit_result and ctx.commit_result.events:
            committed_event = ctx.commit_result.events[0]  # from StateEngine commit
        logger.debug(
            "[handle_action] _event attached: type=%s, short_circuited=%s",
            type(committed_event).__name__, ctx.short_circuited,
        )

        if ctx.short_circuited:
            step = ctx.short_circuit_step
            return {
                "error": f"Pipeline short-circuited at step '{step}'",
                "step": step,
                "_event": committed_event,
            }

        if ctx.response_proposal:
            result = ctx.response_proposal.response_body
            if isinstance(result, dict):
                result["_event"] = committed_event
            return result
        return {"error": "No response produced", "_event": committed_event}

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

        # Filter gateway tools to only services defined in this world
        world_services = set(plan.services.keys()) if hasattr(plan, "services") else set()
        if self._gateway and world_services:
            self._gateway.set_active_services(world_services)

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

    async def configure_agency(self, plan: Any, result: dict) -> None:
        """Configure the AgencyEngine from compilation results.

        Creates ActorState for each internal actor, builds WorldContextBundle,
        extracts available actions from service packs.

        Handles gracefully if the agency engine is not registered.

        Args:
            plan: A WorldPlan object with actors, behavior, and mission.
            result: The compilation result dict from generate_world().
        """
        from terrarium.actors.state import ActorState
        from terrarium.actors.trait_extractor import extract_behavior_traits
        from terrarium.engines.world_compiler.generation_context import (
            WorldGenerationContext,
        )
        from terrarium.simulation.world_context import WorldContextBundle

        try:
            agency = self._registry.get("agency")
        except KeyError:
            logger.debug("Agency engine not registered — skipping configure_agency")
            return

        actors = result.get("actors", [])

        # Build WorldContextBundle from plan + generation context
        gen_ctx = WorldGenerationContext(plan)
        ctx_vars = gen_ctx.for_entity_generation()

        # Gather available actions from service packs — only for
        # services defined in this world (not all registered packs)
        world_services = set(plan.services.keys()) if hasattr(plan, "services") else set()
        available_actions: list[dict[str, Any]] = []
        try:
            responder = self._registry.get("responder")
            if hasattr(responder, "_pack_registry"):
                for tool_info in responder._pack_registry.list_tools():
                    pack_name = tool_info.get("pack_name", "")
                    # Only include tools from services in this world
                    if world_services and pack_name not in world_services:
                        continue
                    params = tool_info.get("parameters", {})
                    available_actions.append(
                        {
                            "name": tool_info.get("name", ""),
                            "description": tool_info.get("description", ""),
                            "service": pack_name,
                            "required_params": params.get("required", []),
                        }
                    )
        except KeyError:
            logger.debug("Responder engine not registered — no available actions")

        world_context = WorldContextBundle(
            world_description=getattr(plan, "description", ""),
            reality_summary=ctx_vars.get("reality_summary", ""),
            behavior_mode=getattr(plan, "behavior", "dynamic"),
            behavior_description=ctx_vars.get("behavior_description", ""),
            governance_rules_summary=ctx_vars.get("policies_summary", ""),
            mission=getattr(plan, "mission", "") or "",
            available_services=available_actions,
        )

        # Collect all entity IDs from compilation result for watched_entities
        all_entity_ids: list[str] = []
        for entity_type, entities in result.get("entities", {}).items():
            for entity in entities:
                eid = (
                    entity.get("id")
                    or entity.get(f"{entity_type}_id")
                    or entity.get("number")
                )
                if eid:
                    all_entity_ids.append(str(eid))

        # Create ActorState for each internal actor
        actor_states: list[ActorState] = []
        for actor_def in actors:
            if str(actor_def.type) in ("human", "system"):
                traits = extract_behavior_traits(actor_def)
                state = ActorState(
                    actor_id=actor_def.id,
                    role=actor_def.role,
                    actor_type="internal",
                    persona=(
                        actor_def.personality.model_dump()
                        if actor_def.personality
                        else {}
                    ),
                    behavior_traits=traits,
                    current_goal=actor_def.metadata.get("goal"),
                    goal_strategy=actor_def.metadata.get("goal_strategy"),
                )

                # Populate watched_entities: each actor watches a
                # deterministic ~30% subset of generated entities so
                # activation triggers when relevant entities change.
                if all_entity_ids:
                    actor_hash = int(
                        hashlib.md5(  # noqa: S324
                            str(actor_def.id).encode(),
                        ).hexdigest(),
                        16,
                    )
                    state.watched_entities = [
                        e
                        for i, e in enumerate(all_entity_ids)
                        if (actor_hash + i) % 3 == 0
                    ][:15]

                actor_states.append(state)

        # Set batch_threshold from config for each actor
        batch_threshold = self._config.agency.batch_threshold_default
        for state in actor_states:
            state.batch_threshold = batch_threshold

        # Apply subscriptions: use pre-generated from compilation result,
        # or generate via LLM if available
        if actor_states:
            pre_generated = result.get("subscriptions", {})

            if pre_generated:
                # Apply pre-generated subscriptions (no LLM needed).
                # Deserialize dicts to Subscription objects (JSON loses types).
                from terrarium.actors.state import Subscription as _Sub
                for state in actor_states:
                    actor_key = str(state.actor_id)
                    if actor_key in pre_generated:
                        state.subscriptions = [
                            _Sub.model_validate(s) if isinstance(s, dict) else s
                            for s in pre_generated[actor_key]
                        ]
                logger.info(
                    "Applied pre-generated subscriptions for %d actors",
                    sum(1 for s in actor_states if s.subscriptions),
                )
            elif self._llm_router:
                try:
                    from terrarium.engines.world_compiler.subscription_generator import (
                        SubscriptionGenerator,
                    )

                    sub_gen = SubscriptionGenerator(
                        llm_router=self._llm_router,
                        seed=getattr(plan, "seed", 42),
                    )
                    for state in actor_states:
                        actor_spec = {
                            "role": state.role,
                            "personality": state.persona,
                            "type": state.actor_type,
                        }
                        try:
                            subs = await sub_gen.generate_subscriptions(
                                actor_spec, plan,
                            )
                            state.subscriptions = subs
                        except Exception as exc:
                            logger.warning(
                                "Subscription generation failed for actor %s: %s",
                                state.actor_id,
                                exc,
                            )
                except Exception as exc:
                    logger.warning(
                        "Subscription generation unavailable: %s", exc,
                    )
            else:
                logger.info(
                    "No pre-generated subscriptions and no LLM router — "
                    "actors will have empty subscriptions"
                )

        # Schedule deliverable production for lead actor
        deliverable_cfg = getattr(plan, "deliverable_config", {})
        if deliverable_cfg and actor_states:
            from terrarium.deliverable_presets.loader import load_preset
            from terrarium.actors.state import ScheduledAction

            preset_name = deliverable_cfg.get("preset", "")
            preset = load_preset(preset_name) if preset_name else None

            if preset:
                # Find lead actor from actor_specs
                lead_state = None
                for state in actor_states:
                    spec = next(
                        (s for s in plan.actor_specs if s.get("role") == state.role),
                        {},
                    )
                    if spec.get("lead", False):
                        lead_state = state
                        break
                if lead_state is None:
                    lead_state = actor_states[0]

                # Calculate synthesis deadline
                max_ticks = self._config.simulation_runner.max_ticks
                buffer_pct = self._config.agency.synthesis_buffer_pct
                deadline_tick = int(max_ticks * (1 - buffer_pct))
                tick_interval = self._config.simulation_runner.tick_interval_seconds

                lead_state.goal_context = (
                    f"You are the designated lead for this collaboration. "
                    f"After the team has discussed sufficiently (around tick {deadline_tick}), "
                    f"you must produce a '{preset_name}' deliverable.\n\n"
                    f"{preset.get('prompt_instructions', '')}"
                )
                lead_state.scheduled_action = ScheduledAction(
                    logical_time=float(deadline_tick * tick_interval),
                    action_type="produce_deliverable",
                    description=f"Produce {preset_name} deliverable",
                    target_service=None,
                    payload={
                        "preset": preset_name,
                        "schema": preset.get("schema", {}),
                    },
                )
                logger.info(
                    "Scheduled %s deliverable for %s at tick %d",
                    preset_name, lead_state.actor_id, deadline_tick,
                )

        await agency.configure(actor_states, world_context, available_actions)

    async def compile_and_run(self, plan: Any) -> dict:
        """Compile world + configure all runtime engines in one call.

        Routes through the proper world/run separation:
        1. create_world(plan) — generate entities into world's own state.db
        2. create_run() — copy world state to run, configure runtime engines

        Returns the generation result dict for backward compatibility.
        """
        world_id = await self.create_world(plan)
        run_id = await self.create_run(plan, world_id=world_id)
        # Load from disk (not instance state)
        import json as _json
        gen_path = self._world_manager.get_world_dir(world_id) / "generation.json"
        return _json.loads(gen_path.read_text()) if gen_path.exists() else {}

    # ── Run management ─────────────────────────────────────────

    _GATEWAY_ACTORS = [
        {"id": "http-agent", "role": "agent", "type": "external",
         "permissions": {"read": "all", "write": "all"}},
        {"id": "mcp-agent", "role": "agent", "type": "external",
         "permissions": {"read": "all", "write": "all"}},
    ]

    # ── World lifecycle ───────────────────────────────────────

    async def create_world(self, plan: Any) -> WorldId:
        """Create a world — generate entities into the world's own state.db.

        This is the "stage setup." No agent has acted yet.
        The world's ``state.db`` is the pristine initial state.
        """
        plan_data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else {}
        world_id = await self._world_manager.create_world(
            name=getattr(plan, "name", "unnamed"),
            plan_data=plan_data,
            seed=getattr(plan, "seed", 42),
            services=list(plan.services.keys()) if hasattr(plan, "services") else [],
        )

        # Point state engine at the world's isolated DB
        state_engine = self._registry.get("state")
        world_db_path = self._world_manager.get_state_db_path(world_id)
        await state_engine.reconfigure(world_db_path)

        # Generate world (LLM → entities → populate_entities → world's state.db)
        compiler = self._registry.get("world_compiler")
        result = await compiler.generate_world(plan)

        # Save generation result alongside the world
        import json as _json

        def _serialize_result(obj: Any) -> Any:
            """Serialize Pydantic models and other objects for JSON storage."""
            if hasattr(obj, "model_dump"):
                return obj.model_dump(mode="json")
            return str(obj)

        world_dir = self._world_manager.get_world_dir(world_id)
        (world_dir / "generation.json").write_text(
            _json.dumps(result, indent=2, default=_serialize_result)
        )

        # Update world metadata with counts
        total_entities = sum(len(v) for v in result.get("entities", {}).values())
        actor_count = len(result.get("actors", []))
        await self._world_manager.mark_generated(world_id, total_entities, actor_count)

        self._current_world_id = str(world_id)

        return world_id

    async def create_run(
        self, plan: Any, mode: str = "governed", tag: str | None = None,
        world_id: WorldId | None = None,
        agents_yaml: str | None = None,
    ) -> RunId:
        """Create a run against an existing world.

        Copies the world's pristine ``state.db`` into the run's
        directory, then configures governance + animator + agency.
        If *world_id* is ``None``, creates a new world first
        (backward-compatible with the old single-call flow).
        """
        import shutil

        # Create world if not provided
        if world_id is None:
            world_id = await self.create_world(plan)

        # Validate world exists
        world = await self._world_manager.get_world(world_id)
        if world is None:
            raise TerrariumError(f"World '{world_id}' not found")

        # Serialize plan + inject gateway actors
        world_def = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else {}
        actors = world_def.get("actor_specs", world_def.get("actors", []))
        if isinstance(actors, list):
            existing_ids = {a.get("id") for a in actors if isinstance(a, dict)}
            for ga in self._GATEWAY_ACTORS:
                if ga["id"] not in existing_ids:
                    actors.append(ga)

        # Create run record (now includes world_id)
        run_id = await self._run_manager.create_run(
            world_id=str(world_id),
            world_def=world_def,
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

        # Copy world's pristine state.db → run's own state.db
        world_db = self._world_manager.get_state_db_path(world_id)
        if not Path(world_db).exists():
            raise TerrariumError(
                f"World '{world_id}' has no state.db — generation may have failed"
            )
        run_dir = Path(self._run_manager._data_dir) / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        run_db = str(run_dir / "state.db")

        # Close current state connection before copying the file
        state_engine = self._registry.get("state")
        if state_engine._db is not None:
            await state_engine._db.close()
            state_engine._db = None

        shutil.copy2(world_db, run_db)

        # Point state engine at the run's DB
        await state_engine.reconfigure(run_db)

        # Load generation result from the world's saved data (not instance state)
        import json as _json
        gen_path = self._world_manager.get_world_dir(world_id) / "generation.json"
        result = _json.loads(gen_path.read_text()) if gen_path.exists() else {}

        # Deserialize actors back to ActorDefinition objects (JSON loses types)
        # and register them in the actor registry (same as compiler does at
        # engine.py:374 during fresh generation — needed for permission checks)
        from terrarium.actors.definition import ActorDefinition
        if "actors" in result:
            result["actors"] = [
                ActorDefinition.model_validate(a) if isinstance(a, dict) else a
                for a in result["actors"]
            ]
            if self._actor_registry is not None:
                for actor_def in result["actors"]:
                    if not self._actor_registry.has_actor(actor_def.id):
                        self._actor_registry.register(actor_def)

        # Load external agent profiles if provided
        if agents_yaml and self._slot_manager:
            from terrarium.actors.profile import load_agent_profile
            agent_defs = load_agent_profile(agents_yaml)
            self._slot_manager.register_from_profile(agent_defs)

        self.configure_governance(plan)
        await self.configure_animator(plan)
        await self.configure_agency(plan, result)

        # Track active run
        self._current_run_id = str(run_id)
        await self._run_manager.start_run(run_id)

        # Save compilation result as run artifact
        await self._artifact_store.save_config(run_id, result)

        return run_id

    async def end_run(self, run_id: RunId) -> dict:
        """Complete a run: generate report, save artifacts, optional snapshot."""
        run = await self._run_manager.get_run(run_id)
        if run is None or run.get("status") != "running":
            raise ValueError(
                f"Cannot end run {run_id}: run is not in 'running' state"
            )

        world_def = run.get("world_def", {}) if run else {}
        actors_raw = world_def.get("actor_specs", world_def.get("actors", []))

        # Build actors list for reporter (explicit — not from global registry)
        actors_for_report = [
            {"id": a.get("id", ""), "type": a.get("type", ""), "role": a.get("role", "")}
            for a in actors_raw if isinstance(a, dict) and a.get("id")
        ]

        reporter = self._registry.get("reporter")
        report = await reporter.generate_full_report(actors=actors_for_report)
        scorecard = await reporter.generate_scorecard(actors=actors_for_report)

        await self._artifact_store.save_report(run_id, report)
        await self._artifact_store.save_scorecard(run_id, scorecard)

        # Save event log from bus (includes blocked/denied events)
        raw_events: list[dict] = []
        persistence = getattr(self._bus, "_persistence", None)
        if persistence:
            raw_events = await persistence.query_raw(
                filters={"run_id": str(run_id)},
            )
        await self._artifact_store.save_event_log(run_id, raw_events)

        state = self._registry.get("state")
        if self._config.runs.snapshot_on_complete:
            try:
                await state.snapshot(f"run_complete_{run_id}")
            except Exception as exc:
                logger.warning("Auto-snapshot failed for run %s: %s", run_id, exc)

        # Compute run summary
        services_raw = world_def.get("services", {})

        services_list: list[dict] = []
        if isinstance(services_raw, dict):
            for svc_id, svc_def in services_raw.items():
                entry: dict = {"id": svc_id}
                if isinstance(svc_def, dict):
                    entry["name"] = svc_def.get("name", svc_id)
                    entry["provider"] = svc_def.get("provider", "")
                    entry["category"] = svc_def.get("category", "")
                services_list.append(entry)

        ticks = [
            e.get("timestamp", {}).get("tick", 0)
            for e in raw_events
            if isinstance(e.get("timestamp"), dict)
        ]

        def _actor_to_dict(a: Any) -> dict:
            if isinstance(a, dict):
                return {"id": a.get("id", ""), "role": a.get("role", ""), "type": a.get("type", "")}
            return {"id": getattr(a, "id", ""), "role": getattr(a, "role", ""), "type": getattr(a, "type", "")}

        actors_summary = [_actor_to_dict(a) for a in actors_raw]

        summary = {
            "current_tick": max(ticks) if ticks else 0,
            "event_count": len(raw_events),
            "actor_count": len(actors_summary),
            "governance_score": scorecard.get("collective", {}).get("overall_score")
            if isinstance(scorecard, dict)
            else None,
            "services": services_list,
            "conditions": world_def.get("conditions", world_def.get("reality_dimensions", {})),
            "description": world_def.get("description", world_def.get("name", "")),
            "actors": actors_summary,
        }

        await self._run_manager.complete_run(run_id, summary=summary)
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

    @property
    def config(self) -> TerrariumConfig:
        return self._config

    @property
    def health(self) -> HealthAggregator | None:
        return self._health

    @property
    def actor_registry(self) -> Any:
        return self._actor_registry

    @property
    def world_manager(self) -> Any:
        return self._world_manager
