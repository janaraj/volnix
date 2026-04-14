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

from volnix.llm.router import LLMRouter
from volnix.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _strip_surrogates(obj: Any) -> Any:
    """Recursively remove Unicode surrogate characters from parsed JSON.

    Local LLMs (Ollama) can produce lone surrogates that are valid in
    Python strings but cause UnicodeEncodeError when serialized to
    UTF-8 or JSON downstream.
    """
    if isinstance(obj, str):
        return _SURROGATE_RE.sub("", obj)
    if isinstance(obj, dict):
        return {k: _strip_surrogates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_surrogates(v) for v in obj]
    return obj


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
        _output_schema: dict[str, Any] | None = None,
        **variables: Any,
    ) -> LLMResponse:
        """Render, send to LLM, return response."""
        sys_prompt, user_prompt = self.render(**variables)
        request = LLMRequest(
            system_prompt=sys_prompt,
            user_content=user_prompt,
            output_schema=_output_schema or self.output_schema,
            seed=_seed,
        )
        return await router.route(request, self.engine_name, self.use_case)

    def parse_json_response(self, response: LLMResponse) -> dict[str, Any]:
        """Extract JSON from LLM response (structured output or content parsing)."""
        # Check for LLM provider errors first
        if response.error:
            from volnix.core.errors import LLMError

            raise LLMError(
                f"LLM provider returned error: {response.error[:200]}",
                context={
                    "provider": response.provider,
                    "model": response.model,
                },
            )

        if response.structured_output:
            return _strip_surrogates(response.structured_output)

        content = response.content.strip()
        if not content:
            from volnix.core.errors import LLMError

            raise LLMError(
                "LLM returned empty response (no content, no error)",
                context={
                    "provider": response.provider,
                    "model": response.model,
                },
            )

        # Strip markdown code block wrappers (greedy — handle truncated responses)
        # Remove opening ```json or ```
        content = re.sub(r"^```(?:json)?\s*\n?", "", content)
        # Remove closing ```
        content = re.sub(r"\n?\s*```\s*$", "", content)
        content = content.strip()

        # Strip trailing commas before } or ] (common LLM quirk, especially Gemini)
        content = re.sub(r",\s*([}\]])", r"\1", content)

        # Try direct parse
        try:
            return _strip_surrogates(json.loads(content))
        except json.JSONDecodeError:
            pass

        # Try to find JSON object or array in the response
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = content.find(start_char)
            end = content.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return _strip_surrogates(json.loads(content[start : end + 1]))
                except json.JSONDecodeError:
                    continue

        # Handle truncated JSON arrays — if response was cut off by token limit,
        # the array may be missing its closing bracket. Try progressively shorter
        # truncations until we find valid JSON.
        arr_start = content.find("[")
        if arr_start != -1:
            # Try each } from the end backwards until we find valid JSON
            search_from = len(content)
            for _ in range(50):  # max 50 attempts (complex nested entities need more)
                last_obj_end = content.rfind("}", 0, search_from)
                if last_obj_end == -1 or last_obj_end <= arr_start:
                    break
                truncated = content[arr_start : last_obj_end + 1] + "]"
                try:
                    result = json.loads(truncated)
                    if isinstance(result, list) and result:
                        return _strip_surrogates(result)
                except json.JSONDecodeError:
                    pass
                search_from = last_obj_end

        raise ValueError(f"Could not parse JSON from LLM response: {content[:200]}")


# ── NL → World Definition Template ──────────────────────────────

NL_TO_WORLD_DEF = PromptTemplate(
    system="""You are Volnix's world definition interpreter.

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
    system="""Generate Volnix compiler settings as JSON.

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
    system="""You are Volnix's world compiler. Generate realistic {entity_type} entities.

## World Description
{domain_description}

## Mission
{mission}

## Reality — The World's Personality
These are personality traits, not engineering parameters. Interpret them holistically.
Generate narratively coherent data — entities should have REASONS for their state,
not randomly corrupted fields.

{reality_summary}

## Behavior Mode
{behavior_mode}

## Actors in This World
{actor_summary}

## Governance Policies
{policies_summary}

## Seed Scenarios (MUST appear in generated entities)
{seed_scenarios}
These specific situations MUST exist in the generated world.
Weave them naturally into the entities — they should feel organic,
not bolted on. Characters, amounts, and timelines from seeds should
appear as real entities with proper cross-references.

## Entity Schema
{entity_schema}

## Existing Entity References
{existing_refs}
For any field with x-volnix-ref in the schema, you MUST use an ID from the
valid_ids list above. The "samples" show what those entities look like — use them
to create coherent relationships (e.g., assign tweets to users matching their personality).
If "none", this entity type has no reference dependencies — generate fresh IDs.

## Rules
- Generate exactly {count} {entity_type} entities as a valid JSON array
- Each entity MUST conform to the schema above (required fields, valid types, enum values)
- Reference fields MUST use IDs from the existing_refs valid_ids lists
- Keep text fields concise: descriptions 1-2 sentences, subjects under 80 chars
- Focus on facts an agent needs (who, what, status, urgency), not prose
- Output ONLY a valid JSON array. No markdown, no explanation.""",
    user="Generate {count} {entity_type} entities for this world.",
    engine_name="data_generator",
    use_case="default",
)


# ── Personality Batch Template (per-role, not per-actor) ─────────

PERSONALITY_BATCH = PromptTemplate(
    system="""You are Volnix's actor personality generator.

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
    system="""You are Volnix's seed expander.

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
Each entity type shows: existing entity IDs, field schema, and reference constraints.
If a field has a "references" annotation (e.g. "author_id" → "reddit_user"), the value MUST be an ID from that entity type.
{available_entities}

## Rules
- Modify existing entities or create new ones to establish the seed
- Use "fields" key for entity data (not "properties")
- Reference fields (author_id, channel_id, etc.) MUST use IDs from the CORRECT entity type shown in "references"
- NEVER cross entity types: a reddit comment's author_id must reference a reddit_user, not a twitter user
- New entities MUST only use field names listed in the "fields" schema for that entity type
- Large numbers in seeds (e.g. "50K mentions") → store as FIELD VALUE on entity, NOT as count invariant
- Prefer modifying existing entities over creating new ones

## CRITICAL: Invariant Rules
- Invariants VERIFY that your entity changes were applied correctly
- ONLY use "exists" invariants with selector matching the entity's "id" field
- One invariant per entity you create or modify — just verify it exists by ID
- NEVER use "field_equals", "count", "references", or "temporal" invariants
- NEVER use complex objects as values in selectors — only simple string IDs
- Keep it simple: if you created entity with id "ticket-seed-001", your invariant is {{"kind": "exists", "selector": {{"entity_type": "ticket", "match": {{"id": "ticket-seed-001"}}}}}}

Output JSON:
{{
  "entities_to_create": [
    {{"entity_type": "ticket", "fields": {{"id": "ticket-seed-001", "subject": "...", ...}}}}
  ],
  "entities_to_modify": [
    {{"entity_type": "ticket", "entity_id": "existing-ticket-id", "field_updates": {{"status": "escalated"}}}}
  ],
  "invariants": [
    {{"kind": "exists", "selector": {{"entity_type": "ticket", "match": {{"id": "ticket-seed-001"}}}}}},
    {{"kind": "exists", "selector": {{"entity_type": "ticket", "match": {{"id": "existing-ticket-id"}}}}}}
  ]
}}

Output ONLY valid JSON.""",
    user="Expand this seed scenario: {seed_description}",
    engine_name="world_compiler",
    use_case="default",
)


# ── Profile Inference Template ──────────────────────────────────

PROFILE_INFER = PromptTemplate(
    system="""You are Volnix's service profiler. Generate a structured service profile
for the given service. This profile will be used to simulate the service's API.

Output ONLY valid YAML matching this structure:
profile_name: <service>
service_name: <service>
category: <category>
operations:
  - name: <service>_<action>
    service: <service>
    http_method: <GET|POST|PUT|DELETE>
    http_path: <real API path>
    description: <what it does>
    parameters:
      param_name: {{type: string}}
    required_params: [param1, param2]
    response_schema:
      type: object
      properties:
        field_name: {{type: string}}
    is_read_only: false
    creates_entity: <entity_type or null>
    mutates_entity: <entity_type or null>
entities:
  - name: <entity>
    identity_field: id
    fields:
      field_name: {{type: string}}
    required: [field1, field2]
state_machines:
  - entity_type: <entity>
    field: status
    transitions:
      state1: [state2, state3]
error_modes:
  - code: <ERROR_CODE>
    when: <condition>
    http_status: <400|403|404|409>
behavioral_notes:
  - <note1>
  - <note2>
responder_prompt: |
  You are simulating the <service> API. <instructions>

Output ONLY valid YAML. No markdown, no explanation.""",
    user="""Generate a service profile for: {service_name}

Category: {category}

{available_docs}

Include realistic operations, entities, state machines, error modes, and a responder prompt.
Base the operations on the real API if you know it.""",
    engine_name="profile_infer",
    use_case="default",
)


SECTION_REPAIR = PromptTemplate(
    system="""You are Volnix's compiler repair assistant.

Repair ONLY the failing section described below. Do not change the section type,
shape, or count unless the validation errors require it.

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

## Section
Kind: {section_kind}
Name: {section_name}

## Validation Errors
{validation_errors}

## Relevant Contracts
{relevant_schema}

## Output Contract
{output_contract}

## Failing Payload
{failing_payload}

## Repair Rules
- If an entity references a missing entity (e.g. "comment.author_id references missing user"),
  ADD the missing entity to entities_to_create with a valid schema
- If a field has an invalid value, fix the value
- Do not remove entities — fix their references instead

Output ONLY the repaired payload as valid JSON. No markdown, no explanation.""",
    user="Repair this failing {section_kind} section: {section_name}",
    engine_name="world_compiler",
    use_case="section_repair",
)


# ── Animator Event Template ──────────────────────────────────────

ANIMATOR_EVENT = PromptTemplate(
    system="""You are the World Animator for a Volnix simulation.
Generate organic world events that happen between agent turns.

## World Reality (ongoing creative direction)
{reality_summary}

## Reality Dimensions (per-attribute intensity)
{reality_dimensions}

## Behavior Mode
{behavior_mode}: {behavior_description}

## Domain
{domain_description}

## Actors in the World
{actors}

## Current World State (entity snapshot — capped at 3 samples per type)
{entity_snapshot}

## Recent Agent Actions
{recent_actions}

## Previous Organic Events (from earlier ticks)
{recent_organic}

## Animator Settings
Creativity: {creativity}, Frequency: {event_frequency}
Escalation on inaction: {escalation_on_inaction}

## Available Tools (you MUST only use these action names)
{available_tools}

## Rules
- Generate up to {budget} events as a JSON array
- Each event:
  {{"actor_id": "<role from actors list>", "service_id": "service_name",
    "action": "tool_name_from_list_above",
    "input_data": {{"<fill ALL required_params from the tool definition>": "..."}},
    "sub_type": "organic"}}
- input_data MUST contain ALL fields listed in the tool's required_params.
  Look up the action in Available Tools above and populate every required field
  with a realistic value. Events with missing required fields will be rejected.
- Use actor roles from the Actors list — events come FROM characters in the world
- VARY the actor across ticks — rotate through different roles, don't always pick the same one
- If no actors are defined, use "system" as actor_id
- You MUST use action names from the Available Tools list — do NOT invent actions
- Use the service name from the tool's "service" field as service_id
- Reality dimensions shape what happens (messy = things go wrong, hostile = active opposition)
- When the entity snapshot above shows specific entities, PREFER updating/extending
  those existing entities over creating generic new ones. That keeps the world
  coherent — e.g., if there's a weather_alert named td_18w, evolve IT rather
  than spawning a second unrelated storm.
- Events go through the governance pipeline — they CAN be blocked by policies
- When generating events that reference specific entities (users, channels, pages,
  databases), use ONLY entity IDs visible in the Current World State snapshot above.
  Do NOT invent entity IDs — if no matching entity exists in the snapshot, skip that
  event type and use a different action instead.

Output ONLY valid JSON array.""",
    user="Generate up to {budget} world events.",
    engine_name="animator",
    use_case="default",
)


# ── Policy Trigger Compilation Template ─────────────────────────

POLICY_TRIGGER_COMPILATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "compiled_policies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "policy_name": {"type": "string"},
                    "triggers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string"},
                                "condition": {"type": "string"},
                            },
                            "required": ["action"],
                        },
                    },
                    "unresolvable": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["policy_name", "triggers"],
            },
        }
    },
    "required": ["compiled_policies"],
}

POLICY_TRIGGER_COMPILATION = PromptTemplate(
    system="""You are Volnix's policy trigger compiler.
Given natural-language policy triggers and the available API operations,
compile each NL trigger into structured dict triggers matching specific operations.

## Available API Operations
{available_operations}

## Rules
- Map each NL trigger to the specific operation(s) it refers to.
- Use EXACT operation names from the list above as the "action" field.
- If the trigger describes a condition (e.g., "amount exceeds $100"), add a
  "condition" field using the expression syntax: "input.<field> <operator> <value>"
  (e.g., "input.amount > 10000").
- If the trigger mentions a class of operations (e.g., "all list operations"),
  create one trigger entry per matching operation.
- If the trigger cannot map to any available operation (e.g., it describes
  a conceptual situation not tied to an API call), set "unresolvable" to true
  and explain in "reason".
- Do NOT invent operation names — only use names from the provided list.

Output ONLY valid JSON.""",
    user="Compile these policy triggers:\n\n{policy_triggers}",
    output_schema=POLICY_TRIGGER_COMPILATION_SCHEMA,
    engine_name="world_compiler",
    use_case="policy_trigger_compilation",
)
