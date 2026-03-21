"""Tier 1 dispatcher -- verified service packs."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActionContext, ResponseProposal, ServiceId


class Tier1Dispatcher:
    """Dispatches requests to verified service packs (highest fidelity)."""

    def __init__(self, pack_registry: dict[str, Any]) -> None:
        self._pack_registry = pack_registry

    async def dispatch(self, ctx: ActionContext) -> ResponseProposal:
        """Dispatch the action to the matching verified pack."""
        ...

    def get_pack(self, service_id: ServiceId) -> Any | None:
        """Look up the service pack for the given service id.

        Returns:
            The ServicePack instance or ``None`` if not found.
        """
        ...
