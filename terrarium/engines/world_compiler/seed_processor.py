"""Seed processing via LLM for world compilation.

Uses: SEED_EXPANSION PromptTemplate (prompt_templates.py)
Uses: WorldGenerationContext (generation_context.py) — single source of truth
Uses: SeedProcessor (terrarium/reality/seeds.py) for Seed model

RULE: LLM expands ALL seeds. No empty no-op returns.
RULE: Handle both "fields" and "properties" keys from LLM response.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from terrarium.core.errors import CompilerError
from terrarium.engines.world_compiler.generation_context import WorldGenerationContext
from terrarium.engines.world_compiler.prompt_templates import SEED_EXPANSION
from terrarium.llm.router import LLMRouter
from terrarium.reality.seeds import Seed, SeedProcessor

logger = logging.getLogger(__name__)


class CompilerSeedProcessor:
    """Processes NL seed descriptions into entity modifications via LLM."""

    def __init__(self, llm_router: LLMRouter | None = None) -> None:
        self._router = llm_router
        self._base_processor = SeedProcessor(llm_router=llm_router)

    async def process_all(
        self,
        seed_descriptions: list[str],
        all_entities: dict[str, list[dict[str, Any]]],
        ctx: WorldGenerationContext,
    ) -> dict[str, list[dict[str, Any]]]:
        """Process ALL seed descriptions via LLM and apply to entity set."""
        if not self._router:
            raise CompilerError(
                "LLM router required for seed expansion"
            )

        base_vars = ctx.for_seed_expansion()

        for desc in seed_descriptions:
            mods = await self.expand_seed(desc, all_entities, base_vars)
            all_entities = self.apply_modifications(mods, all_entities)
        return all_entities

    async def expand_seed(
        self,
        description: str,
        all_entities: dict[str, list[dict[str, Any]]],
        base_vars: dict[str, str],
    ) -> dict[str, Any]:
        """NL seed -> structured modifications via LLM. No fallback."""
        if not self._router:
            raise CompilerError(
                "LLM router required for seed expansion"
            )

        available: dict[str, list[str]] = {}
        for etype, entities in all_entities.items():
            available[etype] = [e.get("id", "") for e in entities[:20]]

        response = await SEED_EXPANSION.execute(
            self._router,
            _seed=42,
            **base_vars,
            seed_description=description,
            available_entities=json.dumps(available, indent=2),
        )
        parsed = SEED_EXPANSION.parse_json_response(response)
        return {
            "entities_to_create": parsed.get("entities_to_create", []),
            "entities_to_modify": parsed.get("entities_to_modify", []),
            "description": description,
        }

    def apply_modifications(
        self,
        mods: dict[str, Any],
        all_entities: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Apply structured modifications to entity set.

        Handles both "fields" and "properties" keys — Gemini uses different keys.
        """
        for new_entity in mods.get("entities_to_create", []):
            etype = new_entity.get("entity_type")
            # Handle both "fields" and "properties" keys from LLM response
            fields = new_entity.get("fields") or new_entity.get("properties", {})
            if etype and fields:
                all_entities.setdefault(etype, []).append(fields)

        for mod in mods.get("entities_to_modify", []):
            etype = mod.get("entity_type")
            eid = mod.get("entity_id")
            updates = mod.get("field_updates", {})
            if etype in all_entities and updates:
                for entity in all_entities[etype]:
                    if entity.get("id") == eid:
                        entity.update(updates)
                        break

        return all_entities

    async def expand_nl_seeds(
        self, descriptions: list[str]
    ) -> list[Seed]:
        """Convert NL descriptions to Seed models."""
        seeds: list[Seed] = []
        for desc in descriptions:
            seed = await self._base_processor.expand_nl_seed(desc)
            seeds.append(seed)
        return seeds
