"""GamePack — verified Tier 1 service pack for negotiation games.

Exposes four structured negotiation tools as a single service
(``service_id="game"``). Handlers in ``handlers.py`` write atomic deal
state deltas through the pipeline commit step (MF1).

Entity schemas + static tool definitions live in ``schemas.py``.
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.game.handlers import (
    handle_negotiate_accept,
    handle_negotiate_counter,
    handle_negotiate_propose,
    handle_negotiate_reject,
)
from volnix.packs.verified.game.schemas import (
    GAME_PLAYER_BRIEF_SCHEMA,
    GAME_TOOL_DEFINITIONS,
    NEGOTIATION_DEAL_SCHEMA,
    NEGOTIATION_PROPOSAL_SCHEMA,
    NEGOTIATION_TARGET_TERMS_SCHEMA,
)


class GamePack(ServicePack):
    """Verified pack for the ``game`` service.

    Handles the four fixed structured negotiation tools. The tool
    parameter schema is one of two shapes:

    - **Static fallback** (``deal_id`` + optional ``message`` with
      ``additionalProperties: True``) — used when the blueprint
      declares no ``game.negotiation_fields``. Returned by
      :meth:`get_tools` for pack-registry discovery and listed in
      :data:`GAME_TOOL_DEFINITIONS`.
    - **Dynamic typed schema** — built at game configure time by
      :func:`volnix.packs.verified.game.tool_schema.build_negotiation_tools`
      from the blueprint's top-level ``game.negotiation_fields`` and
      registered on the agency via
      :meth:`volnix.engines.agency.engine.AgencyEngine.register_game_tools`.
      This is the live code path for any blueprint that declares typed
      negotiation fields. See NF1 in ``internal_docs/game/`` for the
      migration history.

    Tools: negotiate_propose, negotiate_counter, negotiate_accept,
    negotiate_reject.

    Entity types owned by this pack:
    - negotiation_deal
    - negotiation_proposal
    - game_player_brief (visibility-rule filtered)
    - negotiation_target_terms (competitive mode only)
    """

    pack_name: ClassVar[str] = "game"
    category: ClassVar[str] = "game"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "negotiate_propose": handle_negotiate_propose,
        "negotiate_counter": handle_negotiate_counter,
        "negotiate_accept": handle_negotiate_accept,
        "negotiate_reject": handle_negotiate_reject,
    }

    def get_tools(self) -> list[dict]:
        """Return the static fallback tool manifest.

        The static shape (``deal_id`` + ``message`` only) is used for
        pack-registry discovery so the responder can route the four
        tool names to this pack. The parameter schema surfaced to LLMs
        is overridden at game configure time by
        :meth:`AgencyEngine.register_game_tools`, which calls
        :func:`volnix.packs.verified.game.tool_schema.build_negotiation_tools`
        on the blueprint's ``game.negotiation_fields`` to build the
        typed dynamic schema.
        """
        return list(GAME_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return schemas for the four entity types owned by this pack."""
        return {
            "negotiation_deal": NEGOTIATION_DEAL_SCHEMA,
            "negotiation_proposal": NEGOTIATION_PROPOSAL_SCHEMA,
            "game_player_brief": GAME_PLAYER_BRIEF_SCHEMA,
            "negotiation_target_terms": NEGOTIATION_TARGET_TERMS_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines — the deal lifecycle is enforced here.

        Simple forward-only state machine:
            open -> proposed -> countered -> accepted (terminal)
                               -> rejected (terminal)
        """
        return {
            "negotiation_deal": {
                "transitions": {
                    "open": ["proposed"],
                    "proposed": ["countered", "accepted", "rejected"],
                    "countered": ["proposed", "countered", "accepted", "rejected"],
                    "accepted": [],
                    "rejected": [],
                },
            },
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the matching handler via the ServicePack base dispatcher."""
        return await self.dispatch_action(action, input_data, state)
