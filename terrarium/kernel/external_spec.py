"""External spec provider protocol.

Any source of API specifications implements this protocol:
- ContextHubProvider (chub CLI via npx @aisuite/chub)
- OpenAPIProvider (parse spec files/URLs)
- Future: MCP manifest provider, etc.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExternalSpecProvider(Protocol):
    """Protocol for external API spec sources."""
    provider_name: str

    async def is_available(self) -> bool:
        """Check if this provider is accessible."""
        ...

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Fetch raw spec for a service. Returns None if not available."""
        ...

    async def supports(self, service_name: str) -> bool:
        """Quick check if this provider likely has the service."""
        ...
