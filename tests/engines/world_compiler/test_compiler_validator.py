"""Tests for compiler-time world validation."""

from __future__ import annotations

import pytest

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.personality import Personality
from terrarium.core.types import ActorId, ActorType
from terrarium.engines.world_compiler.plan import ServiceResolution, WorldPlan
from terrarium.engines.world_compiler.validator import CompilerWorldValidator
from terrarium.kernel.surface import ServiceSurface
from terrarium.reality.dimensions import WorldConditions
from terrarium.reality.seeds import EntitySelector, SeedInvariant


def _make_plan() -> WorldPlan:
    surface = ServiceSurface(
        service_name="support",
        category="work_management",
        source="tier1_pack",
        fidelity_tier=1,
        entity_schemas={
            "customer": {
                "type": "object",
                "x-terrarium-identity": "customer_id",
                "required": ["customer_id"],
                "properties": {
                    "customer_id": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
            "ticket": {
                "type": "object",
                "x-terrarium-identity": "ticket_id",
                "required": ["ticket_id", "customer_id", "status"],
                "properties": {
                    "ticket_id": {"type": "string"},
                    "customer_id": {"type": "string", "x-terrarium-ref": "customer"},
                    "status": {"type": "string"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
                "x-terrarium-ordering": [
                    {"before": "created_at", "after": "updated_at", "context": "ticket lifecycle"},
                ],
            },
        },
        state_machines={
            "ticket": {"transitions": {"open": ["closed"], "closed": []}},
        },
    )
    return WorldPlan(
        name="Support World",
        description="test world",
        services={
            "support": ServiceResolution(
                service_name="support",
                spec_reference="verified/support",
                surface=surface,
                resolution_source="tier1_pack",
            )
        },
        actor_specs=[{"role": "support-agent", "type": "external", "count": 2}],
        conditions=WorldConditions(),
        reality_prompt_context={},
    )


def _make_actor(role: str) -> ActorDefinition:
    return ActorDefinition(
        id=ActorId(f"{role}-1"),
        type=ActorType.HUMAN,
        role=role,
        personality=Personality(style="balanced", response_time="5m"),
    )


def test_validate_entity_section_checks_schema_count_and_state_machine():
    validator = CompilerWorldValidator()
    plan = _make_plan()
    schemas = validator.normalize_plan_schemas(plan)
    state_machines = validator.collect_state_machines(plan)
    result = validator.validate_entity_section(
        "ticket",
        [{"ticket_id": "t1", "customer_id": "c1", "status": "invalid"}],
        schemas["ticket"],
        state_machine=state_machines["ticket"],
        expected_count=2,
    )

    assert result.valid is False
    assert any("Expected 2 entities" in error for error in result.errors)
    assert any("invalid status" in error for error in result.errors)


@pytest.mark.asyncio
async def test_validate_world_checks_cross_entity_references():
    validator = CompilerWorldValidator()
    plan = _make_plan()
    result = await validator.validate_world(
        plan,
        {
            "customer": [{"customer_id": "c1", "name": "Alice"}],
            "ticket": [{"ticket_id": "t1", "customer_id": "missing", "status": "open"}],
        },
        actors=[_make_actor("support-agent"), _make_actor("support-agent")],
    )

    assert result.valid is False
    assert "ticket" in result.sections
    assert any("references missing customer" in error for error in result.sections["ticket"].errors)


@pytest.mark.asyncio
async def test_validate_world_checks_actor_counts():
    validator = CompilerWorldValidator()
    plan = _make_plan()
    result = await validator.validate_world(
        plan,
        {
            "customer": [{"customer_id": "c1"}],
            "ticket": [{"ticket_id": "t1", "customer_id": "c1", "status": "open"}],
        },
        actors=[_make_actor("support-agent")],
    )

    assert result.valid is False
    assert "actor_role:support-agent" in result.sections


def test_validate_seed_invariants_and_aggregation():
    validator = CompilerWorldValidator()
    plan = _make_plan()
    schemas = validator.normalize_plan_schemas(plan)
    result = validator.validate_seed_invariants(
        "seed:0",
        [
            SeedInvariant(
                kind="exists",
                selector=EntitySelector(entity_type="customer", match={"customer_id": "c1"}),
            ),
            SeedInvariant(
                kind="references",
                selector=EntitySelector(entity_type="ticket", match={"ticket_id": "t1"}),
                field="customer_id",
                target_selector=EntitySelector(
                    entity_type="customer",
                    match={"customer_id": "c1"},
                ),
            ),
        ],
        {
            "customer": [{"customer_id": "c1"}],
            "ticket": [{"ticket_id": "t1", "customer_id": "c1", "status": "open"}],
        },
        schemas,
    )

    assert result.valid is True
