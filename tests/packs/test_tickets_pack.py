"""Tests for terrarium.packs.verified.tickets -- ticket lifecycle and SLA tracking.

Full test suite lives in tests/packs/verified/test_tickets.py.
This module verifies backward-compatible import and basic smoke checks.
"""

import pytest

from terrarium.packs.verified.tickets.pack import TicketsPack
from terrarium.packs.verified.tickets.state_machines import TICKET_STATES


def test_ticket_pack_tools():
    pack = TicketsPack()
    tools = pack.get_tools()
    assert len(tools) == 12


def test_ticket_lifecycle_states():
    assert "new" in TICKET_STATES
    assert "closed" in TICKET_STATES
    assert len(TICKET_STATES) == 6


def test_ticket_valid_transitions():
    from terrarium.packs.verified.tickets.state_machines import TICKET_TRANSITIONS

    assert "open" in TICKET_TRANSITIONS["new"]
    assert "solved" in TICKET_TRANSITIONS["open"]


def test_ticket_invalid_transitions():
    from terrarium.packs.verified.tickets.state_machines import TICKET_TRANSITIONS

    # closed has no valid transitions
    assert TICKET_TRANSITIONS["closed"] == []


@pytest.mark.asyncio
async def test_ticket_sla_tracking():
    """Smoke test: creating a ticket returns a valid proposal."""
    from terrarium.core.types import ToolName

    pack = TicketsPack()
    proposal = await pack.handle_action(
        ToolName("zendesk_tickets_create"),
        {
            "subject": "SLA test",
            "description": "Testing SLA",
            "requester_id": "user-1",
        },
        {},
    )
    assert proposal.response_body["ticket"]["status"] == "new"
