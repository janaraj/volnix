"""LLM prompt templates for the world compiler.

All LLM interactions in the compiler use PromptTemplate objects.
Templates are data — prompts are not hardcoded inline.
New compilation features add new templates, not new code.

Every generation template receives the FULL WorldGenerationContext via
its variable dict. No partial context — the LLM always sees:
  - Reality narrative (world's personality traits)
  - Behavior mode (static/dynamic/reactive)
  - Domain description + mission
  - Governance policies
  - Actor summary
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from terrarium.llm.router import LLMRouter
from terrarium.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class PromptTemplate:
    """Reusable prompt template for LLM interactions."""

    def __init__(
        self,
        system: str,
        user: str,
        output_schema: dict[str, Any] | None = None,
        engine_name: str = "world_compiler",
        use_case: str = "default",
    ) -> None:
        self.system = system
        self.user = user
        self.output_schema = output_schema
        self.engine_name = engine_name
        self.use_case = use_case

    def render(self, **variables: Any) -> tuple[str, str]:
        """Render system + user prompts with template variables."""
        try:
            sys_prompt = self.system.format(**variables)
            user_prompt = self.user.format(**variables)
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")
        return sys_prompt, user_prompt

    async def execute(
        self,
        router: LLMRouter,
        _seed: int | None = None,
        **variables: Any,
    ) -> LLMResponse:
        """Render, send to LLM, return response."""
        sys_prompt, user_prompt = self.render(**variables)
        request = LLMRequest(
            system_prompt=sys_prompt,
            user_content=user_prompt,
            output_schema=self.output_schema,
            seed=_seed,
        )
        return await router.route(request, self.engine_name, self.use_case)

    def parse_json_response(self, response: LLMResponse) -> dict[str, Any]:
        """Extract JSON from LLM response (structured output or content parsing)."""
        if response.structured_output:
            return response.structured_output

        content = response.content.strip()
        if not content:
            raise ValueError("LLM returned empty response")

        # Strip markdown code block wrappers (greedy — handle truncated responses)
        # Remove opening ```json or ```
        content = re.sub(r'^```(?:json)?\s*\n?', '', content)
        # Remove closing ```
        content = re.sub(r'\n?\s*```\s*$', '', content)
        content = content.strip()

        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object or array in the response
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = content.find(start_char)
            end = content.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    continue

        # Handle truncated JSON arrays — if response was cut off by token limit,
        # the array may be missing its closing bracket. Try to salvage by finding
        # the last complete object and closing the array.
        arr_start = content.find("[")
        if arr_start != -1:
            # Find last complete object (ending with })
            last_obj_end = content.rfind("}")
            if last_obj_end != -1 and last_obj_end > arr_start:
                truncated = content[arr_start:last_obj_end + 1] + "]"
                try:
                    return json.loads(truncated)
                except json.JSONDecodeError:
                    pass

        raise ValueError(f"Could not parse JSON from LLM response: {content[:200]}")


# ── NL → World Definition Template ──────────────────────────────

NL_TO_WORLD_DEF = PromptTemplate(
    system="""You are Terrarium's world definition interpreter.

Given a natural language description, produce a structured world definition as JSON.

The output MUST contain:
- "world": {{
    "name": "short name",
    "description": "expanded description",
    "services": {{"service_name": "pack_reference"}},
    "actors": [{{
      "role": "...",
      "count": N,
      "type": "external|internal",
      "personality": "...",
      "permissions": {{"read": [...], "write": [...], "actions": {{}}}},
      "budget": {{"api_calls": N, "llm_spend": N}}
    }}],
    "policies": [{{
      "name": "...",
      "description": "...",
      "trigger": "condition that activates policy",
      "enforcement": "hold|block|escalate|log",
      "hold_config": {{"approver_role": "...", "timeout": "..."}}
    }}],
    "seeds": ["specific scenario descriptions"],
    "mission": "what success looks like"
  }}

Known semantic categories: {categories}
Known verified packs: {verified_packs}

For services with verified packs, use "verified/pack_name".
For services with profiles, use "profiled/service_name".
For unknown services, use the bare service name (the compiler will resolve it).

Output ONLY valid JSON. No markdown, no explanation.""",

    user="""Create a world definition for this description:

{description}""",

    engine_name="world_compiler",
    use_case="nl_to_world_def",
)


# ── NL → Compiler Settings Template ─────────────────────────────

NL_TO_COMPILER_SETTINGS = PromptTemplate(
    system="""Generate Terrarium compiler settings as JSON.

The output MUST follow this structure:
{{
  "compiler": {{
    "seed": <integer>,
    "behavior": "<static|reactive|dynamic>",
    "fidelity": "<auto|strict|exploratory>",
    "mode": "governed",
    "reality": {{
      "preset": "<ideal|messy|hostile>"
    }},
    "animator": {{
      "creativity": "medium",
      "event_frequency": "moderate",
      "contextual_targeting": true,
      "escalation_on_inaction": true
    }}
  }}
}}

Output ONLY valid JSON.""",

    user="""Generate compiler settings for: {description}

Use these values:
- Reality: {reality}
- Behavior: {behavior}
- Fidelity: {fidelity}
- Seed: {seed}""",

    engine_name="world_compiler",
    use_case="nl_to_compiler_settings",
)


# ── Entity Generation Template ──────────────────────────────────

ENTITY_GENERATION = PromptTemplate(
    system="""You are Terrarium's world compiler. Generate realistic {entity_type} entities.

## World Description
{domain_description}

## Mission
{mission}

## Reality — The World's Personality
These are personality traits, not engineering parameters. Interpret them holistically.
Generate narratively coherent data — entities should have REASONS for their state,
not randomly corrupted fields.

{reality_summary}

Detailed dimensions:
{reality_dimensions}

## Behavior Mode
{behavior_mode}: {behavior_description}

## Actors in This World
{actor_summary}

## Governance Policies
{policies_summary}

## Entity Schema
{entity_schema}

## Rules
- Generate exactly {count} {entity_type} entities as a JSON array
- Each entity MUST conform to the schema (required fields, valid types, enum values)
- Each entity MUST have all required fields from the schema
- Entity IDs should be realistic (e.g., "email_a1b2c3", not "email_001")
- Data should reflect the reality personality — if information is "somewhat_neglected",
  some records should show signs of neglect (outdated dates, missing optional fields)
  with a REASON (e.g., "not updated since CRM migration")
- Behavior mode shapes entity states:
  - static: entities in settled/final states
  - dynamic: entities with in-flight activities and pending events
  - reactive: entities with trigger conditions waiting for agent action

Output ONLY a valid JSON array. No markdown, no explanation.""",

    user="Generate {count} {entity_type} entities for this world.",
    engine_name="data_generator",
    use_case="default",
)


# ── Personality Batch Template (per-role, not per-actor) ─────────

PERSONALITY_BATCH = PromptTemplate(
    system="""You are Terrarium's actor personality generator.

Generate {count} DISTINCT personality profiles for actors with role "{role}".

## World Context
{domain_context}

## Reality Personality
{reality_summary}

## Behavior Mode
{behavior_mode}: {behavior_description}

## Role Hint from World Definition
{personality_hint}

## Governance
{policies_summary}

## Rules
- Generate exactly {count} personality objects as a JSON array
- Each personality MUST be DISTINCT — different styles, strengths, weaknesses
- Personalities should reflect the reality dimensions (e.g., in a "messy" world,
  some actors may be disorganized or overwhelmed)
- In dynamic mode, actors should have active goals and in-progress situations
- In static mode, actors should be in settled states
- In reactive mode, actors should have trigger conditions

Each JSON object:
{{
  "style": "<methodical|creative|aggressive|cautious|balanced>",
  "response_time": "<duration like 1m, 5m, 30m, 2h>",
  "strengths": ["strength1", "strength2"],
  "weaknesses": ["weakness1", "weakness2"],
  "description": "One-paragraph narrative description of this specific actor",
  "traits": {{"key": "value"}}
}}

Output ONLY a valid JSON array of {count} objects. No markdown.""",

    user="Generate {count} distinct personalities for: {role}",
    engine_name="world_compiler",
    use_case="default",
)


# ── Seed Expansion Template ─────────────────────────────────────

SEED_EXPANSION = PromptTemplate(
    system="""You are Terrarium's seed expander.

A "seed" is a guaranteed scenario that MUST exist in the world. Expand the
natural language description into concrete entity modifications.

## World Context
{domain_description}

## Reality Personality
{reality_summary}

## Behavior Mode
{behavior_mode}: {behavior_description}

## Actors
{actor_summary}

## Governance
{policies_summary}

## Available Entities (already generated)
{available_entities}

## Rules
- Create entities or modify existing ones to establish the seed scenario
- Entity fields must use the "fields" key (not "properties")
- Reference existing entity IDs when modifying
- New entities must have realistic IDs and complete required fields
- The seed must be CONSISTENT with the reality personality and behavior mode

Output JSON:
{{
  "entities_to_create": [
    {{"entity_type": "...", "fields": {{"id": "...", ...}}}}
  ],
  "entities_to_modify": [
    {{"entity_type": "...", "entity_id": "existing_id", "field_updates": {{...}}}}
  ]
}}

Output ONLY valid JSON.""",

    user="Expand this seed scenario: {seed_description}",
    engine_name="world_compiler",
    use_case="default",
)
