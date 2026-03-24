"""World data generator — generates entities via LLM shaped by reality dimensions.

Generation only. Validation and repair orchestration live in the compiler
validator/engine path.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from terrarium.core.errors import CompilerError
from terrarium.engines.world_compiler.generation_context import WorldGenerationContext
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.engines.world_compiler.prompt_templates import ENTITY_GENERATION
from terrarium.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class EntityGenerationSpec(BaseModel, frozen=True):
    """Single deterministic generation request for one entity section."""

    service_name: str
    entity_type: str
    entity_schema: dict[str, Any]
    count: int


class WorldDataGenerator:
    """Generates entities via LLM from WorldPlan service schemas."""

    DEFAULT_ENTITY_COUNT = 10

    def __init__(
        self, llm_router: LLMRouter | None = None, seed: int = 42,
        default_entity_count: int | None = None,
    ) -> None:
        self._router = llm_router
        self._seed = seed
        self._default_count = default_entity_count or self.DEFAULT_ENTITY_COUNT

    async def generate(
        self, plan: WorldPlan, ctx: WorldGenerationContext
    ) -> dict[str, list[dict[str, Any]]]:
        """Generate ALL entities from WorldPlan via LLM.

        Iterates plan services and generates each entity section independently.
        """
        all_entities: dict[str, list[dict[str, Any]]] = {}
        for spec in self.iter_generation_specs(plan):
            all_entities[spec.entity_type] = await self.generate_section(spec, ctx)
        return all_entities

    def iter_generation_specs(
        self,
        plan: WorldPlan,
    ) -> list[EntityGenerationSpec]:
        """Expand a plan into deterministic per-section generation requests."""
        specs: list[EntityGenerationSpec] = []
        for service_name, resolution in plan.services.items():
            for entity_type, schema in resolution.surface.entity_schemas.items():
                specs.append(
                    EntityGenerationSpec(
                        service_name=service_name,
                        entity_type=entity_type,
                        entity_schema=schema,
                        count=self._determine_count(entity_type, plan),
                    )
                )
        return specs

    async def generate_section(
        self,
        spec: EntityGenerationSpec,
        ctx: WorldGenerationContext,
    ) -> list[dict[str, Any]]:
        """Generate a single entity section via LLM."""
        if not self._router:
            raise CompilerError(
                "LLM router required for entity generation. "
                "Set GOOGLE_API_KEY and configure llm.providers in terrarium.toml"
            )

        base_vars = ctx.for_entity_generation()
        return await self._generate_batch(
            entity_type=spec.entity_type,
            schema=spec.entity_schema,
            count=spec.count,
            base_vars=base_vars,
        )

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
        return self.parse_generated_entities(entity_type, parsed, count)

    def parse_generated_entities(
        self,
        entity_type: str,
        parsed: Any,
        count: int,
    ) -> list[dict[str, Any]]:
        """Normalize a section payload into a concrete list of entities."""
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict) and entity_type in parsed:
            items = parsed[entity_type]
        elif isinstance(parsed, dict) and "entities" in parsed:
            items = parsed["entities"]
        elif parsed:
            items = [parsed]
        else:
            items = []

        return [
            item for item in items[:count]
            if isinstance(item, dict)
        ]

    def _determine_count(self, entity_type: str, plan: WorldPlan) -> int:
        """Read count from actor_specs YAML config."""
        for spec in plan.actor_specs:
            if spec.get("role", "").lower() == entity_type.lower():
                return spec.get("count", self._default_count)
        return self._default_count
