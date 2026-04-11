"""Runtime context for the World Animator engine.

REUSES: WorldGenerationContext pattern from world_compiler/generation_context.py
REUSES: ConditionExpander.build_prompt_context() (same as D4b)
Adds: runtime state snapshot, recent actions, per-attribute probabilities

Built ONCE when animator is configured, used each tick for organic generation.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from volnix.engines.world_compiler.generation_context import (
    WorldGenerationContext,
)
from volnix.engines.world_compiler.plan import WorldPlan

logger = logging.getLogger(__name__)


# Type alias for the state-reader callable injected into AnimatorContext.
# Returns a dict mapping entity_type -> list of entity dicts.
StateReader = Callable[[], Awaitable[dict[str, list[dict[str, Any]]]]]


# Entity types that are game-internal and should never leak into the
# organic animator's prompt. Blueprint authors can extend this via
# ``world.animator.state_snapshot_exclude`` in YAML.
_DEFAULT_EXCLUDE_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "negotiation_target",
        "negotiation_scorecard",
        "negotiation_proposal",
        # scoring / game-internal entities must not shape organic events
    }
)

# Maximum number of entity samples included in the snapshot per entity
# type. Prevents the prompt from ballooning when a world has hundreds of
# entities of one type.
_SNAPSHOT_SAMPLE_CAP: int = 3

# Fields preferred when summarizing an entity sample (if present), in
# priority order. We include up to 4 fields per entity sample.
_PREFERRED_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "title",
    "status",
    "severity",
    "region",
    "type",
    "state",
    "priority",
    "value",
    "count",
    "level",
)

_MAX_FIELDS_PER_SAMPLE: int = 4


class AnimatorContext:
    """Runtime context for the Animator -- mirrors WorldGenerationContext pattern.

    REUSES: ConditionExpander.build_prompt_context() (same as D4b)
    REUSES: WorldPlan fields (same as D4b)
    Adds: runtime state snapshot, recent actions, tick info

    Built ONCE when animator is configured, updated each tick.

    State-awareness is **optional**. If no ``state_reader`` is provided,
    the context behaves exactly as before (backward compat). If a reader
    is provided, ``for_organic_generation`` becomes state-aware: it
    fetches a capped, filtered snapshot of the current world entities
    and injects it into the ANIMATOR_EVENT prompt via the
    ``entity_snapshot`` template variable.
    """

    def __init__(
        self,
        plan: WorldPlan,
        available_tools: list[dict[str, Any]] | None = None,
        state_reader: StateReader | None = None,
        state_snapshot_exclude: list[str] | None = None,
    ) -> None:
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

        # Optional state reader for dynamic snapshots (P3). None means
        # backward-compat behavior: no state snapshot in the prompt.
        self._state_reader: StateReader | None = state_reader

        # Excluded entity types: defaults + blueprint override.
        # Blueprints can extend via ``animator.state_snapshot_exclude``.
        excluded = set(_DEFAULT_EXCLUDE_ENTITY_TYPES)
        if state_snapshot_exclude:
            excluded.update(str(e) for e in state_snapshot_exclude)
        self._snapshot_exclude: frozenset[str] = frozenset(excluded)

    async def for_organic_generation(
        self, recent_actions: list[dict[str, Any]] | None = None
    ) -> dict[str, str]:
        """Variables for ANIMATOR_EVENT template -- includes per-attribute numbers.

        Async because it may fetch a state snapshot from the state
        engine via the injected ``state_reader``. If no reader was
        provided, returns a synchronous snapshot-free context.

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
            tool_info.append(
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "service": t.get("pack_name", ""),
                    "required_params": properties,
                }
            )

        entity_snapshot_text = await self._build_entity_snapshot_text()

        return {
            "reality_summary": self.reality_summary,
            "reality_dimensions": json.dumps(self.dimensions, indent=2),
            "behavior_mode": self.behavior,
            "behavior_description": self.behavior_description,
            "domain_description": self.domain,
            "available_tools": json.dumps(tool_info, indent=2),
            "actors": json.dumps(self.actors, indent=2) if self.actors else "[]",
            "entity_snapshot": entity_snapshot_text,
        }

    async def _build_entity_snapshot_text(self) -> str:
        """Fetch and format the current entity snapshot for the prompt.

        Returns a human-readable text block like::

            - weather_alert (1 total):
              - td_18w: severity=Tropical Depression, region=South China Sea
            - port (6 total):
              - haiphong: status=open, congestion_level=low
              ...

        If no state reader is configured, returns a placeholder string.
        If the reader raises, logs the error and returns a placeholder
        (the animator should never crash because state is unavailable).
        """
        if self._state_reader is None:
            return "(state snapshot unavailable — reader not configured)"

        try:
            snapshot = await self._state_reader()
        except Exception as exc:
            logger.warning(
                "Animator state snapshot reader failed: %s — returning "
                "placeholder so organic generation can still run.",
                exc,
            )
            return "(state snapshot unavailable — reader raised)"

        if not snapshot:
            return "(no entities in world yet)"

        lines: list[str] = []
        for entity_type in sorted(snapshot.keys()):
            if entity_type in self._snapshot_exclude:
                continue
            entities = snapshot[entity_type]
            if not isinstance(entities, list):
                continue
            total = len(entities)
            sample = entities[:_SNAPSHOT_SAMPLE_CAP]
            lines.append(f"- {entity_type} ({total} total):")
            for entity in sample:
                if not isinstance(entity, dict):
                    continue
                summary = self._summarize_entity(entity)
                lines.append(f"  - {summary}")

        if not lines:
            return "(no world-owned entities — only game internals present)"

        return "\n".join(lines)

    @staticmethod
    def _summarize_entity(entity: dict[str, Any]) -> str:
        """Summarize a single entity dict as a compact one-liner for the prompt.

        Picks the entity's id (or name, or title) as the head, then up
        to ``_MAX_FIELDS_PER_SAMPLE`` preferred fields as ``key=value``.
        Skips list/dict values to keep the line flat.
        """
        head = str(entity.get("id") or entity.get("name") or entity.get("title") or "")
        selected: list[str] = []
        for field in _PREFERRED_SNAPSHOT_FIELDS:
            if field in {"id", "name", "title"}:
                continue  # already used as head
            if field not in entity:
                continue
            val = entity[field]
            if isinstance(val, (list, dict)):
                continue
            selected.append(f"{field}={val}")
            if len(selected) >= _MAX_FIELDS_PER_SAMPLE:
                break
        if head and selected:
            return f"{head}: {', '.join(selected)}"
        if head:
            return head
        if selected:
            return ", ".join(selected)
        # Fallback: raw dict stringified (capped length)
        return str(entity)[:120]

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
