"""Email service pack (Tier 1 -- verified).

Provides the canonical tool surface for email-category services:
send, list, read, search, reply, and mark-read operations.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ServicePack


class EmailPack(ServicePack):
    """Verified pack for email communication services.

    Tools: email_send, email_list, email_read, email_search,
    email_reply, email_mark_read.
    """

    pack_name: ClassVar[str] = "email"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 1

    def get_tools(self) -> list[dict]:
        """Return the email tool manifest."""
        ...

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (email, mailbox, thread)."""
        ...

    def get_state_machines(self) -> dict:
        """Return state machines for email entities."""
        ...

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate email action handler."""
        ...
