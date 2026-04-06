"""Notion service pack (Tier 1 -- verified).

Provides the canonical tool surface for Notion-style document/database
services: pages (create, retrieve, update), databases (create, retrieve,
query), blocks (children list, children append, retrieve, delete), users
(list, me), search, and comments (create, list).
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.notion.handlers import (
    handle_blocks_children_append,
    handle_blocks_children_list,
    handle_blocks_delete,
    handle_blocks_retrieve,
    handle_comments_create,
    handle_comments_list,
    handle_databases_create,
    handle_databases_query,
    handle_databases_retrieve,
    handle_pages_create,
    handle_pages_retrieve,
    handle_pages_update,
    handle_search,
    handle_users_list,
    handle_users_me,
)
from volnix.packs.verified.notion.schemas import (
    BLOCK_ENTITY_SCHEMA,
    COMMENT_ENTITY_SCHEMA,
    DATABASE_ENTITY_SCHEMA,
    NOTION_TOOL_DEFINITIONS,
    PAGE_ENTITY_SCHEMA,
    USER_ENTITY_SCHEMA,
)
from volnix.packs.verified.notion.state_machines import ARCHIVED_TRANSITIONS


class NotionPack(ServicePack):
    """Verified pack for Notion-style document and database services.

    Tools: pages.create, pages.retrieve, pages.update,
    databases.create, databases.retrieve, databases.query,
    blocks.children.list, blocks.children.append, blocks.retrieve,
    blocks.delete, users.list, users.me, search,
    comments.create, comments.list.
    """

    pack_name: ClassVar[str] = "notion"
    category: ClassVar[str] = "storage_documents"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "pages.create": handle_pages_create,
        "pages.retrieve": handle_pages_retrieve,
        "pages.update": handle_pages_update,
        "databases.create": handle_databases_create,
        "databases.retrieve": handle_databases_retrieve,
        "databases.query": handle_databases_query,
        "blocks.children.list": handle_blocks_children_list,
        "blocks.children.append": handle_blocks_children_append,
        "blocks.retrieve": handle_blocks_retrieve,
        "blocks.delete": handle_blocks_delete,
        "users.list": handle_users_list,
        "users.me": handle_users_me,
        "search": handle_search,
        "comments.create": handle_comments_create,
        "comments.list": handle_comments_list,
    }

    def get_tools(self) -> list[dict]:
        """Return the Notion tool manifest."""
        return list(NOTION_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (page, database, block, user, comment)."""
        return {
            "page": PAGE_ENTITY_SCHEMA,
            "database": DATABASE_ENTITY_SCHEMA,
            "block": BLOCK_ENTITY_SCHEMA,
            "user": USER_ENTITY_SCHEMA,
            "comment": COMMENT_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for archivable entities."""
        return {
            "page": {"transitions": ARCHIVED_TRANSITIONS},
            "database": {"transitions": ARCHIVED_TRANSITIONS},
            "block": {"transitions": ARCHIVED_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate Notion action handler."""
        return await self.dispatch_action(action, input_data, state)
