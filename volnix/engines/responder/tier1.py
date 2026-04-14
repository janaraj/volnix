"""Tier 1 dispatcher -- verified service packs."""

from __future__ import annotations

from typing import Any

from volnix.core.context import ActionContext, ResponseProposal
from volnix.packs.runtime import PackRuntime


class Tier1Dispatcher:
    """Dispatches requests to verified service packs (highest fidelity).

    Passes world state from the ActionContext to the pack runtime so
    stateful actions (list, read, search) see the current world.
    """

    def __init__(self, pack_runtime: PackRuntime) -> None:
        self._runtime = pack_runtime

    async def dispatch(
        self, ctx: ActionContext, state: dict[str, Any] | None = None
    ) -> ResponseProposal:
        """Dispatch the action to the matching verified pack.

        Args:
            ctx: The action context with action name, input data, and
                the calling actor's id.
            state: Current world state relevant to this action. If None,
                   the pack runtime will use an empty dict.
        """
        return await self._runtime.execute(
            action=ctx.action,
            input_data=ctx.input_data or {},
            state=state,
            service_id=str(ctx.service_id) if ctx.service_id else None,
            actor_id=str(ctx.actor_id) if ctx.actor_id else None,
        )

    def has_pack_for_tool(self, tool_name: str) -> bool:
        """Check if any registered pack handles this tool."""
        return self._runtime.has_tool(tool_name)
