"""Browser service pack (Tier 1 -- verified).

Provides the canonical tool surface for web browsing within the simulated
world: navigate, search, click links, submit forms, read pages, manage
sessions. Forms bridge to other service packs via SideEffect objects
that enter the governance pipeline.
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.browser.handlers import (
    handle_web_back,
    handle_web_click_link,
    handle_web_create_session,
    handle_web_get_page,
    handle_web_list_sites,
    handle_web_navigate,
    handle_web_page_create,
    handle_web_page_modify,
    handle_web_read_page,
    handle_web_search,
    handle_web_submit_form,
)
from volnix.packs.verified.browser.schemas import (
    BROWSER_TOOL_DEFINITIONS,
    WEB_PAGE_ENTITY_SCHEMA,
    WEB_SESSION_ENTITY_SCHEMA,
    WEB_SITE_ENTITY_SCHEMA,
)
from volnix.packs.verified.browser.state_machines import (
    WEB_PAGE_TRANSITIONS,
    WEB_SESSION_TRANSITIONS,
)


class BrowserPack(ServicePack):
    """Verified pack for web browsing within the simulated world.

    Tools: web_navigate, web_search, web_read_page, web_click_link,
    web_submit_form, web_back, web_list_sites, web_get_page,
    web_create_session, web_page_modify, web_page_create.
    """

    pack_name: ClassVar[str] = "browser"
    category: ClassVar[str] = "browser"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "web_navigate": handle_web_navigate,
        "web_search": handle_web_search,
        "web_read_page": handle_web_read_page,
        "web_click_link": handle_web_click_link,
        "web_submit_form": handle_web_submit_form,
        "web_back": handle_web_back,
        "web_list_sites": handle_web_list_sites,
        "web_get_page": handle_web_get_page,
        "web_create_session": handle_web_create_session,
        "web_page_modify": handle_web_page_modify,
        "web_page_create": handle_web_page_create,
    }

    def get_tools(self) -> list[dict]:
        """Return the browser tool manifest."""
        return list(BROWSER_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (web_site, web_page, web_session)."""
        return {
            "web_site": WEB_SITE_ENTITY_SCHEMA,
            "web_page": WEB_PAGE_ENTITY_SCHEMA,
            "web_session": WEB_SESSION_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for web_page and web_session entities."""
        return {
            "web_page": {"transitions": WEB_PAGE_TRANSITIONS},
            "web_session": {"transitions": WEB_SESSION_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate browser action handler."""
        return await self.dispatch_action(action, input_data, state)
