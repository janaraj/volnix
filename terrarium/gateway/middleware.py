"""Gateway middleware protocol and chain for the Terrarium framework.

Defines the middleware interface and a chain that composes multiple
middleware instances into a sequential processing pipeline.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class GatewayMiddleware(Protocol):
    """Protocol for gateway middleware components.

    Each middleware receives the request and a ``next_handler`` callable
    that invokes the next middleware in the chain (or the final handler).
    """

    async def process(self, request: Any, next_handler: Callable[..., Any]) -> Any:
        """Process a request, optionally delegating to the next handler.

        Args:
            request: The request payload.
            next_handler: An async callable for the next middleware or handler.

        Returns:
            The response payload.
        """
        ...


class GatewayMiddlewareChain:
    """Composes multiple middleware instances into a sequential chain."""

    def __init__(self) -> None:
        ...

    def add(self, middleware: GatewayMiddleware) -> None:
        """Append a middleware to the chain.

        Args:
            middleware: The middleware instance to add.
        """
        ...

    async def process(self, request: Any) -> Any:
        """Run the request through the full middleware chain.

        Args:
            request: The request payload to process.

        Returns:
            The response payload after all middleware have processed.
        """
        ...
