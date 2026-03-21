"""Gateway monitoring for the Terrarium framework.

Tracks request/response lifecycle events and errors for observability,
optionally recording metrics to the event ledger.
"""

from __future__ import annotations

from terrarium.core.context import ActionContext
from terrarium.core.protocols import LedgerProtocol


class GatewayMonitor:
    """Monitors gateway request lifecycle for observability."""

    def __init__(self, ledger: LedgerProtocol | None = None) -> None:
        ...

    async def on_request(self, ctx: ActionContext) -> None:
        """Record that a request has been received.

        Args:
            ctx: The action context for the incoming request.
        """
        ...

    async def on_response(self, ctx: ActionContext, latency_ms: float) -> None:
        """Record that a response has been sent.

        Args:
            ctx: The action context for the completed request.
            latency_ms: Wall-clock latency in milliseconds.
        """
        ...

    async def on_error(self, ctx: ActionContext, error: Exception) -> None:
        """Record that an error occurred during request processing.

        Args:
            ctx: The action context for the failed request.
            error: The exception that was raised.
        """
        ...

    async def get_metrics(self) -> dict:
        """Return aggregated gateway metrics.

        Returns:
            A dictionary of metric names to values.
        """
        ...
