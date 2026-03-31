# Plan A: Visibility Scoping (Entity-Level)

## Context

The Permission Engine has a stub `get_visible_entities()` at `permission/engine.py:215` returning `[]`. All entity queries return ALL entities regardless of actor role. A customer sees all tickets. A junior agent sees everything a supervisor sees. This breaks information asymmetry — the #1 differentiator from multi-agent frameworks.

**Service-level permissions work** (`read: [tickets, email]` checked in `execute()` pipeline step). What's missing is **entity-level scoping** — WHICH tickets can this actor see.

## What Already Exists (verified line numbers)

| What | Where | Status |
|---|---|---|
| `get_visible_entities()` stub | `permission/engine.py:215` | Returns `[]` |
| `PermissionEngineProtocol.get_visible_entities()` | `core/protocols.py:198` | Defined in protocol |
| `ActorDefinition.visibility` field | `actors/definition.py:32` | `dict[str, Any] | None`, populated from YAML but unused |
| `StateEngine.query_entities(type, filters)` | `state/engine.py:346` | Supports key-value filter dicts |
| `PermissionEngine.dependencies` | `permission/engine.py:45` | `["state"]` — already depends on state engine |
| `_build_state_for_pack()` | `responder/engine.py:197` | Returns ALL entities, no filtering |
| `_build_state_for_profile()` | `responder/engine.py:223` | Returns ALL entities, no filtering |
| `read_entities()` | `app.py:482` | Ignores actor_id, returns all |
| `HTTP /api/v1/entities/{type}?actor_id=xxx` | `http_rest.py:~120` | Accepts actor_id but unused |
| `PermissionConfig` | `permission/config.py` | Only `cache_ttl_seconds: int = 300` |
| `SubscriptionGenerator` | `world_compiler/subscription_generator.py` | Pattern to follow for VisibilityGenerator |

## Design: Visibility Rules as Entities

At compile time, the LLM generates `visibility_rule` entities (same pattern as subscription generation). Stored in State Engine. Queried at runtime by Permission Engine.

```
Compile time:
  LLM sees: actor role + service topology + world context
  LLM outputs: visibility rules per role
  Stored as: visibility_rule entities in state.db

Runtime:
  Permission Engine queries visibility_rule entities
  Resolves $self.actor_id references
  Returns filtered entity IDs to callers

  Backward compat:
  No rules for this actor+entity_type → return [] → caller returns ALL entities
```

---

## Files to Create (3)

### 1. `terrarium/engines/world_compiler/visibility_generator.py`

Follows EXACT pattern of `subscription_generator.py`:

```python
"""Generate visibility rules from world context via LLM.

Follows the same pattern as SubscriptionGenerator: LLM infers
what each actor role should see based on world description,
service topology, and actor permissions. NO hardcoded rules.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from terrarium.core.types import WorldId
from terrarium.engines.world_compiler.prompt_templates import PromptTemplate
from terrarium.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class VisibilityRule(BaseModel, frozen=True):
    """Declarative rule for entity-level visibility scoping.

    Generated at compile time. Stored as entities in State Engine.
    Queried at runtime by Permission Engine.
    """
    id: str
    actor_role: str
    target_entity_type: str              # entity type or "*" for all
    filter_field: str | None = None      # None = see all of this type
    filter_value: str | None = None      # supports "$self.actor_id"
    include_unmatched: bool = False       # also include where field is null
    description: str = ""


VISIBILITY_RULE_GENERATION = PromptTemplate(
    system="""You are Terrarium's visibility rule generator. Given an actor's role
and the world context, determine what entities this actor should be able to see.

## World Description
{domain_description}

## Available Services and Entity Types
{services_summary}

## Actors
{actor_summary}

## Policies
{policies_summary}

## Rules
- Each rule targets a specific entity type (or "*" for all types)
- filter_field: the entity field to match (e.g. "requester_id", "assignee_id")
- filter_value: value to match. "$self.actor_id" = this actor's own ID
- include_unmatched: true = also include entities where filter_field is null/empty
- filter_field=null means see ALL entities of that type (supervisors, admins)
- target_entity_type="*" with filter_field=null = full access to everything

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

Output ONLY valid JSON array.""",
    user="""Generate visibility rules for:
Role: {actor_role}
Type: {actor_type}
Permissions: {actor_permissions}
Visibility hints: {visibility_hints}""",
    engine_name="world_compiler",
    use_case="visibility_rule_generation",
)


class VisibilityRuleGenerator:
    """LLM-based visibility rule inference at compile time."""

    def __init__(self, llm_router: LLMRouter, seed: int = 42) -> None:
        self._router = llm_router
        self._seed = seed

    async def generate_for_role(
        self,
        actor_spec: dict[str, Any],
        plan: Any,
        context_vars: dict[str, str],
    ) -> list[VisibilityRule]:
        """Generate visibility rules for one actor role."""
        response = await VISIBILITY_RULE_GENERATION.execute(
            self._router,
            _seed=self._seed,
            **context_vars,
            actor_role=actor_spec.get("role", ""),
            actor_type=actor_spec.get("type", "internal"),
            actor_permissions=json.dumps(actor_spec.get("permissions", {})),
            visibility_hints=json.dumps(actor_spec.get("visibility", {})),
        )
        parsed = VISIBILITY_RULE_GENERATION.parse_json_response(response)
        return self._parse_rules(parsed, plan)

    def _parse_rules(self, parsed: Any, plan: Any) -> list[VisibilityRule]:
        """Parse + validate LLM output into VisibilityRule objects."""
        if not isinstance(parsed, list):
            parsed = parsed.get("rules", []) if isinstance(parsed, dict) else []

        # Known entity types from plan
        known_types = set()
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
            if target != "*" and target not in known_types:
                logger.debug("Skipping visibility rule for unknown type: %s", target)
                continue
            try:
                rules.append(VisibilityRule(**item))
            except Exception:
                logger.debug("Skipping invalid visibility rule: %s", item)
                continue
        return rules
```

### 2. `tests/engines/permission/test_visibility.py`

```python
"""Tests for visibility scoping in Permission Engine.

Covers: rule resolution, $self reference, include_unmatched, wildcard,
backward compatibility (no rules = no filtering).
"""
import pytest
from terrarium.core.types import ActorId, EntityId


class TestGetVisibleEntities:
    """Tests for PermissionEngine.get_visible_entities()."""

    async def test_no_rules_returns_empty(self, stub_permission_engine):
        """No visibility_rule entities → return [] (backward compat)."""
        result = await stub_permission_engine.get_visible_entities(
            ActorId("actor-1"), "ticket"
        )
        assert result == []

    async def test_customer_sees_own_tickets(self, permission_with_rules):
        """Customer role with filter_field=requester_id sees only their tickets."""
        result = await permission_with_rules.get_visible_entities(
            ActorId("customer-1"), "ticket"
        )
        # Should contain only tickets where requester_id == "customer-1"
        assert all(isinstance(eid, EntityId) for eid in result)
        assert len(result) == 2  # fixture has 2 matching tickets

    async def test_agent_sees_assigned_plus_unassigned(self, permission_with_rules):
        """Agent with include_unmatched=True sees assigned + unassigned."""
        result = await permission_with_rules.get_visible_entities(
            ActorId("agent-1"), "ticket"
        )
        # Assigned to agent-1 (2) + unassigned (1) = 3
        assert len(result) == 3

    async def test_supervisor_sees_all(self, permission_with_rules):
        """Supervisor with filter_field=None sees all entities."""
        result = await permission_with_rules.get_visible_entities(
            ActorId("supervisor-1"), "ticket"
        )
        assert len(result) == 5  # all tickets in fixture

    async def test_wildcard_entity_type(self, permission_with_rules):
        """Rule with target_entity_type="*" applies to any entity type."""
        result = await permission_with_rules.get_visible_entities(
            ActorId("supervisor-1"), "email"
        )
        assert len(result) > 0  # wildcard covers all types

    async def test_self_reference_resolved(self, permission_with_rules):
        """$self.actor_id is replaced with actual actor ID."""
        result = await permission_with_rules.get_visible_entities(
            ActorId("customer-2"), "ticket"
        )
        # Different customer, different tickets
        assert len(result) == 1  # fixture has 1 ticket for customer-2

    async def test_multiple_rules_union(self, permission_with_rules):
        """Multiple rules for same role produce union of results."""
        # Agent has one rule for assigned tickets + one for escalated tickets
        result = await permission_with_rules.get_visible_entities(
            ActorId("agent-1"), "ticket"
        )
        assert len(result) >= 3  # assigned + unassigned + escalated


class TestHasVisibilityRules:
    async def test_no_rules_returns_false(self, stub_permission_engine):
        result = await stub_permission_engine.has_visibility_rules(
            ActorId("actor-1"), "ticket"
        )
        assert result is False

    async def test_rules_exist_returns_true(self, permission_with_rules):
        result = await permission_with_rules.has_visibility_rules(
            ActorId("customer-1"), "ticket"
        )
        assert result is True


class TestVisibilityHarness:
    """Harness: structural contracts that catch regressions."""

    def test_protocol_defines_visibility_methods(self):
        """PermissionEngineProtocol must define both visibility methods."""
        from terrarium.core.protocols import PermissionEngineProtocol
        assert hasattr(PermissionEngineProtocol, "get_visible_entities")
        assert hasattr(PermissionEngineProtocol, "has_visibility_rules")

    def test_permission_engine_implements_protocol(self):
        """PermissionEngine must implement the protocol methods."""
        from terrarium.engines.permission.engine import PermissionEngine
        assert hasattr(PermissionEngine, "get_visible_entities")
        assert hasattr(PermissionEngine, "has_visibility_rules")

    def test_visibility_rule_entity_type_in_config(self):
        """Config must specify the entity type name for visibility rules."""
        from terrarium.engines.permission.config import PermissionConfig
        config = PermissionConfig()
        assert hasattr(config, "visibility_rule_entity_type")
        assert config.visibility_rule_entity_type == "visibility_rule"
```

### 3. `tests/engines/world_compiler/test_visibility_generator.py`

```python
"""Tests for VisibilityRuleGenerator."""

class TestVisibilityRuleGenerator:
    async def test_parse_valid_rules(self):
        """Valid LLM output produces VisibilityRule objects."""
        ...

    async def test_unknown_entity_types_filtered(self):
        """Rules referencing non-existent entity types are dropped."""
        ...

    async def test_wildcard_always_passes(self):
        """target_entity_type="*" is always valid."""
        ...

class TestVisibilityGeneratorHarness:
    def test_prompt_template_has_required_vars(self):
        """VISIBILITY_RULE_GENERATION template must reference all context vars."""
        from terrarium.engines.world_compiler.visibility_generator import VISIBILITY_RULE_GENERATION
        assert "{actor_role}" in VISIBILITY_RULE_GENERATION.user
        assert "{services_summary}" in VISIBILITY_RULE_GENERATION.system
```

---

## Files to Modify (7)

### 4. `terrarium/core/protocols.py` — Add `has_visibility_rules()`

**Insert at line 206** (after `get_visible_entities`):

```python
    async def has_visibility_rules(
        self, actor_id: ActorId, entity_type: str,
    ) -> bool:
        """Check if visibility rules exist for this actor and entity type."""
        ...
```

### 5. `terrarium/engines/permission/engine.py` — Implement visibility

**Replace stub at line 215-217** with full implementation:

```python
async def get_visible_entities(
    self, actor_id: ActorId, entity_type: str,
) -> list[EntityId]:
    """Return entity IDs visible to the given actor.

    Queries visibility_rule entities from State Engine, resolves
    $self references, builds filters, returns matching entity IDs.

    Returns empty list [] when no rules exist — callers interpret
    this as "no filtering, return all entities" (backward compat).
    """
    state_engine = self._dependencies.get("state")
    if state_engine is None:
        return []

    actor = self._get_actor(actor_id)
    if actor is None:
        return []

    rule_entity_type = self._typed_config.visibility_rule_entity_type
    rules = await state_engine.query_entities(
        rule_entity_type, {"actor_role": actor.role}
    )
    if not rules:
        return []

    applicable = [
        r for r in rules
        if r.get("target_entity_type") in (entity_type, "*")
    ]
    if not applicable:
        return []

    visible_ids: list[EntityId] = []
    for rule in applicable:
        filter_field = rule.get("filter_field")
        filter_value = rule.get("filter_value")
        include_unmatched = rule.get("include_unmatched", False)

        if filter_field is None:
            # No filter = see all
            entities = await state_engine.query_entities(entity_type)
            visible_ids.extend(
                EntityId(e.get("id", "")) for e in entities
            )
        else:
            resolved = self._resolve_self_ref(filter_value, actor_id)
            entities = await state_engine.query_entities(
                entity_type, {filter_field: resolved}
            )
            visible_ids.extend(
                EntityId(e.get("id", "")) for e in entities
            )
            if include_unmatched:
                all_ents = await state_engine.query_entities(entity_type)
                for e in all_ents:
                    if not e.get(filter_field):
                        eid = EntityId(e.get("id", ""))
                        if eid not in visible_ids:
                            visible_ids.append(eid)

    return visible_ids

async def has_visibility_rules(
    self, actor_id: ActorId, entity_type: str,
) -> bool:
    """Check if any visibility rules exist for this actor + entity type."""
    state_engine = self._dependencies.get("state")
    if state_engine is None:
        return False
    actor = self._get_actor(actor_id)
    if actor is None:
        return False
    rule_entity_type = self._typed_config.visibility_rule_entity_type
    rules = await state_engine.query_entities(
        rule_entity_type, {"actor_role": actor.role}
    )
    return any(
        r.get("target_entity_type") in (entity_type, "*")
        for r in rules
    )

@staticmethod
def _resolve_self_ref(value: str | None, actor_id: ActorId) -> str:
    """Resolve $self.actor_id in filter values."""
    if value is None:
        return ""
    return value.replace("$self.actor_id", str(actor_id))
```

### 6. `terrarium/engines/permission/config.py` — Add config field

```python
class PermissionConfig(BaseModel):
    cache_ttl_seconds: int = 300
    visibility_rule_entity_type: str = "visibility_rule"  # NEW
```

### 7. `terrarium/engines/responder/engine.py` — Visibility-filtered queries

**Add helper method after `_pluralize()` (after line 195):**

```python
async def _query_with_visibility(
    self,
    state_engine: Any,
    permission_engine: Any,
    actor_id: ActorId,
    entity_type: str,
) -> list[dict[str, Any]]:
    """Query entities filtered by actor visibility.

    If no visibility rules exist → return ALL (backward compat).
    If rules exist → return only visible entities.
    """
    if permission_engine is None:
        return await state_engine.query_entities(entity_type)

    has_rules = await permission_engine.has_visibility_rules(actor_id, entity_type)
    if not has_rules:
        return await state_engine.query_entities(entity_type)

    visible_ids = await permission_engine.get_visible_entities(actor_id, entity_type)
    if not visible_ids:
        return await state_engine.query_entities(entity_type)

    all_entities = await state_engine.query_entities(entity_type)
    visible_set = {str(eid) for eid in visible_ids}
    return [e for e in all_entities if e.get("id", "") in visible_set]
```

**Modify `_build_state_for_pack()` (line 197)** to use visibility:

```python
async def _build_state_for_pack(self, ctx: ActionContext) -> dict:
    state_engine = self._dependencies.get("state")
    if state_engine is None:
        return {}

    permission_engine = self._dependencies.get("permission")  # NEW
    pack = self._pack_registry.get_pack_for_tool(ctx.action)
    entity_types = list(pack.get_entity_schemas().keys())

    result = {}
    for etype in entity_types:
        key = self._pluralize(etype)
        try:
            entities = await self._query_with_visibility(  # CHANGED
                state_engine, permission_engine, ctx.actor_id, etype
            )
            result[key] = entities
        except Exception as exc:
            logger.warning("Failed to query '%s': %s", etype, exc)
            result[key] = []
    return result
```

Apply same change to `_build_state_for_profile()`.

### 8. `terrarium/app.py` — Wire permission into responder + update read_entities

**In `_inject_cross_engine_deps()` (around line 310)** add:

```python
# Responder needs permission engine for visibility filtering
responder = self._registry.get("responder")
permission = self._registry.get("permission")
if responder and permission:
    responder._dependencies["permission"] = permission
```

**Update `read_entities()` at line 482:**

```python
async def read_entities(self, actor_id: str, entity_type: str) -> dict[str, Any]:
    state = self._registry.get("state")
    permission = self._registry.get("permission")

    typed_actor = ActorId(actor_id)
    has_rules = await permission.has_visibility_rules(typed_actor, entity_type)

    if has_rules:
        visible_ids = await permission.get_visible_entities(typed_actor, entity_type)
        if visible_ids:
            all_ents = await state.query_entities(entity_type)
            visible_set = {str(eid) for eid in visible_ids}
            entities = [e for e in all_ents if e.get("id", "") in visible_set]
        else:
            entities = await state.query_entities(entity_type)
    else:
        entities = await state.query_entities(entity_type)

    return {"entity_type": entity_type, "count": len(entities), "entities": entities}
```

### 9. `terrarium/engines/world_compiler/engine.py` — Generate visibility rules

**Insert after subscription generation step** (around line ~420, after Step 9 subscriptions):

```python
        # Step 9b: GENERATE visibility rules per actor role
        visibility_rules: list[dict[str, Any]] = []
        if self._llm_router and actors:
            try:
                from terrarium.engines.world_compiler.visibility_generator import (
                    VisibilityRuleGenerator,
                )
                vis_gen = VisibilityRuleGenerator(
                    llm_router=self._llm_router, seed=plan.seed,
                )
                context_vars = ctx.for_entity_generation()
                seen_roles: set[str] = set()
                for actor in actors:
                    if actor.role in seen_roles:
                        continue
                    seen_roles.add(actor.role)
                    actor_spec = {
                        "role": actor.role,
                        "type": str(actor.type),
                        "permissions": actor.permissions,
                        "visibility": actor.visibility,
                    }
                    try:
                        rules = await vis_gen.generate_for_role(
                            actor_spec, plan, context_vars,
                        )
                        for rule in rules:
                            visibility_rules.append(rule.model_dump())
                    except Exception as exc:
                        logger.warning(
                            "Visibility rules failed for role %s: %s",
                            actor.role, exc,
                        )
            except Exception as exc:
                logger.warning("Visibility rule generation unavailable: %s", exc)

        if visibility_rules:
            all_entities.setdefault("visibility_rule", []).extend(visibility_rules)
```

### 10. `terrarium.toml` — Add visibility config

```toml
[permission]
cache_ttl_seconds = 300
visibility_rule_entity_type = "visibility_rule"
```

---

## What Does NOT Change
- `execute()` pipeline step — service-level permissions untouched
- `AuthorityChecker` — untouched
- Pack entity schemas — no changes
- Existing tests — no rules = no filtering = backward compat
- `ActorDefinition.visibility` field — stays as optional hint passed to LLM

## Verification
1. `uv run pytest tests/engines/permission/test_visibility.py -v` — all pass
2. `uv run pytest tests/engines/world_compiler/test_visibility_generator.py -v` — all pass
3. `uv run pytest tests/ -q --ignore=tests/live` — no regressions
4. Live: compile acme_support world → verify visibility_rule entities in state
5. Live: customer queries tickets → sees only their own
6. Live: supervisor queries tickets → sees all
