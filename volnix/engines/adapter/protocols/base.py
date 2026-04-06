"""Abstract base class for protocol adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from volnix.core.types import ToolName


class ProtocolAdapter(ABC):
    """Abstract base for all protocol adapters.

    Each concrete adapter translates between one external protocol
    (MCP, ACP, OpenAI, Anthropic, HTTP) and the internal format.

    Method signatures match ``core.protocols.AdapterProtocol``.
    """

    protocol_name: ClassVar[str] = ""

    @abstractmethod
    async def translate_inbound(
        self,
        tool_name: ToolName,
        raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate an external tool invocation into canonical form."""
        ...

    @abstractmethod
    async def translate_outbound(
        self,
        tool_name: ToolName,
        internal_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate an internal response back to external format."""
        ...

    @abstractmethod
    async def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return the manifest of all tools this adapter exposes."""
        ...

    @abstractmethod
    async def start_server(self) -> None:
        """Start the protocol server (if applicable)."""
        ...

    @abstractmethod
    async def stop_server(self) -> None:
        """Stop the protocol server."""
        ...
