"""Email service pack (Tier 1 -- verified).

Provides the canonical tool surface for email-category services:
send, list, read, search, reply, and mark-read operations.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.email.handlers import (
    handle_email_list,
    handle_email_mark_read,
    handle_email_read,
    handle_email_reply,
    handle_email_search,
    handle_email_send,
)
from terrarium.packs.verified.email.schemas import (
    EMAIL_ENTITY_SCHEMA,
    EMAIL_TOOL_DEFINITIONS,
    MAILBOX_ENTITY_SCHEMA,
    THREAD_ENTITY_SCHEMA,
)
from terrarium.packs.verified.email.state_machines import EMAIL_TRANSITIONS


class EmailPack(ServicePack):
    """Verified pack for email communication services.

    Tools: email_send, email_list, email_read, email_search,
    email_reply, email_mark_read.
    """

    pack_name: ClassVar[str] = "email"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "email_send": handle_email_send,
        "email_list": handle_email_list,
        "email_read": handle_email_read,
        "email_search": handle_email_search,
        "email_reply": handle_email_reply,
        "email_mark_read": handle_email_mark_read,
    }

    def get_tools(self) -> list[dict]:
        """Return the email tool manifest."""
        return list(EMAIL_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (email, mailbox, thread)."""
        return {
            "email": EMAIL_ENTITY_SCHEMA,
            "mailbox": MAILBOX_ENTITY_SCHEMA,
            "thread": THREAD_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for email entities."""
        return {"email": {"transitions": EMAIL_TRANSITIONS}}

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate email action handler."""
        return await self.dispatch_action(action, input_data, state)
