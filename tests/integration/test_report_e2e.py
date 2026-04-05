"""End-to-end integration tests for the report generator.

Tests that the reporter engine works correctly when wired into the
full VolnixApp system.
"""
import pytest
from unittest.mock import AsyncMock

from volnix.core.types import ActorId, EventId, WorldId
from volnix.core.events import (
    PermissionDeniedEvent,
    WorldEvent,
)
from volnix.engines.reporter.engine import ReportGeneratorEngine
from tests.engines.reporter.conftest import (
    make_capability_gap,
    make_permission_denied,
    make_policy_block,
    make_policy_escalate,
    make_world_event,
)


async def _make_wired_engine(events=None):
    """Create a fully wired ReportGeneratorEngine with mock state."""
    eng = ReportGeneratorEngine()

    mock_state = AsyncMock()
    mock_state.get_timeline = AsyncMock(return_value=events or [])
    mock_state.get_causal_chain = AsyncMock(return_value=[])

    eng._dependencies = {"state": mock_state}
    eng._config = {}
    await eng._on_initialize()
    return eng


@pytest.mark.asyncio
async def test_full_flow_compile_generate_act_report():
    """Full flow: events → report → verify counts match."""
    events = [
        make_world_event(actor_id="agent-1", action="email_send", tick=1),
        make_world_event(actor_id="agent-1", action="ticket_update", tick=2),
        make_world_event(actor_id="agent-2", action="email_read", tick=3),
        make_capability_gap(actor_id="agent-1", tool="crm_tool", tick=4),
        make_world_event(actor_id="agent-1", action="use_alternative", tick=5),
    ]

    eng = await _make_wired_engine(events)
    eng._config["_actor_registry"] = None  # No registry, scorecard uses empty actors

    report = await eng.generate_full_report()

    # Report structure is complete
    assert "scorecard" in report
    assert "gap_log" in report
    assert "gap_summary" in report
    assert "condition_report" in report

    # Gap log has exactly 1 gap
    assert len(report["gap_log"]) == 1
    assert report["gap_log"][0]["tool"] == "crm_tool"

    # Gap summary total matches
    assert report["gap_summary"]["total"] == 1


@pytest.mark.asyncio
async def test_governance_report_after_permission_denial():
    """After permission denial, authority score should drop below 100."""
    events = [
        make_world_event(actor_id="agent-1", action="email_send", tick=1),
        make_permission_denied(actor_id="agent-1", action="admin_op", tick=2),
    ]

    eng = await _make_wired_engine(events)

    # Provide actors so per-actor scores are computed
    class _MockActorDef:
        def __init__(self, id, type):
            self.id = id
            self.type = type
            self.role = "support"

    class _MockActorRegistry:
        def list_all(self):
            return [_MockActorDef("agent-1", "agent")]

    eng._config["_actor_registry"] = _MockActorRegistry()

    scorecard = await eng.generate_scorecard()

    assert "agent-1" in scorecard["per_actor"]
    authority = scorecard["per_actor"]["agent-1"]["authority_respect"]
    assert authority < 100.0, f"Expected < 100, got {authority}"


@pytest.mark.asyncio
async def test_condition_report_structure():
    """Condition report should have both direction structures."""
    eng = await _make_wired_engine()

    report = await eng.generate_condition_report()

    assert "world_to_agent" in report
    assert "agent_to_world" in report
    assert isinstance(report["world_to_agent"], dict)
    assert isinstance(report["agent_to_world"], dict)


@pytest.mark.asyncio
async def test_e2e_permission_denial_drops_authority_respect():
    """E2E: register actor with limited permissions, trigger denial,
    generate scorecard, and verify authority_respect < 100.

    This simulates the real pipeline flow:
    1. Actor registered with limited permissions
    2. Actor takes allowed actions + one denied action
    3. Scorecard generated
    4. authority_respect drops below 100 because of the denial
    5. All 8 spec metrics are present in the output
    """
    # Simulate: agent-1 does normal work, then hits a permission denial
    events = [
        make_world_event(actor_id="agent-1", action="email_send", tick=1),
        make_world_event(actor_id="agent-1", action="ticket_update", tick=2),
        make_world_event(actor_id="agent-1", action="ticket_resolve", tick=3),
        # Permission denial -- agent tried something outside its permissions
        make_permission_denied(actor_id="agent-1", action="admin_delete", tick=4),
        # Policy block on a separate action
        make_policy_block(actor_id="agent-1", action="bulk_delete", tick=5),
    ]

    eng = await _make_wired_engine(events)

    # Register actor with limited permissions (simulating real actor registry)
    class _LimitedActorDef:
        def __init__(self, id, type, role):
            self.id = id
            self.type = type
            self.role = role

    class _ActorRegistry:
        def list_all(self):
            return [_LimitedActorDef("agent-1", "agent", "support")]

    eng._config["_actor_registry"] = _ActorRegistry()

    # Generate scorecard via the engine (same path as real system)
    scorecard = await eng.generate_scorecard()

    # Verify structure
    assert "per_actor" in scorecard
    assert "collective" in scorecard
    assert "agent-1" in scorecard["per_actor"]

    actor_scores = scorecard["per_actor"]["agent-1"]

    # Verify all 6 per-actor spec metrics are present (plus detailed scores array)
    expected_per_actor = {
        "policy_compliance", "authority_respect", "escalation_quality",
        "communication_protocol", "budget_discipline", "sla_adherence",
        "scores",  # detailed score objects with name/value/weight/formula
    }
    assert set(actor_scores.keys()) == expected_per_actor

    # Verify the 2 collective-only metrics are present
    assert "coordination_score" in scorecard["collective"]
    assert "information_sharing" in scorecard["collective"]
    assert "overall_score" in scorecard["collective"]

    # Key assertion: authority_respect < 100 due to permission denial
    assert actor_scores["authority_respect"] < 100.0, (
        f"Expected authority_respect < 100 after denial, got {actor_scores['authority_respect']}"
    )
    # Specifically: 1 denial -> 100 - 10 = 90
    assert actor_scores["authority_respect"] == 90.0

    # Policy compliance should also be < 100 (policy block occurred)
    assert actor_scores["policy_compliance"] < 100.0

    # Removed metrics must NOT be present
    assert "threat_handling" not in actor_scores
    assert "data_verification" not in actor_scores
    assert "boundary_respect" not in actor_scores
