"""Generate visibility rules from world context via LLM.

The compiler calls this during the actor compilation phase. The LLM
sees the world description, service topology, actor role/permissions,
and generates appropriate visibility rules. NO hardcoded rules — the LLM
infers what each actor role should see based on world context.

Follows the exact same pattern as SubscriptionGenerator.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from volnix.core.types import VisibilityRule
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.engines.world_compiler.prompt_templates import PromptTemplate
from volnix.llm.router import LLMRouter

logger = logging.getLogger(__name__)


# ── Prompt Template ──────────────────────────────────────────────


VISIBILITY_RULE_GENERATION = PromptTemplate(
    system="""You are Volnix's visibility rule generator. Given an actor's role
and the world context, determine what entities this actor should be able to see.

Visibility rules define entity-level scoping — WHICH entities of each type
an actor can access. This is separate from service-level permissions (read/write
access to entire services).

## World Description
{domain_description}

## Available Services and Entity Types
{services_summary}

## Actors
{actor_summary}

## Policies
{policies_summary}

## Rules
- Each rule targets a specific entity type (must be one listed above) or "*" for all
- filter_field: the entity field to match on (e.g. "requester_id", "assignee_id", "author_id")
- filter_value: value to match. Use "$self.actor_id" when the actor should only see their own
- include_unmatched: true = also include entities where filter_field is null/empty (e.g. unassigned tickets)
- filter_field=null means see ALL entities of that type (supervisors, admins)
- target_entity_type="*" with filter_field=null = full access to everything
- Consider: customers see their own data, agents see assigned + unassigned, supervisors see all

Output JSON array:
[
  {{
    "id": "vr_<role>_<entity_type>",
    "actor_role": "<role>",
    "target_entity_type": "<entity_type or *>",
    "filter_field": "<field or null>",
    "filter_value": "<value or $self.actor_id or null>",
    "include_unmatched": false,
    "description": "<what this rule means>"
  }}
]

Output ONLY valid JSON array. No markdown, no explanation.""",
    user="""Generate visibility rules for this actor:

Role: {actor_role}
Type: {actor_type}
Permissions: {actor_permissions}
Visibility hints: {visibility_hints}""",
    engine_name="world_compiler",
    use_case="visibility_rule_generation",
)


# ── Generator Class ──────────────────────────────────────────────


class VisibilityRuleGenerator:
    """LLM-based visibility rule inference at compile time."""

    def __init__(self, llm_router: LLMRouter, seed: int = 42) -> None:
        self._router = llm_router
        self._seed = seed

    async def generate_for_role(
        self,
        actor_spec: dict[str, Any],
        plan: WorldPlan,
        context_vars: dict[str, str],
    ) -> list[VisibilityRule]:
        """Generate visibility rules for one actor role.

        Args:
            actor_spec: Actor spec dict with role, type, permissions, visibility.
            plan: The compiled WorldPlan (for entity type validation).
            context_vars: Base context variables from WorldGenerationContext.

        Returns:
            List of validated VisibilityRule objects.
        """
        # Build services_summary from plan (same pattern as SubscriptionGenerator)
        services_lines: list[str] = []
        for svc_name, resolution in (plan.services or {}).items():
            entity_types = list(resolution.surface.entity_schemas.keys())
            services_lines.append(f"- {svc_name}: entities={entity_types}")
        services_summary = "\n".join(services_lines) if services_lines else "No services."

        response = await VISIBILITY_RULE_GENERATION.execute(
            self._router,
            _seed=self._seed,
            **context_vars,
            services_summary=services_summary,
            actor_role=actor_spec.get("role", ""),
            actor_type=actor_spec.get("type", "internal"),
            actor_permissions=json.dumps(actor_spec.get("permissions", {})),
            visibility_hints=json.dumps(actor_spec.get("visibility") or {}),
        )
        parsed = VISIBILITY_RULE_GENERATION.parse_json_response(response)
        return self._parse_rules(parsed, plan)

    def _parse_rules(
        self,
        parsed: Any,
        plan: WorldPlan,
    ) -> list[VisibilityRule]:
        """Parse and validate LLM output into VisibilityRule objects."""
        if not isinstance(parsed, list):
            parsed = parsed.get("rules", []) if isinstance(parsed, dict) else []

        # Collect known entity types from plan services
        known_types: set[str] = set()
        if hasattr(plan, "services"):
            for svc in plan.services.values():
                if hasattr(svc, "surface") and hasattr(svc.surface, "entity_schemas"):
                    known_types.update(svc.surface.entity_schemas.keys())

        rules: list[VisibilityRule] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            target = item.get("target_entity_type", "")
            # Validate entity type exists (or is wildcard)
            if target != "*" and known_types and target not in known_types:
                logger.debug(
                    "Skipping visibility rule for unknown entity type: %s",
                    target,
                )
                continue
            try:
                rules.append(VisibilityRule(**item))
            except Exception as exc:
                logger.debug("Skipping invalid visibility rule: %s (%s)", item, exc)
                continue
        return rules
