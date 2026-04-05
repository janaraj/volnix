"""Runtime context for the World Animator engine.

REUSES: WorldGenerationContext pattern from world_compiler/generation_context.py
REUSES: ConditionExpander.build_prompt_context() (same as D4b)
Adds: runtime state snapshot, recent actions, per-attribute probabilities

Built ONCE when animator is configured, used each tick for organic generation.
"""

from __future__ import annotations

import json
from typing import Any

from volnix.engines.world_compiler.generation_context import (
    BEHAVIOR_DESCRIPTIONS,
    WorldGenerationContext,
)
from volnix.engines.world_compiler.plan import WorldPlan


class AnimatorContext:
    """Runtime context for the Animator -- mirrors WorldGenerationContext pattern.

    REUSES: ConditionExpander.build_prompt_context() (same as D4b)
    REUSES: WorldPlan fields (same as D4b)
    Adds: runtime state snapshot, recent actions, tick info

    Built ONCE when animator is configured, updated each tick.
    """

    def __init__(self, plan: WorldPlan, available_tools: list[dict[str, Any]] | None = None) -> None:
        # REUSE the SAME context builder as D4b
        self._base = WorldGenerationContext(plan)

        # Extract per-attribute numbers (Level 2) for probabilistic decisions
        self.dimension_values: dict[str, dict[str, Any]] = {}
        for dim_name in ["information", "reliability", "friction", "complexity", "boundaries"]:
            dim = getattr(plan.conditions, dim_name)
            self.dimension_values[dim_name] = dim.to_dict()

        # Expose base context fields
        self.reality_summary: str = self._base.reality_summary
        self.dimensions: dict[str, Any] = self._base.dimensions
        self.behavior: str = self._base.behavior
        self.behavior_description: str = self._base.behavior_description
        self.domain: str = self._base.domain

        # Available tools from pack registry — used by both probabilistic
        # and organic generators to produce valid actions only
        self.available_tools: list[dict[str, Any]] = available_tools or []

        # Actors from world plan — used by organic generator to assign
        # events to characters in the world (not "system")
        self.actors: list[dict[str, Any]] = [
            {
                "role": spec.get("role", "unknown"),
                "type": spec.get("type", "internal"),
                "personality": spec.get("personality", ""),
            }
            for spec in (plan.actor_specs or [])
        ]

    def for_organic_generation(
        self, recent_actions: list[dict[str, Any]] | None = None
    ) -> dict[str, str]:
        """Variables for ANIMATOR_EVENT template -- includes per-attribute numbers.

        Args:
            recent_actions: Optional list of recent agent actions for reactive mode.

        Returns:
            Dict of template variables for the ANIMATOR_EVENT prompt template.
        """
        # Include parameter schemas so the LLM generates valid input_data
        tool_info = []
        for t in self.available_tools:
            params = t.get("parameters", {})
            required = params.get("required", [])
            properties = {
                k: {"type": v.get("type", "string"), "description": v.get("description", "")}
                for k, v in params.get("properties", {}).items()
                if k in required
            }
            tool_info.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "service": t.get("pack_name", ""),
                "required_params": properties,
            })
        return {
            "reality_summary": self.reality_summary,
            "reality_dimensions": json.dumps(self.dimensions, indent=2),
            "behavior_mode": self.behavior,
            "behavior_description": self.behavior_description,
            "domain_description": self.domain,
            "available_tools": json.dumps(tool_info, indent=2),
            "actors": json.dumps(self.actors, indent=2) if self.actors else "[]",
        }

    def get_probability(self, dimension: str, attribute: str) -> float:
        """Get a per-attribute intensity as a probability (0.0-1.0).

        Used by the animator for probabilistic decisions:
        - reliability.failures=20 -> 0.20 (20% chance per tick)
        - friction.deceptive=15 -> 0.15

        Args:
            dimension: The dimension name (e.g. "reliability").
            attribute: The attribute name (e.g. "failures").

        Returns:
            The probability as a float between 0.0 and 1.0.
            Returns 0.0 for non-numeric attributes or missing values.
        """
        dim_vals = self.dimension_values.get(dimension, {})
        raw = dim_vals.get(attribute, 0)
        if isinstance(raw, (int, float)):
            return raw / 100.0
        return 0.0
