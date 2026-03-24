"""Tickets service pack (Tier 1 -- verified).

Provides the canonical tool surface for Zendesk-style ticket services:
create, update, list, show tickets; create and list comments; list and
show users.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.tickets.handlers import (
    handle_zendesk_ticket_comments_create,
    handle_zendesk_ticket_comments_list,
    handle_zendesk_tickets_create,
    handle_zendesk_tickets_list,
    handle_zendesk_tickets_show,
    handle_zendesk_tickets_update,
    handle_zendesk_users_list,
    handle_zendesk_users_show,
)
from terrarium.packs.verified.tickets.schemas import (
    COMMENT_ENTITY_SCHEMA,
    GROUP_ENTITY_SCHEMA,
    TICKET_ENTITY_SCHEMA,
    TICKET_TOOL_DEFINITIONS,
    USER_ENTITY_SCHEMA,
)
from terrarium.packs.verified.tickets.state_machines import TICKET_TRANSITIONS


class TicketsPack(ServicePack):
    """Verified pack for Zendesk-style ticket / work-management services.

    Tools: zendesk_tickets_list, zendesk_tickets_show, zendesk_tickets_create,
    zendesk_tickets_update, zendesk_ticket_comments_list,
    zendesk_ticket_comments_create, zendesk_users_list, zendesk_users_show.
    """

    pack_name: ClassVar[str] = "tickets"
    category: ClassVar[str] = "work_management"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "zendesk_tickets_list": handle_zendesk_tickets_list,
        "zendesk_tickets_show": handle_zendesk_tickets_show,
        "zendesk_tickets_create": handle_zendesk_tickets_create,
        "zendesk_tickets_update": handle_zendesk_tickets_update,
        "zendesk_ticket_comments_list": handle_zendesk_ticket_comments_list,
        "zendesk_ticket_comments_create": handle_zendesk_ticket_comments_create,
        "zendesk_users_list": handle_zendesk_users_list,
        "zendesk_users_show": handle_zendesk_users_show,
    }

    def get_tools(self) -> list[dict]:
        """Return the ticket tool manifest."""
        return list(TICKET_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (ticket, comment, user, group)."""
        return {
            "ticket": TICKET_ENTITY_SCHEMA,
            "comment": COMMENT_ENTITY_SCHEMA,
            "user": USER_ENTITY_SCHEMA,
            "group": GROUP_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for ticket entities."""
        return {"ticket": {"transitions": TICKET_TRANSITIONS}}

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate ticket action handler."""
        return await self.dispatch_action(action, input_data, state)
