"""World data generator — generates entities via LLM shaped by reality dimensions.

Uses: ENTITY_GENERATION PromptTemplate (prompt_templates.py)
Uses: WorldGenerationContext (generation_context.py) — single source of truth
Uses: LLMRouter.route() (terrarium/llm/router.py)
Uses: SchemaValidator.validate_entity() (terrarium/validation/schema.py)
Uses: ServiceSurface.entity_schemas (terrarium/kernel/surface.py)

RULE: NO FALLBACK GENERATION. If LLM is unavailable, raise CompilerError.
RULE: NO HEURISTICS. No _generate_fallback(), no randint(), no hardcoded data.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any

from terrarium.core.errors import CompilerError
from terrarium.engines.world_compiler.generation_context import WorldGenerationContext
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.engines.world_compiler.prompt_templates import ENTITY_GENERATION
from terrarium.llm.router import LLMRouter
from terrarium.validation.schema import SchemaValidator

logger = logging.getLogger(__name__)


class WorldDataGenerator:
    """Generates entities via LLM from WorldPlan service schemas."""

    def __init__(
        self, llm_router: LLMRouter | None = None, seed: int = 42
    ) -> None:
        self._router = llm_router
        self._seed = seed
        self._rng = random.Random(seed)  # For cross-linking only
        self._schema_validator = SchemaValidator()

    async def generate(
        self, plan: WorldPlan, ctx: WorldGenerationContext
    ) -> dict[str, list[dict[str, Any]]]:
        """Generate ALL entities from WorldPlan via LLM.

        Iterates plan.services -> surface.entity_schemas -> LLM generates per type.
        Cross-links _id fields. Returns {entity_type: [entity_dicts]}.
        """
        if not self._router:
            raise CompilerError(
                "LLM router required for entity generation. "
                "Set GOOGLE_API_KEY and configure llm.providers in terrarium.toml"
            )

        base_vars = ctx.for_entity_generation()
        all_entities: dict[str, list[dict[str, Any]]] = {}

        for svc_name, resolution in plan.services.items():
            surface = resolution.surface
            for entity_type, schema in surface.entity_schemas.items():
                count = self._determine_count(entity_type, plan)
                entities = await self._generate_batch(
                    entity_type=entity_type,
                    schema=schema,
                    count=count,
                    base_vars=base_vars,
                )
                all_entities.setdefault(entity_type, []).extend(entities)

        all_entities = self._cross_link(all_entities)
        return all_entities

    async def _generate_batch(
        self,
        entity_type: str,
        schema: dict[str, Any],
        count: int,
        base_vars: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Generate N entities via LLM. No fallback."""
        if count == 0:
            return []

        response = await ENTITY_GENERATION.execute(
            self._router,
            _seed=self._seed,
            **base_vars,
            entity_type=entity_type,
            count=str(count),
            entity_schema=json.dumps(schema, indent=2),
        )
        parsed = ENTITY_GENERATION.parse_json_response(response)

        # Normalize response format
        if isinstance(parsed, list):
            return parsed[:count]
        if isinstance(parsed, dict) and entity_type in parsed:
            return parsed[entity_type][:count]
        if isinstance(parsed, dict) and "entities" in parsed:
            return parsed["entities"][:count]
        return [parsed] if parsed else []

    def _determine_count(self, entity_type: str, plan: WorldPlan) -> int:
        """Read count from actor_specs YAML config."""
        for spec in plan.actor_specs:
            if spec.get("role", "").lower() == entity_type.lower():
                return spec.get("count", 10)
        return 10

    def _cross_link(
        self, all_entities: dict[str, list[dict[str, Any]]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Establish referential integrity between entity types.

        For each field ending in _id, assign a valid ID from the referenced type.
        Uses seeded RNG for reproducibility — this is referential integrity.
        """
        for entity_type, entities in all_entities.items():
            for entity in entities:
                for field, value in list(entity.items()):
                    if field.endswith("_id") and field != "id":
                        ref_type = field.replace("_id", "")
                        if ref_type in all_entities and all_entities[ref_type]:
                            ref_entity = self._rng.choice(
                                all_entities[ref_type]
                            )
                            entity[field] = ref_entity.get("id", value)
        return all_entities

    def validate(
        self,
        all_entities: dict[str, list[dict[str, Any]]],
        plan: WorldPlan,
    ) -> list[str]:
        """Validate entities against ServiceSurface schemas + state machines."""
        warnings: list[str] = []
        for svc_name, resolution in plan.services.items():
            surface = resolution.surface
            for entity_type, schema in surface.entity_schemas.items():
                for entity in all_entities.get(entity_type, []):
                    result = self._schema_validator.validate_entity(
                        entity, schema
                    )
                    if not result.valid:
                        warnings.extend(
                            [f"{entity_type}: {e}" for e in result.errors]
                        )
            for sm_name, sm_def in surface.state_machines.items():
                for entity in all_entities.get(sm_name, []):
                    status = entity.get("status")
                    if status:
                        transitions = sm_def.get("transitions", {})
                        all_states: set[str] = set(transitions.keys())
                        for targets in transitions.values():
                            if isinstance(targets, list):
                                all_states.update(targets)
                        if all_states and status not in all_states:
                            warnings.append(
                                f"{sm_name}: invalid status '{status}'"
                            )
        return warnings
