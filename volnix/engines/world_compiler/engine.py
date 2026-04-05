"""World compiler engine implementation.

Compiles world definitions from YAML files or natural-language descriptions,
resolves service schemas, and generates seed data for new worlds.

D4a: Input → Parse → Resolve → WorldPlan (this phase)
D4b: WorldPlan → Generate → Validate → Populate (next phase)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from volnix.core import ActorId, BaseEngine, Event, ServiceId, Timestamp, WorldEvent
from volnix.core.errors import CompilerError, WorldGenerationValidationError
from volnix.engines.world_compiler.config import WorldCompilerConfig
from volnix.engines.world_compiler.generation_context import WorldGenerationContext
from volnix.engines.world_compiler.nl_parser import NLParser
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.engines.world_compiler.service_resolution import CompilerServiceResolver
from volnix.engines.world_compiler.validator import SectionValidationResult
from volnix.engines.world_compiler.yaml_parser import YAMLParser
from volnix.reality.expander import ConditionExpander

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

        # Auto-include chat service when internal actors exist
        chat_auto_included = False
        if self._typed_config.auto_include_chat:
            original_specs = service_specs
            service_specs = self._maybe_auto_include_chat(
                partial, service_specs,
            )
            chat_auto_included = service_specs is not original_specs

        resolutions, warnings = await self._compiler_resolver.resolve_all(
            service_specs, partial.fidelity,
        )

        updates: dict[str, Any] = {
            "services": resolutions,
            "warnings": list(partial.warnings) + warnings,
        }

        # Add team channel seed when chat was auto-included
        if chat_auto_included and "chat" in resolutions:
            team_seed = self._build_team_channel_seed(partial)
            updates["seeds"] = list(partial.seeds) + [team_seed]

        return partial.model_copy(update=updates)

    def _maybe_auto_include_chat(
        self,
        partial: WorldPlan,
        service_specs: dict[str, Any],
    ) -> dict[str, Any]:
        """Auto-include chat service when internal actors exist and chat is not already defined.

        Returns the (possibly augmented) service_specs dict.
        """
        # Check if world has internal actors
        has_internal = any(
            spec.get("type", "external") == "internal"
            for spec in partial.actor_specs
        )
        if not has_internal:
            return service_specs

        # Check if chat service is already defined (by name or category)
        chat_names = {"chat", "slack", "teams", "discord", "messaging"}
        existing_names = {name.lower() for name in service_specs}
        if existing_names & chat_names:
            return service_specs

        # Add chat service via verified/slack pack
        logger.info(
            "Auto-including chat service for world with internal actors"
        )
        updated_specs = dict(service_specs)
        updated_specs["chat"] = "verified/slack"
        return updated_specs

    def _build_team_channel_seed(self, partial: WorldPlan) -> str:
        """Build a seed description for the auto-included team channel."""
        roles = [spec.get("role", "actor") for spec in partial.actor_specs]
        role_list = ", ".join(roles[:5])
        mission_snippet = (partial.mission or "team collaboration")[:100]
        return (
            f"A #team channel exists in the chat service where all actors "
            f"({role_list}) coordinate. The channel topic is related to: "
            f"{mission_snippet}"
        )

    async def compile_from_dicts(
        self,
        world_def: dict[str, Any],
        settings: dict[str, Any] | None = None,
    ) -> WorldPlan:
        """Compile a WorldPlan from in-memory dicts (public API for replay)."""
        partial, specs = await self._yaml_parser.parse_from_dicts(
            world_def, settings or {},
        )
        return await self._resolve_and_assemble(partial, specs)

    # -- D4b: Generation (entity creation + population) -----------------------

    async def generate_world(self, plan: WorldPlan) -> dict[str, Any]:
        """Generate entities from WorldPlan and snapshot only after hard validation."""
        if not self._llm_router:
            raise CompilerError(
                "Cannot generate world without LLM. "
                "Set GOOGLE_API_KEY environment variable and configure "
                "llm.providers in volnix.toml"
            )
        import time as _time

        _compile_start = _time.monotonic()
        logger.info("Generating world '%s' (behavior=%s)", plan.name, plan.behavior)

        from volnix.engines.world_compiler.data_generator import WorldDataGenerator
        from volnix.engines.world_compiler.personality_generator import (
            CompilerPersonalityGenerator,
        )
        from volnix.engines.world_compiler.plan_reviewer import PlanReviewer
        from volnix.engines.world_compiler.prompt_templates import SECTION_REPAIR
        from volnix.engines.world_compiler.seed_processor import CompilerSeedProcessor
        from volnix.engines.world_compiler.validator import CompilerWorldValidator

        # Assemble generation context ONCE — shared by all generators
        ctx = WorldGenerationContext(plan)
        validator = CompilerWorldValidator(
            collect_all_validation_errors=self._typed_config.collect_all_validation_errors
        )
        normalized_schemas = validator.normalize_plan_schemas(plan)
        state_machines = validator.collect_state_machines(plan)
        retry_counts: dict[str, int] = {}
        validation_sections: dict[str, dict[str, Any]] = {}

        # Step 4: GENERATE entities
        data_gen = WorldDataGenerator(
            llm_router=self._llm_router,
            seed=plan.seed,
        )
        all_entities: dict[str, list[dict[str, Any]]] = {}
        section_specs = {
            spec.entity_type: spec
            for spec in data_gen.iter_generation_specs(plan)
        }
        # Sort by dependency: generate root entities (no x-volnix-ref)
        # before dependent entities. Ensures valid cross-references.
        ordered_specs = data_gen._sort_by_dependency(list(section_specs.values()))

        for spec in ordered_specs:
            entity_type = spec.entity_type
            # Build reference context from already-generated entities
            ref_context = data_gen._build_ref_context(spec.entity_schema, all_entities)
            section_entities, section_result = await self._generate_validated_entity_section(
                spec=spec,
                ctx=ctx,
                data_gen=data_gen,
                validator=validator,
                normalized_schema=normalized_schemas.get(entity_type),
                state_machine=state_machines.get(entity_type),
                repair_template=SECTION_REPAIR,
                ref_context=ref_context,
            )
            all_entities[entity_type] = section_entities
            retry_counts[entity_type] = max(
                retry_counts.get(entity_type, 0),
                max(section_result.get("retry_count", 0), 0),
            )
            validation_sections[entity_type] = section_result["result"].model_dump(mode="json")

        # Step 4b: GENERATE actors with personalities
        personality_gen = CompilerPersonalityGenerator(
            llm_router=self._llm_router,
            seed=plan.seed,
        )
        actors = await personality_gen.expand_actor_structure(
            plan.actor_specs,
            plan.conditions,
            ctx,
        )
        role_indices: dict[str, list[int]] = {}
        for index, actor in enumerate(actors):
            role_indices.setdefault(actor.role, []).append(index)
        for role, indices in role_indices.items():
            count = len(indices)
            hint = actors[indices[0]].personality_hint or role
            personalities, role_result = await self._generate_validated_role_batch(
                role=role,
                count=count,
                personality_hint=hint,
                ctx=ctx,
                personality_gen=personality_gen,
                validator=validator,
                repair_template=SECTION_REPAIR,
            )
            for offset, actor_index in enumerate(indices):
                actors[actor_index] = actors[actor_index].model_copy(
                    update={"personality": personalities[offset]}
                )
            role_section = f"actor_role:{role}"
            retry_counts[role_section] = role_result.get("retry_count", 0)
            validation_sections[role_section] = role_result["result"].model_dump(mode="json")

        # Step 5: full-world validation before seeds
        all_entities = await self._repair_world_entity_sections(
            plan=plan,
            all_entities=all_entities,
            actors=actors,
            validator=validator,
            data_gen=data_gen,
            ctx=ctx,
            section_specs=section_specs,
            normalized_schemas=normalized_schemas,
            state_machines=state_machines,
            repair_template=SECTION_REPAIR,
            retry_counts=retry_counts,
            validation_sections=validation_sections,
        )

        # Step 6: INJECT SEEDS
        seed_processor = CompilerSeedProcessor(llm_router=self._llm_router, seed=plan.seed)
        applied_seed_invariants: dict[str, list[Any]] = {}
        if plan.seeds:
            seed_vars = ctx.for_seed_expansion()
            for index, description in enumerate(plan.seeds):
                seed_section = f"seed:{index}"
                all_entities, seed_result = await self._apply_validated_seed_section(
                    section=seed_section,
                    description=description,
                    all_entities=all_entities,
                    actors=actors,
                    existing_seed_invariants=applied_seed_invariants,
                    seed_processor=seed_processor,
                    validator=validator,
                    ctx=ctx,
                    base_vars=seed_vars,
                    repair_template=SECTION_REPAIR,
                    schemas=normalized_schemas,
                )
                applied_seed_invariants[seed_section] = seed_result["expansion"].invariants
                retry_counts[seed_section] = seed_result.get("retry_count", 0)
                validation_sections[seed_section] = seed_result["result"].model_dump(mode="json")

        # Step 6.5: DEDUP entities (seed versions win on conflict)
        from volnix.utils.collections import dedup_entity_collection
        all_entities = dedup_entity_collection(all_entities, key="id", strategy="last_wins")

        # Step 7: final validation gate before state/actor side effects
        final_validation = await validator.validate_world(
            plan,
            all_entities,
            actors=actors,
            seed_invariants=applied_seed_invariants,
        )
        if not final_validation.valid:
            raise WorldGenerationValidationError(
                "Generated world failed final validation",
                context={
                    "errors": final_validation.errors,
                    "retry_counts": retry_counts,
                },
            )

        # Step 7b: GENERATE visibility rules per actor role (before populate)
        # Must run before populate_entities so rules are persisted with all other entities.
        visibility_rules: list[dict[str, Any]] = []
        if self._llm_router and actors:
            try:
                from volnix.engines.world_compiler.visibility_generator import (
                    VisibilityRuleGenerator,
                )

                vis_gen = VisibilityRuleGenerator(
                    llm_router=self._llm_router,
                    seed=plan.seed,
                )
                context_vars = ctx.for_entity_generation()
                seen_roles: set[str] = set()
                for actor in actors:
                    if actor.role in seen_roles:
                        continue
                    seen_roles.add(actor.role)
                    actor_spec = {
                        "role": actor.role,
                        "type": str(actor.type),
                        "permissions": actor.permissions,
                        "visibility": getattr(actor, "visibility", None),
                    }
                    try:
                        rules = await vis_gen.generate_for_role(
                            actor_spec, plan, context_vars,
                        )
                        for rule in rules:
                            visibility_rules.append(rule.model_dump())
                    except Exception as exc:
                        logger.warning(
                            "Visibility rules failed for role %s: %s",
                            actor.role, exc,
                        )
            except Exception as exc:
                logger.warning(
                    "Visibility rule generation unavailable: %s", exc,
                )

        if visibility_rules:
            all_entities.setdefault("visibility_rule", []).extend(visibility_rules)
            logger.info(
                "Generated %d visibility rules for %d roles",
                len(visibility_rules),
                len({r["actor_role"] for r in visibility_rules}),
            )

        # Step 8: POPULATE state engine + register actors
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
            now = datetime.now(UTC)
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
                from volnix.ledger.entries import EngineLifecycleEntry

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

        # Step 9: GENERATE subscriptions for internal actors (if LLM available)
        actor_subscriptions: dict[str, list[Any]] = {}
        if self._llm_router and actors:
            try:
                from volnix.engines.world_compiler.subscription_generator import (
                    SubscriptionGenerator,
                )

                sub_gen = SubscriptionGenerator(
                    llm_router=self._llm_router,
                    seed=plan.seed,
                )
                for actor in actors:
                    if str(actor.type) in ("human", "system"):
                        actor_spec = {
                            "role": actor.role,
                            "personality": (
                                actor.personality.model_dump()
                                if actor.personality
                                else ""
                            ),
                            "type": str(actor.type),
                        }
                        try:
                            subs = await sub_gen.generate_subscriptions(
                                actor_spec, plan,
                            )
                            actor_subscriptions[str(actor.id)] = subs
                        except Exception as exc:
                            logger.warning(
                                "Subscription generation failed for actor %s: %s",
                                actor.id,
                                exc,
                            )
            except Exception as exc:
                logger.warning(
                    "Subscription generation unavailable during compilation: %s",
                    exc,
                )

        # Build result
        warnings = list(final_validation.warnings)
        result: dict[str, Any] = {
            "entities": all_entities,
            "actors": actors,
            "subscriptions": actor_subscriptions,
            "warnings": warnings,
            "seeds_processed": len(plan.seeds),
            "snapshot_id": str(snapshot_id) if snapshot_id else None,
            "validation_report": {
                "sections": validation_sections,
                "final_world": final_validation.model_dump(mode="json"),
            },
            "retry_counts": retry_counts,
        }

        # Generate report
        reviewer = PlanReviewer()
        result["report"] = reviewer.generate_report(plan, result)

        # L3: Record compilation to ledger
        _compile_ms = (_time.monotonic() - _compile_start) * 1000
        _ledger = getattr(self, "_ledger", None)
        if _ledger is not None:
            from volnix.ledger.entries import WorldCompilationEntry

            try:
                await _ledger.append(WorldCompilationEntry(
                    plan_name=plan.name,
                    behavior=plan.behavior,
                    seed=plan.seed,
                    services=list(plan.services.keys()),
                    entity_count=sum(
                        len(v) for v in all_entities.values()
                    ),
                    entity_types=list(all_entities.keys()),
                    actor_count=len(actors),
                    seeds_processed=len(plan.seeds),
                    total_retries=sum(retry_counts.values()),
                    warnings_count=len(warnings),
                    snapshot_id=str(snapshot_id) if snapshot_id else "",
                    duration_ms=_compile_ms,
                ))
            except Exception as exc:
                logger.warning(
                    "Compilation ledger entry failed: %s", exc
                )

        # Publish generation complete event
        await self.publish(WorldEvent(
            event_type="world.generation_complete",
            timestamp=Timestamp(
                world_time=datetime.now(UTC),
                wall_time=datetime.now(UTC),
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

    async def _generate_validated_entity_section(
        self,
        *,
        spec: Any,
        ctx: WorldGenerationContext,
        data_gen: Any,
        validator: Any,
        normalized_schema: Any,
        state_machine: dict[str, Any] | None,
        repair_template: Any,
        ref_context: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if normalized_schema is None:
            raise WorldGenerationValidationError(
                f"No normalized schema available for entity type '{spec.entity_type}'"
            )

        entities = await data_gen.generate_section(spec, ctx, ref_context=ref_context)
        retries = 0
        result = validator.validate_entity_section(
            spec.entity_type,
            entities,
            normalized_schema,
            state_machine=state_machine,
            expected_count=spec.count,
        )

        while not result.valid and retries < self._typed_config.max_section_retries:
            repaired_payload = await self._repair_section_payload(
                repair_template=repair_template,
                ctx=ctx,
                section_kind="entity_section",
                section_name=spec.entity_type,
                failing_payload=entities,
                validation_errors=result.errors,
                relevant_schema={
                    "entity_schema": spec.entity_schema,
                    "state_machine": state_machine,
                    "expected_count": spec.count,
                },
                output_contract=(
                    f"JSON array of exactly {spec.count} {spec.entity_type} entities "
                    "that conform to the provided schema."
                ),
            )
            entities = data_gen.parse_generated_entities(
                spec.entity_type,
                repaired_payload,
                spec.count,
            )
            retries += 1
            result = validator.validate_entity_section(
                spec.entity_type,
                entities,
                normalized_schema,
                state_machine=state_machine,
                expected_count=spec.count,
            )

        if not result.valid:
            for err in result.errors[:10]:
                logger.error("Section validation [%s]: %s", spec.entity_type, err)
            raise WorldGenerationValidationError(
                f"Entity section '{spec.entity_type}' failed validation",
                context={"errors": result.errors},
            )

        return entities, {"retry_count": retries, "result": result}

    async def _generate_validated_role_batch(
        self,
        *,
        role: str,
        count: int,
        personality_hint: str,
        ctx: WorldGenerationContext,
        personality_gen: Any,
        validator: Any,
        repair_template: Any,
    ) -> tuple[list[Any], dict[str, Any]]:
        personalities = await personality_gen.generate_role_batch(
            role=role,
            count=count,
            personality_hint=personality_hint,
            ctx=ctx,
        )
        retries = 0
        result = self._validate_role_personalities(
            role=role,
            count=count,
            personalities=personalities,
            validator=validator,
        )

        while not result.valid and retries < self._typed_config.max_section_retries:
            repaired_payload = await self._repair_section_payload(
                repair_template=repair_template,
                ctx=ctx,
                section_kind="actor_role",
                section_name=role,
                failing_payload=[item.model_dump(mode="json") for item in personalities],
                validation_errors=result.errors,
                relevant_schema={"role": role, "expected_count": count},
                output_contract=(
                    f"JSON array of exactly {count} personality objects for role '{role}'."
                ),
            )
            personalities = personality_gen.parse_role_batch(repaired_payload, count)
            retries += 1
            result = self._validate_role_personalities(
                role=role,
                count=count,
                personalities=personalities,
                validator=validator,
            )

        if not result.valid:
            raise WorldGenerationValidationError(
                f"Actor role '{role}' failed validation",
                context={"errors": result.errors},
            )

        return personalities, {"retry_count": retries, "result": result}

    def _validate_role_personalities(
        self,
        *,
        role: str,
        count: int,
        personalities: list[Any],
        validator: Any,
    ) -> Any:
        from volnix.actors.definition import ActorDefinition
        from volnix.core.types import ActorId, ActorType

        actors = [
            ActorDefinition(
                id=ActorId(f"{role}-{index}"),
                type=ActorType.HUMAN,
                role=role,
                personality=personality,
            )
            for index, personality in enumerate(personalities)
        ]
        return validator.validate_actor_role(role, actors, expected_count=count)

    async def _repair_world_entity_sections(
        self,
        *,
        plan: WorldPlan,
        all_entities: dict[str, list[dict[str, Any]]],
        actors: list[Any],
        validator: Any,
        data_gen: Any,
        ctx: WorldGenerationContext,
        section_specs: dict[str, Any],
        normalized_schemas: dict[str, Any],
        state_machines: dict[str, dict[str, Any]],
        repair_template: Any,
        retry_counts: dict[str, int],
        validation_sections: dict[str, dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        validation = await validator.validate_world(plan, all_entities, actors=actors)
        if not validation.valid:
            # Log ALL validation errors before any repair attempts
            for section_name, section_result in validation.sections.items():
                if not section_result.valid:
                    for err in section_result.errors:
                        logger.error("Initial validation: [%s] %s", section_name, err)
        while not validation.valid:
            repairable_sections = [
                section
                for section in validation.sections
                if section in section_specs
                and retry_counts.get(section, 0) < self._typed_config.max_section_retries
            ]
            if not repairable_sections:
                for section_name, section_result in validation.sections.items():
                    if not section_result.valid:
                        for err in section_result.errors[:5]:
                            logger.error("Validation: [%s] %s", section_name, err)
                raise WorldGenerationValidationError(
                    "Generated world failed cross-section validation",
                    context={"errors": validation.errors},
                )

            for section in repairable_sections:
                spec = section_specs[section]
                repaired_payload = await self._repair_section_payload(
                    repair_template=repair_template,
                    ctx=ctx,
                    section_kind="entity_section",
                    section_name=section,
                    failing_payload=all_entities.get(section, []),
                    validation_errors=validation.sections[section].errors,
                    relevant_schema={
                        "entity_schema": spec.entity_schema,
                        "state_machine": state_machines.get(section),
                    },
                    output_contract=(
                        f"JSON array of exactly {spec.count} {section} entities "
                        "that satisfy the schema and validation errors."
                    ),
                )
                all_entities[section] = data_gen.parse_generated_entities(
                    section,
                    repaired_payload,
                    spec.count,
                )
                retry_counts[section] = retry_counts.get(section, 0) + 1
                local_result = validator.validate_entity_section(
                    section,
                    all_entities[section],
                    normalized_schemas[section],
                    state_machine=state_machines.get(section),
                    expected_count=spec.count,
                )
                validation_sections[section] = local_result.model_dump(mode="json")
                if not local_result.valid:
                    raise WorldGenerationValidationError(
                        f"Entity section '{section}' failed local validation after repair",
                        context={"errors": local_result.errors},
                    )

            validation = await validator.validate_world(plan, all_entities, actors=actors)

        return all_entities

    async def _apply_validated_seed_section(
        self,
        *,
        section: str,
        description: str,
        all_entities: dict[str, list[dict[str, Any]]],
        actors: list[Any],
        existing_seed_invariants: dict[str, list[Any]],
        seed_processor: Any,
        validator: Any,
        ctx: WorldGenerationContext,
        base_vars: dict[str, str],
        repair_template: Any,
        schemas: dict[str, Any] | None = None,
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        expansion = await seed_processor.expand_seed(
            description, all_entities, base_vars, schemas=schemas,
        )
        retries = 0
        result, updated_entities = await self._validate_seed_application(
            plan=ctx.plan,
            section=section,
            expansion=expansion,
            current_entities=all_entities,
            actors=actors,
            seed_processor=seed_processor,
            validator=validator,
            existing_seed_invariants=existing_seed_invariants,
            schemas=schemas,
        )
        if not result.valid:
            logger.warning(
                "Seed [%s] initial validation failed (%d errors): %s",
                section, len(result.errors), "; ".join(result.errors[:3]),
            )

        while not result.valid and retries < self._typed_config.max_section_retries:
            repaired_payload = await self._repair_section_payload(
                repair_template=repair_template,
                ctx=ctx,
                section_kind="seed",
                section_name=section,
                failing_payload=expansion.model_dump(mode="json"),
                validation_errors=result.errors,
                relevant_schema={"description": description},
                output_contract=(
                    "JSON object with entities_to_create, entities_to_modify, and "
                    "explicit invariants that verify the seed scenario."
                ),
            )
            expansion = seed_processor.parse_expansion(repaired_payload, description)
            retries += 1
            result, updated_entities = await self._validate_seed_application(
                plan=ctx.plan,
                section=section,
                expansion=expansion,
                current_entities=all_entities,
                actors=actors,
                seed_processor=seed_processor,
                validator=validator,
                existing_seed_invariants=existing_seed_invariants,
                schemas=schemas,
            )

        if not result.valid:
            for err in result.errors:
                logger.error("Seed validation [%s] %s: %s", section, description[:60], err)
            raise WorldGenerationValidationError(
                f"Seed section '{section}' failed validation",
                context={"errors": result.errors},
            )

        return updated_entities, {
            "retry_count": retries,
            "result": result,
            "expansion": expansion,
        }

    async def _validate_seed_application(
        self,
        *,
        plan: WorldPlan,
        section: str,
        expansion: Any,
        current_entities: dict[str, list[dict[str, Any]]],
        actors: list[Any],
        seed_processor: Any,
        validator: Any,
        existing_seed_invariants: dict[str, list[Any]],
        schemas: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, list[dict[str, Any]]]]:
        updated_entities = seed_processor.apply_modifications(
            expansion, current_entities, schemas=schemas,
        )

        if not expansion.invariants:
            return (
                SectionValidationResult(
                    section=section,
                    valid=False,
                    errors=["Seed expansion did not declare invariants"],
                ),
                updated_entities,
            )

        validation = await validator.validate_world(
            plan,
            updated_entities,
            actors=actors,
            seed_invariants={
                **existing_seed_invariants,
                section: expansion.invariants,
            },
        )
        seed_result = validator.validate_seed_invariants(
            section,
            expansion.invariants,
            updated_entities,
            validator.normalize_plan_schemas(plan),
        )
        combined_errors = list(seed_result.errors)
        for error in validation.errors:
            if error not in combined_errors:
                combined_errors.append(error)
        combined_warnings = list(seed_result.warnings)
        for warning in validation.warnings:
            if warning not in combined_warnings:
                combined_warnings.append(warning)

        return (
            SectionValidationResult(
                section=section,
                valid=len(combined_errors) == 0,
                errors=combined_errors,
                warnings=combined_warnings,
            ),
            updated_entities,
        )

    async def _repair_section_payload(
        self,
        *,
        repair_template: Any,
        ctx: WorldGenerationContext,
        section_kind: str,
        section_name: str,
        failing_payload: Any,
        validation_errors: list[str],
        relevant_schema: dict[str, Any],
        output_contract: str,
    ) -> Any:
        response = await repair_template.execute(
            self._llm_router,
            _seed=ctx.seed,
            domain_description=ctx.domain,
            reality_summary=ctx.reality_summary,
            behavior_mode=ctx.behavior,
            behavior_description=ctx.behavior_description,
            actor_summary=ctx.actor_summary,
            policies_summary=ctx.policies_summary,
            section_kind=section_kind,
            section_name=section_name,
            validation_errors=json.dumps(validation_errors, indent=2),
            relevant_schema=json.dumps(relevant_schema, indent=2),
            output_contract=output_contract,
            failing_payload=json.dumps(failing_payload, indent=2, default=str),
        )
        return repair_template.parse_json_response(response)

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
