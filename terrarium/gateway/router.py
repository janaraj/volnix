"""Request router for the Terrarium gateway.

Translates raw inbound requests into :class:`~terrarium.core.ActionContext`
objects, determining the target service and entity from the request data.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.context import ActionContext
from terrarium.core.protocols import AdapterProtocol
from terrarium.core.types import ActorId, EntityId, ServiceId, ToolName


class RequestRouter:
    """Routes raw external requests to action contexts."""

    def __init__(self, adapter: AdapterProtocol) -> None:
        ...

    async def route(
        self,
        raw_request: Any,
        protocol: str,
        actor_id: ActorId,
    ) -> ActionContext:
        """Translate a raw request into an action context.

        Args:
            raw_request: The raw request payload.
            protocol: The protocol the request arrived on.
            actor_id: The authenticated actor making the request.

        Returns:
            A populated :class:`ActionContext` ready for pipeline execution.
        """
        ...

    def _determine_service(self, action: ToolName) -> ServiceId:
        """Determine which service handles a given tool action.

        Args:
            action: The tool name being invoked.

        Returns:
            The :class:`ServiceId` of the responsible service.
        """
        ...

    def _determine_target_entity(self, input_data: dict) -> EntityId | None:
        """Extract the target entity from request input data, if present.

        Args:
            input_data: The translated input data dictionary.

        Returns:
            The :class:`EntityId` of the target entity, or ``None``.
        """
        ...
