"""World generation context — single source of truth for all LLM prompts.

Assembled ONCE from WorldPlan, shared by all generators (data, personality, seed).
Every LLM call in the world compiler receives the full world context through this.

Uses: ConditionExpander.build_prompt_context() (volnix/reality/expander.py)
Uses: WorldPlan fields (volnix/engines/world_compiler/plan.py)
"""

from __future__ import annotations

from typing import Any

from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.expander import ConditionExpander

# ── Behavior mode descriptions (from spec lines 65-74, 216-256) ──


BEHAVIOR_DESCRIPTIONS: dict[str, str] = {
    "static": (
        "STATIC MODE: Generate entities in settled, final states. "
        "No pending actions, no in-flight activities, no evolving situations. "
        "Everything is resolved and stable. The world is frozen after creation — "
        "only agent actions change it. Good for deterministic benchmarking."
    ),
    "dynamic": (
        "DYNAMIC MODE: Generate entities with in-flight activities, pending events, "
        "and evolving situations. Some tickets are mid-conversation, some orders are "
        "processing, some customers are waiting for responses. The world is ALIVE — "
        "it will continue generating events during simulation. Create a world with "
        "momentum and unresolved tension."
    ),
    "reactive": (
        "REACTIVE MODE: Generate entities with trigger conditions and cause-and-effect "
        "states. Entities are set up so that agent actions (or inaction) trigger "
        "realistic consequences. If the agent ignores a ticket, the customer gets "
        "frustrated. If the agent resolves it, satisfaction increases. "
        "Create a world that's waiting to REACT."
    ),
}


class WorldGenerationContext:
    """Everything the LLM needs to generate a world, assembled once from WorldPlan.

    This is the single source of truth for all generation prompts.
    Built once, passed to: WorldDataGenerator, CompilerPersonalityGenerator,
    CompilerSeedProcessor.
    """

    def __init__(self, plan: WorldPlan) -> None:
        self.plan = plan

        # Reality context (from D1 ConditionExpander — REUSE, don't rebuild)
        prompt_ctx = plan.reality_prompt_context
        if not prompt_ctx:
            expander = ConditionExpander()
            prompt_ctx = expander.build_prompt_context(plan.conditions)

        self.reality_summary: str = prompt_ctx.get("reality_summary", "")
        self.dimensions: dict[str, Any] = prompt_ctx.get("dimensions", {})

        # Behavior mode context (spec lines 65-74, 216-256)
        self.behavior: str = plan.behavior
        self.behavior_description: str = BEHAVIOR_DESCRIPTIONS.get(
            plan.behavior, BEHAVIOR_DESCRIPTIONS["dynamic"]
        )

        # Domain context
        self.domain: str = plan.description
        self.mission: str = plan.mission or "No specific mission defined."

        # Governance context
        self.policies: list[dict[str, Any]] = plan.policies
        self.policies_summary: str = self._summarize_policies()

        # Actor context
        self.actor_specs: list[dict[str, Any]] = plan.actor_specs
        self.actor_summary: str = self._summarize_actors()

        # Reproducibility
        self.seed: int = plan.seed

    def _summarize_policies(self) -> str:
        """Build human-readable policy summary for LLM context."""
        if not self.policies:
            return "No governance policies defined."
        lines: list[str] = []
        for p in self.policies:
            name = p.get("name", "unnamed")
            desc = p.get("description", "")
            enforcement = p.get("enforcement", "log")
            lines.append(f"- {name}: {desc} (enforcement: {enforcement})")
        return "\n".join(lines)

    def _summarize_actors(self) -> str:
        """Build human-readable actor summary for LLM context."""
        if not self.actor_specs:
            return "No actors defined."
        lines: list[str] = []
        for spec in self.actor_specs:
            role = spec.get("role", "?")
            count = spec.get("count", 1)
            atype = spec.get("type", "?")
            hint = spec.get("personality", "")
            line = f"- {role} x{count} ({atype})"
            if hint:
                line += f": {hint[:100]}"
            lines.append(line)
        return "\n".join(lines)

    def for_entity_generation(self) -> dict[str, str]:
        """Context variables for ENTITY_GENERATION template."""
        # Seeds go INTO the generation prompt so the LLM creates a world
        # WITH the seed scenarios already woven in naturally.
        seeds = self.plan.seeds if hasattr(self.plan, "seeds") else []
        if seeds:
            seed_text = "\n".join(f"- {s}" for s in seeds)
        else:
            seed_text = "None"

        return {
            "reality_summary": self.reality_summary,
            "reality_dimensions": "",  # Removed: narrative summary is sufficient
            "behavior_mode": self.behavior,
            "behavior_description": self.behavior_description,
            "domain_description": self.domain,
            "mission": self.mission,
            "policies_summary": self.policies_summary,
            "actor_summary": self.actor_summary,
            "seed_scenarios": seed_text,
        }

    def for_personality_batch(self) -> dict[str, str]:
        """Context variables for PERSONALITY_BATCH template."""
        return {
            "reality_summary": self.reality_summary,
            "behavior_mode": self.behavior,
            "behavior_description": self.behavior_description,
            "domain_context": self.domain,
            "policies_summary": self.policies_summary,
        }

    def for_seed_expansion(self) -> dict[str, str]:
        """Context variables for SEED_EXPANSION template."""
        return {
            "reality_summary": self.reality_summary,
            "behavior_mode": self.behavior,
            "behavior_description": self.behavior_description,
            "domain_description": self.domain,
            "policies_summary": self.policies_summary,
            "actor_summary": self.actor_summary,
        }
