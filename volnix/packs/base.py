"""Abstract base classes for service packs and profiles.

:class:`ServicePack` (Tier 1) defines the category-level simulation with
tools, entity schemas, and state machines.  :class:`ServiceProfile`
(Tier 2) extends a pack with service-specific fidelity enhancements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.errors import PackNotFoundError
from volnix.core.types import ToolName

# Type alias for pack action handlers
ActionHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[ResponseProposal]]


class ServicePack(ABC):
    """Abstract base for Tier-1 verified service packs.

    A pack provides the canonical tool surface, entity schemas, and
    state machines for an entire service category (e.g. all email
    services share the same EmailPack).

    Class Attributes:
        pack_name: Unique name identifying this pack.
        category: The semantic category this pack serves.
        fidelity_tier: Always ``1`` for verified packs.
    """

    pack_name: ClassVar[str] = ""
    category: ClassVar[str] = ""
    fidelity_tier: ClassVar[int] = 1

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Return the tool manifest for this pack.

        Returns:
            A list of tool definition dicts.
        """
        ...

    @abstractmethod
    def get_entity_schemas(self) -> dict:
        """Return entity type schemas managed by this pack.

        Returns:
            A dict mapping entity type names to their schema dicts.
        """
        ...

    @abstractmethod
    def get_state_machines(self) -> dict:
        """Return state machine definitions for entities in this pack.

        Returns:
            A dict mapping entity type names to state machine dicts.
        """
        ...

    @abstractmethod
    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Handle an incoming tool action and return a response proposal.

        Args:
            action: The tool name being invoked.
            input_data: The input payload for the tool call.
            state: The current world state relevant to this action.

        Returns:
            A :class:`ResponseProposal` with the simulated result.
        """
        ...

    # ---- Concrete dispatch helper ----
    _handlers: ClassVar[dict[str, ActionHandler]] = {}

    async def dispatch_action(
        self,
        action: ToolName,
        input_data: dict[str, Any],
        state: dict[str, Any],
    ) -> ResponseProposal:
        """Data-driven dispatch to registered _handlers.

        Packs that populate _handlers as a ClassVar can delegate
        handle_action to this method in a single line:
            async def handle_action(self, action, input_data, state):
                return await self.dispatch_action(action, input_data, state)

        Raises:
            PackNotFoundError: If no handler is registered for the action.
        """
        handler = self._handlers.get(str(action))
        if handler is None:
            known = sorted(self._handlers.keys())
            raise PackNotFoundError(
                f"Pack '{self.pack_name}' has no handler for action '{action}'. Available: {known}"
            )
        return await handler(input_data, state)

    def get_tool_names(self) -> list[str]:
        """Return just the tool name strings (convenience)."""
        tools = self.get_tools()
        if not isinstance(tools, list):
            return []
        return [t.get("name", "") for t in tools if isinstance(t, dict)]


class ServiceProfile(ABC):
    """Abstract base for Tier-2 profiled service overlays.

    A profile extends a verified pack with service-specific behavioural
    annotations, additional tools, response schemas, and an LLM
    responder prompt that captures the service's unique personality.

    Class Attributes:
        profile_name: Unique name identifying this profile.
        extends_pack: The :attr:`pack_name` of the pack this profile extends.
        category: The semantic category (should match the pack's category).
        fidelity_tier: Always ``2`` for profiled services.
    """

    profile_name: ClassVar[str] = ""
    extends_pack: ClassVar[str] = ""
    category: ClassVar[str] = ""
    fidelity_tier: ClassVar[int] = 2

    @abstractmethod
    def get_additional_tools(self) -> list[dict]:
        """Return additional tools introduced by this profile.

        Returns:
            A list of tool definition dicts.
        """
        ...

    @abstractmethod
    def get_additional_entities(self) -> dict:
        """Return additional entity schemas introduced by this profile.

        Returns:
            A dict mapping entity type names to their schema dicts.
        """
        ...

    @abstractmethod
    def get_behavioral_annotations(self) -> list[str]:
        """Return behavioural annotations describing service-specific quirks.

        Returns:
            A list of annotation strings.
        """
        ...

    @abstractmethod
    def get_responder_prompt(self) -> str:
        """Return the LLM system prompt for generating service-like responses.

        Returns:
            A prompt string.
        """
        ...

    @abstractmethod
    def get_response_schema(self, action: ToolName) -> dict:
        """Return the expected response schema for a given action.

        Args:
            action: The tool name to get the response schema for.

        Returns:
            A JSON-Schema-style dict.
        """
        ...
