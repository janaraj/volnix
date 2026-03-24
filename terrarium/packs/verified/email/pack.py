"""Email service pack (Tier 1 -- verified).

Provides the canonical tool surface for email-category services.

Gmail-aligned tools: search_gmail_messages, get_gmail_message,
send_gmail_message, create_gmail_draft, modify_gmail_message,
trash_gmail_message, delete_gmail_message, list_gmail_labels.

Legacy tools (backward compatible): email_send, email_list, email_read,
email_search, email_reply, email_mark_read.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.email.handlers import (
    handle_create_gmail_draft,
    handle_delete_gmail_message,
    handle_email_list,
    handle_email_mark_read,
    handle_email_read,
    handle_email_reply,
    handle_email_search,
    handle_email_send,
    handle_get_gmail_message,
    handle_list_gmail_labels,
    handle_modify_gmail_message,
    handle_search_gmail_messages,
    handle_send_gmail_message,
    handle_trash_gmail_message,
)
from terrarium.packs.verified.email.schemas import (
    DRAFT_ENTITY_SCHEMA,
    EMAIL_ENTITY_SCHEMA,
    EMAIL_TOOL_DEFINITIONS,
    LABEL_ENTITY_SCHEMA,
    LEGACY_EMAIL_TOOL_DEFINITIONS,
    MAILBOX_ENTITY_SCHEMA,
    MESSAGE_ENTITY_SCHEMA,
    THREAD_ENTITY_SCHEMA,
)
from terrarium.packs.verified.email.state_machines import EMAIL_TRANSITIONS


class EmailPack(ServicePack):
    """Verified pack for email communication services.

    Gmail-aligned tools: search_gmail_messages, get_gmail_message,
    send_gmail_message, create_gmail_draft, modify_gmail_message,
    trash_gmail_message, delete_gmail_message, list_gmail_labels.

    Legacy tools: email_send, email_list, email_read, email_search,
    email_reply, email_mark_read.
    """

    pack_name: ClassVar[str] = "email"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        # Gmail-aligned handlers
        "send_gmail_message": handle_send_gmail_message,
        "search_gmail_messages": handle_search_gmail_messages,
        "get_gmail_message": handle_get_gmail_message,
        "modify_gmail_message": handle_modify_gmail_message,
        "trash_gmail_message": handle_trash_gmail_message,
        "delete_gmail_message": handle_delete_gmail_message,
        "create_gmail_draft": handle_create_gmail_draft,
        "list_gmail_labels": handle_list_gmail_labels,
        # Legacy handlers (backward compatibility)
        "email_send": handle_email_send,
        "email_list": handle_email_list,
        "email_read": handle_email_read,
        "email_search": handle_email_search,
        "email_reply": handle_email_reply,
        "email_mark_read": handle_email_mark_read,
    }

    def get_tools(self) -> list[dict]:
        """Return Gmail-aligned + legacy email tool definitions.

        Gmail-aligned tools are primary; legacy tools are included for
        backward compatibility so existing tool lookups continue to work.
        """
        return list(EMAIL_TOOL_DEFINITIONS) + list(LEGACY_EMAIL_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (Gmail-aligned + legacy).

        Gmail-aligned: gmail_message, gmail_thread, gmail_label, gmail_draft.
        Namespaced with ``gmail_`` to avoid collision with other packs
        (e.g. the chat pack also defines "message" entities).
        Legacy: email, mailbox, thread.
        """
        return {
            "gmail_message": MESSAGE_ENTITY_SCHEMA,
            "gmail_thread": THREAD_ENTITY_SCHEMA,
            "gmail_label": LABEL_ENTITY_SCHEMA,
            "gmail_draft": DRAFT_ENTITY_SCHEMA,
            "email": EMAIL_ENTITY_SCHEMA,
            "mailbox": MAILBOX_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for email entities.

        Only the legacy email entity type uses status-based transitions.
        Gmail-aligned entities use labels as the state mechanism.
        """
        return {"email": {"transitions": EMAIL_TRANSITIONS}}

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate email action handler."""
        return await self.dispatch_action(action, input_data, state)
