"""Tickets service pack (Tier 1 -- verified).

Provides the canonical tool surface for work-management ticket services:
create, update, assign, escalate, close, and list operations.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ServicePack


class TicketPack(ServicePack):
    """Verified pack for ticket / work-management services.

    Tools: ticket_create, ticket_update, ticket_assign, ticket_escalate,
    ticket_close, ticket_list.
    """

    pack_name: ClassVar[str] = "tickets"
    category: ClassVar[str] = "work_management"
    fidelity_tier: ClassVar[int] = 1

    def get_tools(self) -> list[dict]:
        """Return the ticket tool manifest."""
        ...

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (ticket, comment, assignment)."""
        ...

    def get_state_machines(self) -> dict:
        """Return state machines for ticket entities."""
        ...

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate ticket action handler."""
        ...
