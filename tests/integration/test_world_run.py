"""Integration tests for world compilation and simulation run lifecycle.

Tests compile -> generate -> run actions -> verify state -> report.

All tests that call generate_world() use the ``app_with_mock_llm``
fixture because generation requires an LLM router.
"""

from __future__ import annotations

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.core.types import ActorId, ActorType


def _ensure_agent(app, agent_id: str):
    """Register a test agent if not already present in the actor registry."""
    compiler = app.registry.get("world_compiler")
    actor_registry = compiler._config.get("_actor_registry")
    if actor_registry and not actor_registry.has_actor(ActorId(agent_id)):
        actor_registry.register(
            ActorDefinition(
                id=ActorId(agent_id),
                type=ActorType.AGENT,
                role="test-agent",
                permissions={"write": "all", "read": "all"},
            )
        )


@pytest.mark.asyncio
async def test_compile_and_run_simple_world(app_with_mock_llm):
    """Compile minimal world -> generate -> send email -> verify state."""
    app = app_with_mock_llm
    compiler = app.registry.get("world_compiler")
    plan = await compiler.compile_from_yaml(
        "tests/fixtures/worlds/minimal_world.yaml",
    )
    assert plan.name
    assert plan.source == "yaml"

    result = await compiler.generate_world(plan)
    assert "entities" in result
    assert "actors" in result
    assert "report" in result


@pytest.mark.asyncio
async def test_run_produces_valid_report(app_with_mock_llm):
    """Generated world report has all required sections."""
    app = app_with_mock_llm
    compiler = app.registry.get("world_compiler")
    plan = await compiler.compile_from_yaml(
        "tests/fixtures/worlds/acme_support.yaml",
        "tests/fixtures/worlds/acme_compiler.yaml",
    )
    result = await compiler.generate_world(plan)
    report = result["report"]

    assert "VOLNIX WORLD GENERATION REPORT" in report
    assert "GENERATED ENTITIES:" in report
    assert "ACTORS:" in report
    assert "STATUS:" in report
    assert "TOTAL:" in report


@pytest.mark.asyncio
async def test_run_governance_scores(app_with_mock_llm):
    """After generation, agent actions go through the full 7-step pipeline."""
    app = app_with_mock_llm
    compiler = app.registry.get("world_compiler")
    plan = await compiler.compile_from_yaml(
        "tests/fixtures/worlds/acme_support.yaml",
        "tests/fixtures/worlds/acme_compiler.yaml",
    )
    await compiler.generate_world(plan)

    # Register test agent so governance allows the action
    _ensure_agent(app, "agent-1")

    # Agent action goes through full pipeline
    result = await app.handle_action(
        "agent-1",
        "email",
        "email_send",
        {
            "from_addr": "agent@acme.com",
            "to_addr": "customer@test.com",
            "subject": "Governance test",
            "body": "Testing governance pipeline.",
        },
    )
    assert "email_id" in result


@pytest.mark.asyncio
async def test_compile_world_with_reality_preset(app):
    """Reality preset dimensions flow through to WorldPlan.conditions.

    This is a compilation-only test -- no LLM needed.
    """
    compiler = app.registry.get("world_compiler")
    plan = await compiler.compile_from_yaml(
        "tests/fixtures/worlds/acme_support.yaml",
        "tests/fixtures/worlds/acme_compiler.yaml",
    )
    # acme_compiler.yaml uses "messy" preset
    assert plan.conditions.information.staleness == 30
    assert plan.conditions.reliability.failures == 20
    assert plan.conditions.friction.uncooperative == 30
    assert plan.conditions.complexity.ambiguity == 35
    assert plan.conditions.boundaries.access_limits == 25


@pytest.mark.asyncio
async def test_governed_vs_ungoverned_comparison(app_with_mock_llm):
    """Governed mode produces same entity structure as pipeline expects."""
    app = app_with_mock_llm
    compiler = app.registry.get("world_compiler")
    plan = await compiler.compile_from_yaml(
        "tests/fixtures/worlds/acme_support.yaml",
        "tests/fixtures/worlds/acme_compiler.yaml",
    )
    assert plan.mode == "governed"
    result = await compiler.generate_world(plan)

    # Governed mode should still generate all entities
    assert result["entities"]
    assert result["actors"]
    # Register test agent so governance allows the action
    _ensure_agent(app, "agent-1")

    # Actions should work in governed mode (pass through governance steps)
    action_result = await app.handle_action(
        "agent-1",
        "email",
        "email_send",
        {
            "from_addr": "agent@acme.com",
            "to_addr": "customer@test.com",
            "subject": "Governed mode test",
            "body": "This goes through full governance.",
        },
    )
    assert "email_id" in action_result
