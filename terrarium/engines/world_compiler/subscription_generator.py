"""Generate actor subscriptions and periodic checks from world context via LLM.

The compiler calls this during the actor compilation phase. The LLM
sees the world description, service topology, actor role/persona,
and generates appropriate subscriptions. NO hardcoded rules — the LLM
infers what each actor should listen to based on world context.
"""

from __future__ import annotations

import logging
from typing import Any

from terrarium.actors.state import ScheduledAction, Subscription
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.engines.world_compiler.prompt_templates import PromptTemplate
from terrarium.llm.router import LLMRouter

logger = logging.getLogger(__name__)


# ── Prompt Templates ─────────────────────────────────────────────


SUBSCRIPTION_GENERATION = PromptTemplate(
    system="""You are Terrarium's subscription generator. Given an actor's role,
persona, and the world context, determine what this actor should subscribe to.

Subscriptions define what events an actor is listening for. They are matched
against committed WorldEvents at runtime.

## World Description
{domain_description}

## Mission
{mission}

## Available Services and Entity Types
{services_summary}

## All Actors in This World
{actor_summary}

## Governance Policies
{policies_summary}

## Rules
- Generate subscriptions that make sense for this actor's role and responsibilities
- Each subscription targets a specific service_id (must be one of the available services)
- The filter dict contains service-specific match criteria (e.g. {{"channel": "#research"}})
- Be specific with filters — don't subscribe to everything
- Consider the actor's role: a researcher subscribes to research channels, not admin channels
- All subscriptions are immediate (actor reacts right away)

Output a JSON array of subscription objects:
[
  {{
    "service_id": "<service name>",
    "filter": {{"<key>": "<value>"}},
    "sensitivity": "immediate"
  }}
]

Output ONLY valid JSON array. No markdown, no explanation.""",
    user="""Generate subscriptions for this actor:

Role: {actor_role}
Persona: {actor_persona}
Type: {actor_type}

What should this actor subscribe to in the world?""",
    engine_name="world_compiler",
    use_case="subscription_generation",
)


PERIODIC_CHECK_GENERATION = PromptTemplate(
    system="""You are Terrarium's periodic action scheduler. Given an actor's role
and the world context, determine what periodic checks this actor should perform.

Periodic checks are ScheduledActions that fire at specific logical times during
the simulation, prompting the actor to take proactive actions.

## World Description
{domain_description}

## Mission
{mission}

## Available Services and Entity Types
{services_summary}

## All Actors in This World
{actor_summary}

## Governance Policies
{policies_summary}

## Rules
- Generate periodic checks that make sense for the actor's role
- Each check has a logical_time, action_type, description, and optional target_service
- Logical times are in seconds of simulated time (e.g. 300.0 = 5 minutes in)
- Use action_types like: "check_status", "review_progress", "follow_up", "produce_deliverable"
- The target_service must be one of the available services (or null for meta-actions)
- Don't over-schedule — 1-5 periodic checks is typical
- A lead actor should have a "produce_deliverable" check near the end

Output a JSON array of scheduled action objects:
[
  {{
    "logical_time": <float>,
    "action_type": "<action type>",
    "description": "<what the actor should do>",
    "target_service": "<service name or null>",
    "payload": {{}}
  }}
]

Output ONLY valid JSON array. No markdown, no explanation.""",
    user="""Generate periodic checks for this actor:

Role: {actor_role}
Persona: {actor_persona}
Type: {actor_type}
Is Lead: {is_lead}

What periodic actions should this actor perform during the simulation?""",
    engine_name="world_compiler",
    use_case="periodic_check_generation",
)


class SubscriptionGenerator:
    """LLM-based subscription and periodic check inference.

    Uses the same pattern as WorldDataGenerator: accepts an LLMRouter,
    builds prompts with full world context, parses LLM JSON output into
    typed domain objects.
    """

    def __init__(
        self,
        llm_router: LLMRouter,
        seed: int = 42,
    ) -> None:
        self._router = llm_router
        self._seed = seed

    async def generate_subscriptions(
        self,
        actor_spec: dict[str, Any],
        world_plan: WorldPlan,
    ) -> list[Subscription]:
        """Generate subscriptions for an actor based on world context.

        The LLM sees:
        - Actor role and persona
        - Available services and their channels/entities
        - Other actors in the world
        - The world's mission

        Returns a list of Subscription objects validated against known services.
        """
        context_vars = self._build_context_vars(world_plan)
        context_vars.update({
            "actor_role": actor_spec.get("role", "unknown"),
            "actor_persona": str(actor_spec.get("personality", "")),
            "actor_type": actor_spec.get("type", "internal"),
        })

        response = await SUBSCRIPTION_GENERATION.execute(
            self._router,
            _seed=self._seed,
            **context_vars,
        )
        parsed = SUBSCRIPTION_GENERATION.parse_json_response(response)
        return self._parse_subscriptions(parsed, world_plan)

    async def generate_periodic_checks(
        self,
        actor_spec: dict[str, Any],
        world_plan: WorldPlan,
    ) -> list[ScheduledAction]:
        """Generate periodic checks for an actor based on world context.

        Returns a list of ScheduledAction objects for proactive actor behavior.
        """
        context_vars = self._build_context_vars(world_plan)
        is_lead = actor_spec.get("lead", False) or actor_spec.get("is_lead", False)
        context_vars.update({
            "actor_role": actor_spec.get("role", "unknown"),
            "actor_persona": str(actor_spec.get("personality", "")),
            "actor_type": actor_spec.get("type", "internal"),
            "is_lead": str(is_lead),
        })

        response = await PERIODIC_CHECK_GENERATION.execute(
            self._router,
            _seed=self._seed,
            **context_vars,
        )
        parsed = PERIODIC_CHECK_GENERATION.parse_json_response(response)
        return self._parse_periodic_checks(parsed, world_plan)

    def _build_context_vars(self, plan: WorldPlan) -> dict[str, str]:
        """Build shared context variables from WorldPlan."""
        # Summarize services
        services_lines: list[str] = []
        for svc_name, resolution in plan.services.items():
            entity_types = list(resolution.surface.entity_schemas.keys())
            op_names = [op.name for op in resolution.surface.operations]
            services_lines.append(
                f"- {svc_name} (category: {resolution.surface.category}): "
                f"entities={entity_types}, operations={op_names}"
            )
        services_summary = "\n".join(services_lines) if services_lines else "No services."

        # Summarize actors
        actor_lines: list[str] = []
        for spec in plan.actor_specs:
            role = spec.get("role", "?")
            count = spec.get("count", 1)
            atype = spec.get("type", "?")
            hint = spec.get("personality", "")
            line = f"- {role} x{count} ({atype})"
            if hint:
                line += f": {str(hint)[:100]}"
            actor_lines.append(line)
        actor_summary = "\n".join(actor_lines) if actor_lines else "No actors."

        # Summarize policies
        policy_lines: list[str] = []
        for p in plan.policies:
            name = p.get("name", "unnamed")
            desc = p.get("description", "")
            enforcement = p.get("enforcement", "log")
            policy_lines.append(f"- {name}: {desc} (enforcement: {enforcement})")
        policies_summary = "\n".join(policy_lines) if policy_lines else "No policies."

        return {
            "domain_description": plan.description,
            "mission": plan.mission or "No specific mission defined.",
            "services_summary": services_summary,
            "actor_summary": actor_summary,
            "policies_summary": policies_summary,
        }

    def _parse_subscriptions(
        self,
        parsed: Any,
        plan: WorldPlan,
    ) -> list[Subscription]:
        """Parse and validate LLM output into Subscription objects."""
        items = self._normalize_list(parsed, "subscriptions")
        known_services = set(plan.services.keys())
        subscriptions: list[Subscription] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            service_id = item.get("service_id", "")
            if not service_id:
                logger.warning("Skipping subscription with empty service_id")
                continue

            # Validate service_id exists in the plan
            if service_id not in known_services:
                logger.warning(
                    "Skipping subscription for unknown service '%s' "
                    "(known: %s)",
                    service_id,
                    known_services,
                )
                continue

            filter_dict = item.get("filter", {})
            if not isinstance(filter_dict, dict):
                filter_dict = {}

            # V2: respect LLM-chosen sensitivity (batch/passive)
            # For MVP, all subscriptions activate immediately.
            sensitivity = "immediate"

            subscriptions.append(
                Subscription(
                    service_id=service_id,
                    filter=filter_dict,
                    sensitivity=sensitivity,
                )
            )

        return subscriptions

    def _parse_periodic_checks(
        self,
        parsed: Any,
        plan: WorldPlan,
    ) -> list[ScheduledAction]:
        """Parse and validate LLM output into ScheduledAction objects."""
        items = self._normalize_list(parsed, "scheduled_actions")
        known_services = set(plan.services.keys())
        actions: list[ScheduledAction] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            logical_time = item.get("logical_time", 0.0)
            if not isinstance(logical_time, (int, float)):
                continue

            action_type = item.get("action_type", "")
            if not action_type:
                continue

            description = item.get("description", action_type)

            target_service = item.get("target_service")
            if target_service and target_service not in known_services:
                # Allow null/None target_service for meta-actions
                target_service = None

            payload = item.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            actions.append(
                ScheduledAction(
                    logical_time=float(logical_time),
                    action_type=str(action_type),
                    description=str(description),
                    target_service=target_service,
                    payload=payload,
                )
            )

        return actions

    @staticmethod
    def _normalize_list(parsed: Any, key: str) -> list[Any]:
        """Normalize parsed JSON into a list of items."""
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            if key in parsed:
                return parsed[key]
            # Try common wrapper keys
            for fallback_key in ("items", "results", "data"):
                if fallback_key in parsed:
                    val = parsed[fallback_key]
                    if isinstance(val, list):
                        return val
            # Single item
            return [parsed]
        return []
