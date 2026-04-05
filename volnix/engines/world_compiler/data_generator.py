"""World data generator — generates entities via LLM shaped by reality dimensions.

Generation only. Validation and repair orchestration live in the compiler
validator/engine path.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from volnix.core.errors import CompilerError
from volnix.engines.world_compiler.generation_context import WorldGenerationContext
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.engines.world_compiler.prompt_templates import ENTITY_GENERATION
from volnix.llm.router import LLMRouter

logger = logging.getLogger(__name__)


def _strip_custom_extensions(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip x-volnix-* keys from schema for structured output APIs.

    Entity schemas contain internal extensions (x-volnix-identity,
    x-volnix-ref) that structured output APIs may reject as unknown
    JSON Schema keywords. The stripped version is only used for the
    provider's schema enforcement; the original is still passed in the
    prompt text for context.
    """
    cleaned: dict[str, Any] = {}
    for k, v in schema.items():
        if k.startswith("x-"):
            continue
        if isinstance(v, dict):
            cleaned[k] = _strip_custom_extensions(v)
        elif isinstance(v, list):
            cleaned[k] = [
                _strip_custom_extensions(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            cleaned[k] = v
    return cleaned


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

        Generates entity types in dependency order: root entities (no
        references) first, then dependent entities. Previously generated
        entity IDs are passed as context so the LLM produces valid
        cross-references.

        Dependency order is derived from ``x-volnix-ref`` annotations
        in entity schemas — generic across all packs.
        """
        all_entities: dict[str, list[dict[str, Any]]] = {}
        specs = self.iter_generation_specs(plan)
        ordered = self._sort_by_dependency(specs)

        for spec in ordered:
            ref_context = self._build_ref_context(spec.entity_schema, all_entities)
            all_entities[spec.entity_type] = await self.generate_section(
                spec, ctx, ref_context=ref_context,
            )
            logger.info(
                "Generated %d %s entities (refs: %s)",
                len(all_entities[spec.entity_type]),
                spec.entity_type,
                list(ref_context.keys()) or "none",
            )
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

    def _sort_by_dependency(
        self, specs: list[EntityGenerationSpec],
    ) -> list[EntityGenerationSpec]:
        """Sort specs so referenced entity types are generated before dependents.

        Uses ``x-volnix-ref`` annotations in schemas to build a dependency
        graph, then topologically sorts. Entity types with no references come
        first. Works generically across all packs.
        """
        # Map entity_type -> spec
        spec_map = {s.entity_type: s for s in specs}
        known_types = set(spec_map.keys())

        # Build dependency edges: entity_type -> set of types it depends on
        deps: dict[str, set[str]] = {s.entity_type: set() for s in specs}
        for spec in specs:
            properties = spec.entity_schema.get("properties", {})
            for _field, field_schema in properties.items():
                ref = field_schema.get("x-volnix-ref")
                if isinstance(ref, str) and ref in known_types and ref != spec.entity_type:
                    deps[spec.entity_type].add(ref)
                elif isinstance(ref, dict):
                    target = ref.get("entity_type", "")
                    if target in known_types and target != spec.entity_type:
                        deps[spec.entity_type].add(target)

        # Topological sort (Kahn's algorithm)
        in_degree = {et: 0 for et in deps}
        for et, dep_set in deps.items():
            for dep in dep_set:
                in_degree[et] += 1  # et depends on dep

        queue = [et for et, deg in in_degree.items() if deg == 0]
        ordered: list[str] = []
        while queue:
            et = queue.pop(0)
            ordered.append(et)
            # Find types that depend on et and reduce their in-degree
            for other, dep_set in deps.items():
                if et in dep_set:
                    dep_set.discard(et)
                    if len(deps[other]) == 0 and other not in ordered and other not in queue:
                        queue.append(other)

        # Append any remaining (circular deps — generate in original order)
        for spec in specs:
            if spec.entity_type not in ordered:
                ordered.append(spec.entity_type)

        return [spec_map[et] for et in ordered if et in spec_map]

    def _build_ref_context(
        self,
        schema: dict[str, Any],
        all_entities: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Build reference context from already-generated entities.

        For each field with ``x-volnix-ref`` pointing to an already-generated
        entity type, extract the IDs (and key fields for richer context).
        Generic across all packs — uses only schema annotations.

        Returns:
            Dict mapping field_name -> {target_type, valid_ids, samples}.
        """
        refs: dict[str, Any] = {}
        properties = schema.get("properties", {})
        for field_name, field_schema in properties.items():
            ref_target = field_schema.get("x-volnix-ref")
            if isinstance(ref_target, dict):
                ref_target = ref_target.get("entity_type")
            if not isinstance(ref_target, str) or ref_target not in all_entities:
                continue
            entities = all_entities[ref_target]
            ids = [e.get("id") or e.get("_entity_id", "") for e in entities if e.get("id") or e.get("_entity_id")]
            # Include a few sample entities for richer context (name, role, etc.)
            samples = []
            for e in entities[:5]:
                sample = {"id": e.get("id", "")}
                for key in ("name", "username", "display_name", "role", "title", "symbol", "status"):
                    if key in e:
                        sample[key] = e[key]
                samples.append(sample)
            refs[field_name] = {
                "target_type": ref_target,
                "valid_ids": ids,
                "samples": samples,
            }
        return refs

    async def generate_section(
        self,
        spec: EntityGenerationSpec,
        ctx: WorldGenerationContext,
        ref_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a single entity section via LLM."""
        if not self._router:
            raise CompilerError(
                "LLM router required for entity generation. "
                "Set GOOGLE_API_KEY and configure llm.providers in volnix.toml"
            )

        base_vars = ctx.for_entity_generation()
        return await self._generate_batch(
            entity_type=spec.entity_type,
            schema=spec.entity_schema,
            count=spec.count,
            base_vars=base_vars,
            ref_context=ref_context,
        )

    async def _generate_batch(
        self,
        entity_type: str,
        schema: dict[str, Any],
        count: int,
        base_vars: dict[str, str],
        ref_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate N entities via LLM. No fallback."""
        if count == 0:
            return []

        # Build reference context string for the prompt
        existing_refs = json.dumps(ref_context, indent=2) if ref_context else "none"

        # Build structured output schema: array of entities.
        # Strip x-volnix-* extensions that providers don't understand.
        clean_schema = _strip_custom_extensions(schema)
        array_schema: dict[str, Any] = {
            "type": "array",
            "items": clean_schema,
        }

        response = await ENTITY_GENERATION.execute(
            self._router,
            _seed=self._seed,
            _output_schema=array_schema,
            **base_vars,
            entity_type=entity_type,
            count=str(count),
            entity_schema=json.dumps(schema, indent=2),
            existing_refs=existing_refs,
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
