"""Tickets service pack (Tier 1 -- verified).

Provides the canonical tool surface for Zendesk-style ticket services:
create, update, list, show, delete, search tickets; create and list comments;
list and show users; list and show groups.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.zendesk.handlers import (
    handle_groups_list,
    handle_groups_show,
    handle_ticket_comments_create,
    handle_ticket_comments_list,
    handle_tickets_create,
    handle_tickets_delete,
    handle_tickets_list,
    handle_tickets_search,
    handle_tickets_show,
    handle_tickets_update,
    handle_users_list,
    handle_users_show,
)
from terrarium.packs.verified.zendesk.schemas import (
    COMMENT_ENTITY_SCHEMA,
    GROUP_ENTITY_SCHEMA,
    ORGANIZATION_ENTITY_SCHEMA,
    TICKET_ENTITY_SCHEMA,
    TICKET_TOOL_DEFINITIONS,
    USER_ENTITY_SCHEMA,
)
from terrarium.packs.verified.zendesk.state_machines import TICKET_TRANSITIONS


class TicketsPack(ServicePack):
    """Verified pack for Zendesk-style ticket / work-management services.

    Tools: tickets.list, tickets.read, tickets.create,
    tickets.update, tickets.delete, tickets.search,
    tickets.comments.list, tickets.comment_create,
    customers.list, customers.read, groups.list,
    groups.read.
    """

    pack_name: ClassVar[str] = "zendesk"
    category: ClassVar[str] = "work_management"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "tickets.list": handle_tickets_list,
        "tickets.read": handle_tickets_show,
        "tickets.create": handle_tickets_create,
        "tickets.update": handle_tickets_update,
        "tickets.delete": handle_tickets_delete,
        "tickets.search": handle_tickets_search,
        "tickets.comments.list": handle_ticket_comments_list,
        "tickets.comment_create": handle_ticket_comments_create,
        "customers.list": handle_users_list,
        "customers.read": handle_users_show,
        "groups.list": handle_groups_list,
        "groups.read": handle_groups_show,
    }

    def get_tools(self) -> list[dict]:
        """Return the ticket tool manifest."""
        return list(TICKET_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (ticket, comment, user, group, organization)."""
        return {
            "ticket": TICKET_ENTITY_SCHEMA,
            "comment": COMMENT_ENTITY_SCHEMA,
            "user": USER_ENTITY_SCHEMA,
            "group": GROUP_ENTITY_SCHEMA,
            "organization": ORGANIZATION_ENTITY_SCHEMA,
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
