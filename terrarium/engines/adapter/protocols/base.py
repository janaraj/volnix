"""Abstract base class for protocol adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from terrarium.core import ActionContext, ActorId


class ProtocolAdapter(ABC):
    """Abstract base for all protocol adapters.

    Each concrete adapter translates between one external protocol
    (MCP, ACP, OpenAI, Anthropic, HTTP) and the internal ActionContext.
    """

    protocol_name: ClassVar[str] = ""

    @abstractmethod
    async def translate_inbound(self, raw_request: Any) -> ActionContext:
        """Translate a raw protocol request into an ActionContext."""
        ...

    @abstractmethod
    async def translate_outbound(self, ctx: ActionContext) -> Any:
        """Translate an ActionContext back to the external protocol format."""
        ...

    @abstractmethod
    async def get_tool_manifest(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return the tool manifest for an actor in this protocol's format."""
        ...

    @abstractmethod
    async def start_server(self) -> None:
        """Start the protocol server (if applicable)."""
        ...

    @abstractmethod
    async def stop_server(self) -> None:
        """Stop the protocol server."""
        ...
