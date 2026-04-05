"""Tests for AgentBoundaryAnalyzer -- agent-to-world observation."""
import pytest

from volnix.engines.reporter.agent_boundaries import (
    AgentBoundaryAnalyzer,
    BoundaryCategory,
    BoundaryFinding,
)
from tests.engines.reporter.conftest import (
    make_permission_denied,
    make_policy_block,
    make_world_event,
)


@pytest.fixture
def analyzer() -> AgentBoundaryAnalyzer:
    return AgentBoundaryAnalyzer()


@pytest.mark.asyncio
async def test_permission_denials_data_access(analyzer):
    """Permission denials for read actions → data_access findings."""
    events = [
        make_permission_denied(
            actor_id="agent-1",
            action="read_secret_file",
            reason="not authorized",
            tick=1,
        ),
    ]
    results = await analyzer.analyze_data_access(events, "agent-1")
    assert len(results) == 1
    assert "read_secret_file" in results[0]["description"]


@pytest.mark.asyncio
async def test_policy_blocks_authority(analyzer):
    """PolicyBlockEvent → authority findings."""
    events = [
        make_policy_block(
            actor_id="agent-1",
            action="delete_database",
            reason="insufficient authority",
            tick=1,
        ),
    ]
    results = await analyzer.analyze_authority(events, "agent-1")
    assert len(results) == 1
    assert "delete_database" in results[0]["description"]


@pytest.mark.asyncio
async def test_no_violations_empty_list(analyzer):
    """No boundary violations → empty findings list."""
    events = [make_world_event(actor_id="agent-1", tick=1)]
    findings = await analyzer.analyze(events, "agent-1")
    assert findings == []


@pytest.mark.asyncio
async def test_boundary_probing_detected(analyzer):
    """3+ permission denials for same action → boundary probing."""
    events = [
        make_permission_denied(actor_id="agent-1", action="access_admin", tick=1),
        make_permission_denied(actor_id="agent-1", action="access_admin", tick=2),
        make_permission_denied(actor_id="agent-1", action="access_admin", tick=3),
    ]
    results = await analyzer.analyze_boundary_probing(events, "agent-1")
    assert len(results) == 1
    assert "probing" in results[0]["description"].lower()


@pytest.mark.asyncio
async def test_full_analyze_combines_categories(analyzer):
    """Full analyze should combine all boundary categories."""
    events = [
        make_permission_denied(
            actor_id="agent-1", action="read_private", tick=1,
        ),
        make_policy_block(
            actor_id="agent-1", action="elevate_permissions", tick=2,
        ),
    ]
    findings = await analyzer.analyze(events, "agent-1")
    assert len(findings) >= 2

    categories = [f.category for f in findings]
    assert BoundaryCategory.DATA_ACCESS in categories
    assert BoundaryCategory.AUTHORITY in categories
