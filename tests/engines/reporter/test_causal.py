"""Tests for CausalTraceRenderer -- causal chain formatting."""

from unittest.mock import AsyncMock

import pytest

from tests.engines.reporter.conftest import make_world_event
from volnix.core.types import EventId
from volnix.engines.reporter.causal_trace import CausalTraceRenderer


@pytest.fixture
def renderer() -> CausalTraceRenderer:
    return CausalTraceRenderer()


def _mock_state(causes=None, effects=None):
    """Create a mock state engine that returns given cause/effect chains."""
    state = AsyncMock()

    async def get_chain(event_id, direction="backward"):
        if direction == "backward":
            return causes or []
        return effects or []

    state.get_causal_chain = AsyncMock(side_effect=get_chain)
    return state


@pytest.mark.asyncio
async def test_single_event_empty_chain(renderer):
    """Single event with no causes/effects → empty chains."""
    state = _mock_state(causes=[], effects=[])
    result = await renderer.render(EventId("evt-1"), state)

    assert result["root_event"] == "evt-1"
    assert result["causes"] == []
    assert result["effects"] == []
    assert result["chain_length"] == 0


@pytest.mark.asyncio
async def test_linked_events_chain_returned(renderer):
    """Events with causal links → chain is returned."""
    cause_event = make_world_event(actor_id="agent-1", action="read_ticket", tick=1)
    effect_event = make_world_event(actor_id="agent-1", action="update_ticket", tick=2)

    state = _mock_state(causes=[cause_event], effects=[effect_event])
    result = await renderer.render(EventId("evt-root"), state)

    assert len(result["causes"]) == 1
    assert len(result["effects"]) == 1
    assert result["chain_length"] == 2


@pytest.mark.asyncio
async def test_format_matches_spec(renderer):
    """Formatted events should have the expected fields."""
    event = make_world_event(
        actor_id="agent-1",
        action="email_send",
        tick=5,
        target_entity="e-100",
    )
    state = _mock_state(causes=[event], effects=[])
    result = await renderer.render(EventId("evt-root"), state)

    formatted = result["causes"][0]
    assert "event_id" in formatted
    assert formatted["event_type"] == "world.email_send"
    assert formatted["tick"] == 5
    assert formatted["actor_id"] == "agent-1"
    assert formatted["action"] == "email_send"
    assert formatted["target_entity"] == "e-100"


@pytest.mark.asyncio
async def test_multiple_causes(renderer):
    """Multiple cause events should all be formatted."""
    events = [
        make_world_event(actor_id="agent-1", action="step1", tick=1),
        make_world_event(actor_id="agent-2", action="step2", tick=2),
        make_world_event(actor_id="agent-1", action="step3", tick=3),
    ]
    state = _mock_state(causes=events, effects=[])
    result = await renderer.render(EventId("evt-root"), state)

    assert len(result["causes"]) == 3
    assert result["chain_length"] == 3
