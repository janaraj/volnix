"""Integration: governed vs ungoverned comparison workflow.

Tests the full F4-F5 workflow:
1. Create a run (governed) → compile world → save artifacts
2. Create a run (ungoverned) → compile world → save artifacts
3. Diff the two runs → governance comparison table
"""

from __future__ import annotations

import pytest

from volnix.engines.world_compiler.plan import ServiceResolution, WorldPlan
from volnix.kernel.surface import ServiceSurface
from volnix.packs.verified.gmail.pack import EmailPack
from volnix.reality.presets import load_preset
from volnix.runs.comparison import RunComparator


def _make_email_plan(mode: str = "governed") -> WorldPlan:
    """Build a minimal WorldPlan with email pack for testing."""
    surface = ServiceSurface.from_pack(EmailPack())
    return WorldPlan(
        name="Integration Test World",
        description="Email support system for integration testing",
        seed=42,
        services={
            "gmail": ServiceResolution(
                service_name="gmail",
                spec_reference="verified/gmail",
                surface=surface,
                resolution_source="tier1_pack",
            ),
        },
        actor_specs=[
            {"role": "support-agent", "type": "external", "count": 1},
        ],
        conditions=load_preset("messy"),
        reality_prompt_context={},
        mode=mode,
    )


@pytest.mark.asyncio
async def test_governed_run_saves_artifacts(app_with_mock_llm):
    """A governed run saves report, scorecard, and event_log artifacts."""
    app = app_with_mock_llm
    plan = _make_email_plan(mode="governed")

    # Create and start a run
    run_id = await app.run_manager.create_run(
        world_def={"name": "test"},
        config_snapshot={"seed": 42, "behavior": "dynamic", "mode": "governed"},
        mode="governed",
        tag="gov",
    )

    # Compile the world
    compiler = app.registry.get("world_compiler")
    await compiler.generate_world(plan)

    # Start + complete run (with artifacts)
    await app.run_manager.start_run(run_id)
    result = await app.end_run(run_id)

    assert result["run_id"] == str(run_id)
    assert "report" in result
    assert "scorecard" in result

    # Verify artifacts are on disk
    artifacts = await app.artifact_store.list_artifacts(run_id)
    artifact_types = [a["type"] for a in artifacts]
    assert "report" in artifact_types
    assert "scorecard" in artifact_types
    assert "event_log" in artifact_types


@pytest.mark.asyncio
async def test_ungoverned_run_saves_artifacts(app_with_mock_llm):
    """An ungoverned run saves artifacts the same way."""
    app = app_with_mock_llm
    plan = _make_email_plan(mode="ungoverned")

    run_id = await app.run_manager.create_run(
        world_def={"name": "test"},
        config_snapshot={"seed": 42, "behavior": "dynamic", "mode": "ungoverned"},
        mode="ungoverned",
        tag="ungov",
    )

    compiler = app.registry.get("world_compiler")
    await compiler.generate_world(plan)

    await app.run_manager.start_run(run_id)
    result = await app.end_run(run_id)

    assert result["run_id"] == str(run_id)

    artifacts = await app.artifact_store.list_artifacts(run_id)
    artifact_types = [a["type"] for a in artifacts]
    assert "report" in artifact_types
    assert "scorecard" in artifact_types


@pytest.mark.asyncio
async def test_diff_governed_ungoverned_produces_comparison(app_with_mock_llm):
    """Diffing two runs produces a governance comparison with the expected structure.

    Seeds artifacts directly to test the comparison pipeline without
    requiring two separate world compilations (which conflicts with
    the stateful mock LLM counters).
    """
    app = app_with_mock_llm
    store = app.artifact_store

    # Create governed run with seeded artifacts
    gov_id = await app.run_manager.create_run(
        world_def={"name": "test"},
        config_snapshot={"seed": 42, "mode": "governed"},
        mode="governed",
        tag="gov-diff",
    )
    await app.run_manager.start_run(gov_id)
    await store.save_scorecard(
        gov_id,
        {
            "per_actor": {"agent-1": {"policy_compliance": 95.0}},
            "collective": {"overall_score": 94.0, "policy_compliance": 95.0},
        },
    )
    await store.save_event_log(
        gov_id,
        [
            {"event_type": "world.email_send", "actor_id": "agent-1"},
            {"event_type": "policy_block", "actor_id": "agent-1"},
            {"event_type": "policy_hold", "actor_id": "agent-1"},
        ],
    )
    await store.save_report(gov_id, {"entities": {"email": [{"id": "1"}]}})
    await app.run_manager.complete_run(gov_id)

    # Create ungoverned run with seeded artifacts
    ungov_id = await app.run_manager.create_run(
        world_def={"name": "test"},
        config_snapshot={"seed": 42, "mode": "ungoverned"},
        mode="ungoverned",
        tag="ungov-diff",
    )
    await app.run_manager.start_run(ungov_id)
    await store.save_scorecard(
        ungov_id,
        {
            "per_actor": {"agent-1": {"policy_compliance": 70.0}},
            "collective": {"overall_score": 78.0, "policy_compliance": 70.0},
        },
    )
    await store.save_event_log(
        ungov_id,
        [
            {"event_type": "world.email_send", "actor_id": "agent-1"},
            {"event_type": "world.email_send", "actor_id": "agent-1"},
            {"event_type": "permission_denied", "actor_id": "agent-1"},
            {"event_type": "budget_exhausted", "actor_id": "agent-1"},
        ],
    )
    await store.save_report(ungov_id, {"entities": {"email": [{"id": "1"}, {"id": "2"}]}})
    await app.run_manager.complete_run(ungov_id)

    # Diff
    comparator = RunComparator(store)
    result = await comparator.compare_governed_ungoverned(gov_id, ungov_id)

    # Verify structure
    assert "governance_metrics" in result
    gm = result["governance_metrics"]
    assert "blocked_actions" in gm
    assert "approval_requests" in gm
    assert "budget_exceeded" in gm
    assert "unauthorized_access" in gm
    assert "total_actions" in gm
    assert "policy_hits" in gm

    # Verify governed had blocks, ungoverned didn't
    assert gm["blocked_actions"][str(gov_id)] == 1
    assert gm["blocked_actions"][str(ungov_id)] == 0
    assert gm["unauthorized_access"][str(ungov_id)] == 1
    assert gm["budget_exceeded"][str(ungov_id)] == 1

    # Verify it can be formatted
    table = comparator.format_comparison(result)
    assert isinstance(table, str)
    assert "Run Comparison" in table
