"""Raw REST endpoints mimicking real service APIs."""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import ActionContext, ActorId
from terrarium.engines.adapter.protocols.base import ProtocolAdapter


class HTTPRestAdapter(ProtocolAdapter):
    """Raw REST endpoints mimicking real service APIs."""

    protocol_name: ClassVar[str] = "http"

    async def translate_inbound(self, raw_request: Any) -> ActionContext:
        """Translate an HTTP REST request into an ActionContext."""
        ...

    async def translate_outbound(self, ctx: ActionContext) -> Any:
        """Translate an ActionContext result into an HTTP response."""
        ...

    async def get_tool_manifest(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return tools as REST endpoint descriptions."""
        ...

    async def start_server(self) -> None:
        """Start the HTTP REST server."""
        ...

    async def stop_server(self) -> None:
        """Stop the HTTP REST server."""
        ...
