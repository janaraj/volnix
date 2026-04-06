"""Personality generation via LLM for world compilation.

Uses: PERSONALITY_BATCH PromptTemplate (prompt_templates.py)
Uses: WorldGenerationContext (generation_context.py) — single source of truth
Uses: SimpleActorGenerator for STRUCTURE only (count expansion, friction distribution)

RULE: LLM generates ALL personalities. SimpleActorGenerator provides structure.
RULE: 1 LLM call per ROLE, not per actor. Batch generation.
RULE: NO HEURISTICS. No fallback personality generation.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from volnix.actors.definition import ActorDefinition
from volnix.actors.personality import FrictionProfile, Personality
from volnix.actors.simple_generator import SimpleActorGenerator
from volnix.core.errors import CompilerError
from volnix.engines.world_compiler.generation_context import WorldGenerationContext
from volnix.engines.world_compiler.prompt_templates import PERSONALITY_BATCH
from volnix.llm.router import LLMRouter
from volnix.reality.dimensions import WorldConditions

logger = logging.getLogger(__name__)


class CompilerPersonalityGenerator:
    """LLM-based personality generator. LLM is REQUIRED."""

    def __init__(
        self,
        llm_router: LLMRouter | None = None,
        seed: int = 42,
    ) -> None:
        self._router = llm_router
        self._seed = seed
        self._fallback = SimpleActorGenerator(seed=seed)  # For STRUCTURE only

    async def expand_actor_structure(
        self,
        actor_specs: list[dict[str, Any]],
        conditions: WorldConditions,
        ctx: WorldGenerationContext,
    ) -> list[ActorDefinition]:
        """Deterministically expand actor specs into concrete actor structures."""
        return await self._fallback.generate_batch(
            actor_specs,
            conditions,
            ctx.domain,
        )

    async def generate_role_batch(
        self,
        role: str,
        count: int,
        personality_hint: str,
        ctx: WorldGenerationContext,
    ) -> list[Personality]:
        """Generate a single role batch without rebuilding actor structure."""
        if not self._router:
            raise CompilerError("LLM router required for actor generation")
        return await self._generate_batch_for_role(
            role=role,
            count=count,
            hint=personality_hint or role,
            base_vars=ctx.for_personality_batch(),
        )

    async def generate_personality(
        self,
        role: str,
        personality_hint: str,
        ctx: WorldGenerationContext,
    ) -> Personality:
        """Generate a single personality via LLM. No fallback."""
        if not self._router:
            raise CompilerError("LLM router required for personality generation")

        base_vars = ctx.for_personality_batch()
        personalities = await self._generate_batch_for_role(
            role=role,
            count=1,
            hint=personality_hint or role,
            base_vars=base_vars,
        )
        return personalities[0]

    async def _generate_batch_for_role(
        self,
        role: str,
        count: int,
        hint: str,
        base_vars: dict[str, str],
    ) -> list[Personality]:
        """Single LLM call to generate N personalities for one role."""
        response = await PERSONALITY_BATCH.execute(
            self._router,
            _seed=self._seed,
            **base_vars,
            role=role,
            count=str(count),
            personality_hint=hint or role,
        )
        parsed = PERSONALITY_BATCH.parse_json_response(response)
        return self.parse_role_batch(parsed, count)

    def parse_role_batch(
        self,
        parsed: Any,
        count: int,
    ) -> list[Personality]:
        """Normalize raw LLM output into concrete personality models."""
        if isinstance(parsed, dict) and "personalities" in parsed:
            items = parsed["personalities"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = [parsed]

        personalities: list[Personality] = []
        for item in items:
            personalities.append(
                Personality(
                    style=item.get("style", "balanced"),
                    response_time=item.get("response_time", "5m"),
                    strengths=item.get("strengths", []),
                    weaknesses=item.get("weaknesses", []),
                    description=item.get("description", ""),
                    traits=item.get("traits", {}),
                )
            )

        # If LLM returned fewer than count, duplicate last to fill
        if len(personalities) < count:
            logger.warning(
                "LLM returned %d personalities for role, expected %d — duplicating last to fill",
                len(personalities),
                count,
            )
            while len(personalities) < count:
                personalities.append(personalities[-1])

        return personalities[:count]

    async def generate_friction_profile(
        self,
        category: Literal["uncooperative", "deceptive", "hostile"],
        intensity: int,
        sophistication: Literal["low", "medium", "high"],
        domain_context: str = "",
    ) -> FrictionProfile:
        """Friction profiles use SimpleActorGenerator — deterministic from dimension values."""
        return await self._fallback.generate_friction_profile(
            category, intensity, sophistication, domain_context
        )

    async def generate_batch(
        self,
        actor_specs: list[dict[str, Any]],
        conditions: WorldConditions,
        ctx: WorldGenerationContext,
    ) -> list[ActorDefinition]:
        """Generate batch: structure from SimpleActorGenerator, personalities from LLM.

        Groups actors by ROLE — makes ONE LLM call per role, not per actor.
        """
        if not self._router:
            raise CompilerError("LLM router required for actor generation")

        # SimpleActorGenerator provides STRUCTURE: count expansion, friction
        # distribution, type mapping. Deterministic math, NOT heuristic.
        actors = await self.expand_actor_structure(actor_specs, conditions, ctx)

        # Group actors by role for batch LLM calls (1 call per role)
        actors_by_role: dict[str, list[int]] = {}
        for i, actor in enumerate(actors):
            actors_by_role.setdefault(actor.role, []).append(i)

        # ONE LLM call per role (not per actor)
        enriched = list(actors)  # copy list so we can update in-place
        for role, indices in actors_by_role.items():
            count = len(indices)
            hint = actors[indices[0]].personality_hint or role

            personalities = await self.generate_role_batch(
                role=role,
                count=count,
                personality_hint=hint,
                ctx=ctx,
            )

            for j, actor_idx in enumerate(indices):
                enriched[actor_idx] = enriched[actor_idx].model_copy(
                    update={"personality": personalities[j]}
                )

        return enriched
