"""Tests for reporter agent boundary analysis."""

import pytest

from tests.engines.reporter.conftest import (
    make_permission_denied,
    make_policy_block,
    make_world_event,
)
from volnix.engines.reporter.agent_boundaries import (
    AgentBoundaryAnalyzer,
)


@pytest.fixture
def analyzer() -> AgentBoundaryAnalyzer:
    return AgentBoundaryAnalyzer()


@pytest.mark.asyncio
async def test_analyze_data_access(analyzer):
    """Test analyzing agent data access patterns for boundary violations."""
    events = [
        make_permission_denied(
            actor_id="agent-1",
            action="get_private_data",
            tick=1,
        ),
    ]
    results = await analyzer.analyze_data_access(events, "agent-1")
    assert len(results) == 1
    assert "get_private_data" in results[0]["description"]


@pytest.mark.asyncio
async def test_analyze_information_handling(analyzer):
    """Test analyzing how the agent handles sensitive information."""
    events = [
        make_world_event(
            actor_id="agent-1",
            action="forward_sensitive_data",
            tick=1,
        ),
    ]
    results = await analyzer.analyze_information_handling(events, "agent-1")
    assert len(results) == 1
    assert "forward" in results[0]["description"].lower()


@pytest.mark.asyncio
async def test_analyze_authority_respect(analyzer):
    """Test analyzing whether the agent respects authority boundaries."""
    events = [
        make_policy_block(
            actor_id="agent-1",
            action="override_policy",
            tick=1,
        ),
    ]
    results = await analyzer.analyze_authority(events, "agent-1")
    assert len(results) == 1
    assert "override_policy" in results[0]["description"]


@pytest.mark.asyncio
async def test_analyze_boundary_probing(analyzer):
    """Test detecting agent attempts to probe system boundaries."""
    events = [
        make_permission_denied(actor_id="agent-1", action="admin_access", tick=1),
        make_permission_denied(actor_id="agent-1", action="admin_access", tick=2),
        make_permission_denied(actor_id="agent-1", action="admin_access", tick=3),
    ]
    results = await analyzer.analyze_boundary_probing(events, "agent-1")
    assert len(results) == 1
    assert "probing" in results[0]["description"].lower()
    assert results[0]["severity"] == "high"
