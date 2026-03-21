"""Gateway module -- single entry/exit point for the Terrarium framework.

Provides request routing, authentication, rate limiting, monitoring,
and a middleware chain for the external-facing API surface.

Re-exports the primary public API surface::

    from terrarium.gateway import Gateway, RequestRouter, GatewayConfig
"""

from terrarium.gateway.auth import Authenticator
from terrarium.gateway.config import GatewayConfig
from terrarium.gateway.gateway import Gateway
from terrarium.gateway.middleware import GatewayMiddleware, GatewayMiddlewareChain
from terrarium.gateway.monitor import GatewayMonitor
from terrarium.gateway.rate_limiter import RateLimiter
from terrarium.gateway.router import RequestRouter

__all__ = [
    "Authenticator",
    "Gateway",
    "GatewayConfig",
    "GatewayMiddleware",
    "GatewayMiddlewareChain",
    "GatewayMonitor",
    "RateLimiter",
    "RequestRouter",
]
