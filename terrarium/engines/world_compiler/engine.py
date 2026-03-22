"""World compiler engine implementation.

Compiles world definitions from YAML files or natural-language descriptions,
resolves service schemas, and generates seed data for new worlds.

D4a: Input → Parse → Resolve → WorldPlan (this phase)
D4b: WorldPlan → Generate → Validate → Populate (next phase)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from datetime import datetime, timezone

from terrarium.core import ActorId, BaseEngine, Event, ServiceId, Timestamp, WorldEvent
from terrarium.core.errors import CompilerError
from terrarium.engines.world_compiler.config import WorldCompilerConfig
from terrarium.engines.world_compiler.nl_parser import NLParser
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.engines.world_compiler.service_resolution import CompilerServiceResolver
from terrarium.engines.world_compiler.yaml_parser import YAMLParser
from terrarium.engines.world_compiler.generation_context import WorldGenerationContext
from terrarium.reality.expander import ConditionExpander

logger = logging.getLogger(__name__)


class WorldCompilerEngine(BaseEngine):
    """Compiles world definitions and generates seed data."""

    engine_name: ClassVar[str] = "world_compiler"
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state"]

    # -- BaseEngine hooks ------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Wire sub-components."""
        # Deserialize typed config (ignore private keys injected at runtime)
        self._typed_config = WorldCompilerConfig(
            **{k: v for k, v in self._config.items() if not k.startswith("_")}
        )

        self._condition_expander = ConditionExpander()
        self._yaml_parser = YAMLParser(self._condition_expander)

        # LLM router (optional — NL parsing needs it)
        self._llm_router = self._config.get("_llm_router")
        if not self._llm_router:
            logger.warning("WorldCompiler: no LLM router — NL parsing will be unavailable")
        self._nl_parser = NLParser(self._llm_router) if self._llm_router else None

        # Service resolution (optional — needs kernel + packs)
        self._compiler_resolver = None
        kernel = self._config.get("_kernel")
        pack_registry = self._config.get("_pack_registry")
        service_resolver = self._config.get("_service_resolver")
        if not kernel:
            logger.warning("WorldCompiler: no kernel — service resolution will be limited")
        if kernel:
            self._compiler_resolver = CompilerServiceResolver(
                pack_registry=pack_registry,
                kernel=kernel,
                resolver=service_resolver,
            )

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        logger.debug("WorldCompiler received event: %s", event.event_type)

    # -- D4a: Compilation (planning + resolution) ------------------------------

    async def compile_from_yaml(
        self,
        world_def_path: str,
        settings_path: str | None = None,
    ) -> WorldPlan:
        """YAML files → WorldPlan (D4a)."""
        partial, specs = await self._yaml_parser.parse(world_def_path, settings_path)
        return await self._resolve_and_assemble(partial, specs)

    async def compile_from_nl(
        self,
        description: str,
        reality: str = "messy",
        behavior: str = "dynamic",
        fidelity: str = "auto",
        seed: int | None = None,
    ) -> WorldPlan:
        """NL description → WorldPlan (D4a)."""
        if not self._nl_parser:
            raise CompilerError("NL parsing requires an LLM router")

        if seed is None:
            seed = self._typed_config.default_seed

        # Provide context about available services
        categories = ""
        verified_packs = ""
        if self._compiler_resolver:
            categories = self._compiler_resolver.get_available_categories()
            verified_packs = self._compiler_resolver.get_available_packs()

        world_def, settings = await self._nl_parser.parse(
            description, reality, behavior, fidelity, seed,
            categories=categories, verified_packs=verified_packs,
        )
        partial, specs = await self._yaml_parser.parse_from_dicts(world_def, settings)
        # Override source
        partial = partial.model_copy(update={"source": "nl"})
        return await self._resolve_and_assemble(partial, specs)

    async def _resolve_and_assemble(
        self,
        partial: WorldPlan,
        service_specs: dict[str, Any],
    ) -> WorldPlan:
        """Resolve services and assemble final WorldPlan."""
        if not self._compiler_resolver:
            return partial.model_copy(update={
                "warnings": list(partial.warnings) + ["No service resolver available"],
            })

        resolutions, warnings = await self._compiler_resolver.resolve_all(
            service_specs, partial.fidelity,
        )

        return partial.model_copy(update={
            "services": resolutions,
            "warnings": list(partial.warnings) + warnings,
        })

    # -- D4b: Generation (entity creation + population) -----------------------

    async def generate_world(self, plan: WorldPlan) -> dict[str, Any]:
        """Generate entities from WorldPlan, validate, inject seeds, populate state.

        Full orchestration of compiler steps 4-7:
          4. GENERATE — entities via LLM + actors via personality generator
          5. VALIDATE — B1 schema + state machine validation
          6. INJECT SEEDS — expand NL seeds, apply to entities
          7. POPULATE — store in StateEngine, register actors, snapshot

        Returns dict with keys: entities, actors, warnings, seeds_processed,
        snapshot_id, report.
        """
        if not self._llm_router:
            raise CompilerError(
                "Cannot generate world without LLM. "
                "Set GOOGLE_API_KEY environment variable and configure "
                "llm.providers in terrarium.toml"
            )
        logger.info("Generating world '%s' (behavior=%s)", plan.name, plan.behavior)

        from terrarium.engines.world_compiler.data_generator import WorldDataGenerator
        from terrarium.engines.world_compiler.personality_generator import (
            CompilerPersonalityGenerator,
        )
        from terrarium.engines.world_compiler.seed_processor import CompilerSeedProcessor
        from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer

        # Assemble generation context ONCE — shared by all generators
        ctx = WorldGenerationContext(plan)

        # Step 4: GENERATE entities
        data_gen = WorldDataGenerator(
            llm_router=self._llm_router,
            seed=plan.seed,
        )
        all_entities = await data_gen.generate(plan, ctx)

        # Step 4b: GENERATE actors with personalities
        personality_gen = CompilerPersonalityGenerator(
            llm_router=self._llm_router,
            seed=plan.seed,
        )
        actors = await personality_gen.generate_batch(
            plan.actor_specs,
            plan.conditions,
            ctx,
        )

        # Step 5: VALIDATE
        warnings = data_gen.validate(all_entities, plan)
        if warnings:
            logger.warning(
                "Entity validation produced %d warnings", len(warnings)
            )

        # Step 6: INJECT SEEDS
        seed_processor = CompilerSeedProcessor(llm_router=self._llm_router)
        if plan.seeds:
            all_entities = await seed_processor.process_all(
                plan.seeds, all_entities, ctx
            )
            # Re-validate after seed injection
            post_seed_warnings = data_gen.validate(all_entities, plan)
            warnings.extend(post_seed_warnings)

        # Step 7: POPULATE state engine + register actors
        snapshot_id = None
        state_engine = self._config.get("_state_engine")
        actor_registry = self._config.get("_actor_registry")

        if state_engine and hasattr(state_engine, "populate_entities"):
            entity_count = await state_engine.populate_entities(all_entities)
            logger.info("Populated %d entities into state engine", entity_count)
            snapshot_id = await state_engine.snapshot("initial_world")
        else:
            logger.warning(
                "No state engine available — entities not persisted"
            )

        if actor_registry and actors:
            actor_registry.register_batch(actors)
            logger.info("Registered %d actors", len(actors))

            # Publish actor registration events via bus (BaseEngine.publish)
            now = datetime.now(timezone.utc)
            for actor in actors:
                event = WorldEvent(
                    event_type="world.actor_registered",
                    timestamp=Timestamp(
                        world_time=now, wall_time=now, tick=0
                    ),
                    actor_id=ActorId("world_compiler"),
                    service_id=ServiceId("world_compiler"),
                    action="register_actor",
                    target_entity=None,
                    input_data={
                        "actor_id": str(actor.id),
                        "role": actor.role,
                        "type": str(actor.type),
                        "has_friction": actor.friction_profile is not None,
                    },
                )
                await self.publish(event)

            # Record summary to ledger
            ledger = getattr(self, "_ledger", None)
            if ledger is not None:
                from terrarium.ledger.entries import EngineLifecycleEntry

                entry = EngineLifecycleEntry(
                    engine_name="world_compiler",
                    event_type="actors_registered",
                    details={
                        "count": len(actors),
                        "roles": list(set(a.role for a in actors)),
                    },
                )
                await ledger.append(entry)
        elif actors:
            logger.warning(
                "No actor registry available — %d actors not registered",
                len(actors),
            )

        # Build result
        result: dict[str, Any] = {
            "entities": all_entities,
            "actors": actors,
            "warnings": warnings,
            "seeds_processed": len(plan.seeds),
            "snapshot_id": str(snapshot_id) if snapshot_id else None,
        }

        # Generate report
        reviewer = PlanReviewer()
        result["report"] = reviewer.generate_report(plan, result)

        # Publish generation complete event
        await self.publish(WorldEvent(
            event_type="world.generation_complete",
            timestamp=Timestamp(
                world_time=datetime.now(timezone.utc),
                wall_time=datetime.now(timezone.utc),
                tick=0,
            ),
            actor_id=ActorId("world_compiler"),
            service_id=ServiceId("world_compiler"),
            action="generate_world",
            input_data={
                "entity_count": sum(
                    len(v) for v in all_entities.values()
                ),
                "actor_count": len(actors),
                "seeds_processed": len(plan.seeds),
                "snapshot_id": str(snapshot_id) if snapshot_id else None,
            },
        ))

        return result

    async def resolve_service_schema(
        self, service_name: str
    ) -> dict[str, Any]:
        """Resolve and return the schema for a named service."""
        if not self._compiler_resolver:
            raise CompilerError("No service resolver available")
        resolution = await self._compiler_resolver.resolve_one(
            service_name, service_name, "auto"
        )
        if resolution is None:
            raise CompilerError(f"Could not resolve service: {service_name}")
        return resolution.surface.model_dump()

    async def expand_reality(
        self, preset: str, overrides: dict[str, Any] | None = None
    ) -> Any:
        """Expand reality preset + overrides into WorldConditions."""
        return self._condition_expander.expand(preset, overrides)
