"""Gateway module -- single entry/exit point for the Terrarium framework.

Provides request routing through Gateway.handle_request() and tool
discovery through Gateway.get_tool_manifest().

Re-exports the primary public API surface::

    from terrarium.gateway import Gateway, GatewayConfig
"""

from terrarium.gateway.config import GatewayConfig
from terrarium.gateway.gateway import Gateway

__all__ = [
    "Gateway",
    "GatewayConfig",
]
