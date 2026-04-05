"""Gateway module -- single entry/exit point for the Volnix framework.

Provides request routing through Gateway.handle_request() and tool
discovery through Gateway.get_tool_manifest().

Re-exports the primary public API surface::

    from volnix.gateway import Gateway, GatewayConfig
"""

from volnix.gateway.config import GatewayConfig
from volnix.gateway.gateway import Gateway

__all__ = [
    "Gateway",
    "GatewayConfig",
]
