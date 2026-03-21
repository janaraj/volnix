"""Gateway-specific configuration model.

Defines the Pydantic model for gateway configuration including host/port,
middleware chain, rate limiting, and authentication settings.
"""

from __future__ import annotations

from pydantic import BaseModel


class GatewayConfig(BaseModel):
    """Configuration for the Terrarium gateway.

    Attributes:
        host: The hostname or IP address to bind to.
        port: The port number to listen on.
        middleware: Ordered list of middleware names to apply.
        rate_limit_enabled: Whether rate limiting is active.
        rate_limits: Mapping of actor role to max requests per minute.
        auth_enabled: Whether authentication is required.
    """

    host: str = "127.0.0.1"
    port: int = 8080
    middleware: list[str] = []
    rate_limit_enabled: bool = False
    rate_limits: dict[str, int] = {}
    auth_enabled: bool = False
