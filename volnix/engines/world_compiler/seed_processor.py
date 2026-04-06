"""Seed processing via LLM for world compilation.

Uses: SEED_EXPANSION PromptTemplate (prompt_templates.py)
Uses: WorldGenerationContext (generation_context.py) — single source of truth
Uses: SeedProcessor (volnix/reality/seeds.py) for Seed model

RULE: LLM expands ALL seeds. No empty no-op returns.
RULE: Handle both "fields" and "properties" keys from LLM response.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from volnix.core.errors import CompilerError
from volnix.engines.world_compiler.generation_context import WorldGenerationContext
from volnix.engines.world_compiler.prompt_templates import SEED_EXPANSION
from volnix.llm.router import LLMRouter
from volnix.reality.seeds import Seed, SeedInvariant, SeedProcessor

logger = logging.getLogger(__name__)


class EntityCreate(BaseModel, frozen=True):
    """Typed create mutation emitted by seed expansion."""

    entity_type: str
    fields: dict[str, Any] = Field(default_factory=dict)


class EntityModify(BaseModel, frozen=True):
    """Typed update mutation emitted by seed expansion."""

    entity_type: str
    entity_id: str
    field_updates: dict[str, Any] = Field(default_factory=dict)


class SeedExpansionResult(BaseModel, frozen=True):
    """Concrete seed expansion output used by compiler orchestration."""

    description: str
    entities_to_create: list[EntityCreate] = Field(default_factory=list)
    entities_to_modify: list[EntityModify] = Field(default_factory=list)
    invariants: list[SeedInvariant] = Field(default_factory=list)


class CompilerSeedProcessor:
    """Processes NL seed descriptions into entity modifications via LLM."""

    ENTITY_CONTEXT_LIMIT: int = 50

    def __init__(self, llm_router: LLMRouter | None = None, seed: int = 42) -> None:
        self._router = llm_router
        self._seed = seed
        self._base_processor = SeedProcessor(llm_router=llm_router)

    async def process_all(
        self,
        seed_descriptions: list[str],
        all_entities: dict[str, list[dict[str, Any]]],
        ctx: WorldGenerationContext,
        schemas: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Process ALL seed descriptions via LLM and apply to entity set."""
        if not self._router:
            raise CompilerError("LLM router required for seed expansion")

        base_vars = ctx.for_seed_expansion()

        for desc in seed_descriptions:
            mods = await self.expand_seed(desc, all_entities, base_vars, schemas=schemas)
            all_entities = self.apply_modifications(mods, all_entities, schemas=schemas)
        return all_entities

    async def expand_seed(
        self,
        description: str,
        all_entities: dict[str, list[dict[str, Any]]],
        base_vars: dict[str, str],
        schemas: dict[str, Any] | None = None,
    ) -> SeedExpansionResult:
        """NL seed -> structured modifications via LLM. No fallback."""
        if not self._router:
            raise CompilerError("LLM router required for seed expansion")

        available: dict[str, Any] = {}
        for etype, entities in all_entities.items():
            id_field = "id"
            schema_fields: dict[str, str] = {}
            ref_annotations: dict[str, str] = {}
            if schemas and etype in schemas:
                schema_obj = schemas[etype]
                if hasattr(schema_obj, "identity_field") and schema_obj.identity_field:
                    id_field = schema_obj.identity_field
                # Include field names + types so LLM knows valid fields
                json_schema = getattr(schema_obj, "json_schema", {})
                for fname, fdef in json_schema.get("properties", {}).items():
                    schema_fields[fname] = (
                        fdef.get("type", "string") if isinstance(fdef, dict) else "string"
                    )
                # Include reference annotations so LLM knows which fields reference which entity types
                # references is list[ReferenceRule] with .field and .target_entity_type
                for ref_rule in getattr(schema_obj, "references", []):
                    ref_annotations[ref_rule.field] = ref_rule.target_entity_type
            summaries = []
            for e in entities[: self.ENTITY_CONTEXT_LIMIT]:
                summary: dict[str, str] = {id_field: e.get(id_field, e.get("id", ""))}
                if "status" in e:
                    summary["status"] = e["status"]
                summaries.append(summary)
            entry: dict[str, Any] = {
                "total_count": len(entities),
                "entities": summaries,
            }
            if schema_fields:
                entry["fields"] = schema_fields
            if ref_annotations:
                entry["references"] = ref_annotations
            available[etype] = entry

        response = await SEED_EXPANSION.execute(
            self._router,
            _seed=self._seed,
            **base_vars,
            seed_description=description,
            available_entities=json.dumps(available, indent=2),
        )
        parsed = SEED_EXPANSION.parse_json_response(response)
        return self.parse_expansion(parsed, description)

    def parse_expansion(
        self,
        parsed: Any,
        description: str,
    ) -> SeedExpansionResult:
        """Normalize raw LLM output into the typed seed expansion contract."""
        if not isinstance(parsed, dict):
            parsed = {}

        creates = [
            EntityCreate(
                entity_type=str(item.get("entity_type", "")),
                fields=item.get("fields") or item.get("properties", {}) or {},
            )
            for item in parsed.get("entities_to_create", [])
            if isinstance(item, dict)
        ]
        modifies = [
            EntityModify(
                entity_type=str(item.get("entity_type", "")),
                entity_id=str(item.get("entity_id", "")),
                field_updates=item.get("field_updates", {}) or {},
            )
            for item in parsed.get("entities_to_modify", [])
            if isinstance(item, dict)
        ]
        invariants = [
            SeedInvariant.model_validate(item)
            for item in parsed.get("invariants", [])
            if isinstance(item, dict)
        ]
        return SeedExpansionResult(
            description=description,
            entities_to_create=creates,
            entities_to_modify=modifies,
            invariants=invariants,
        )

    def apply_modifications(
        self,
        mods: SeedExpansionResult | dict[str, Any],
        all_entities: dict[str, list[dict[str, Any]]],
        schemas: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Apply structured modifications to entity set.

        Handles both "fields" and "properties" keys — Gemini uses different keys.
        Uses schema identity_field when available to resolve entities whose
        primary key is not "id" (e.g. customer_id, ticket_id, mailbox_id).
        """
        normalized = (
            mods
            if isinstance(mods, SeedExpansionResult)
            else self.parse_expansion(mods, str(mods.get("description", "")))
        )
        updated_entities = copy.deepcopy(all_entities)

        for new_entity in normalized.entities_to_create:
            if new_entity.entity_type and new_entity.fields:
                updated_entities.setdefault(new_entity.entity_type, []).append(
                    dict(new_entity.fields)
                )

        for mod in normalized.entities_to_modify:
            if mod.entity_type not in updated_entities or not mod.field_updates:
                continue
            # Resolve identity field from schema contract
            identity_field = "id"
            if schemas and mod.entity_type in schemas:
                schema = schemas[mod.entity_type]
                if hasattr(schema, "identity_field") and schema.identity_field:
                    identity_field = schema.identity_field
            for entity in updated_entities[mod.entity_type]:
                entity_identity = (
                    entity.get(identity_field) or entity.get("id") or entity.get("entity_id")
                )
                if entity_identity == mod.entity_id:
                    entity.update(mod.field_updates)
                    break

        return updated_entities

    async def expand_nl_seeds(self, descriptions: list[str]) -> list[Seed]:
        """Convert NL descriptions to Seed models."""
        seeds: list[Seed] = []
        for desc in descriptions:
            seed = await self._base_processor.expand_nl_seed(desc)
            seeds.append(seed)
        return seeds
