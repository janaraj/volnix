"""Main gateway class for the Terrarium framework.

The :class:`Gateway` is the single entry and exit point for all external
requests flowing into the Terrarium simulation.  It coordinates the
adapter, pipeline, ledger, and monitoring subsystems.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.events import Event
from terrarium.core.protocols import AdapterProtocol, LedgerProtocol
from terrarium.core.types import ActorId
from terrarium.gateway.config import GatewayConfig
from terrarium.pipeline.dag import PipelineDAG


class Gateway:
    """Single entry/exit point for external requests into Terrarium."""

    def __init__(
        self,
        config: GatewayConfig,
        pipeline: PipelineDAG,
        adapter: AdapterProtocol,
        ledger: LedgerProtocol | None = None,
    ) -> None:
        ...

    async def initialize(self) -> None:
        """Initialize the gateway and its subsystems."""
        ...

    async def shutdown(self) -> None:
        """Gracefully shut down the gateway."""
        ...

    async def handle_request(
        self,
        raw_request: Any,
        protocol: str,
        actor_id: ActorId,
    ) -> Any:
        """Handle an inbound request from an external actor.

        Translates the raw request via the adapter, runs the governance
        pipeline, and returns the translated response.

        Args:
            raw_request: The raw request payload from the external system.
            protocol: The protocol the request arrived on (e.g. ``"mcp"``, ``"http"``).
            actor_id: The authenticated actor making the request.

        Returns:
            The translated response payload.
        """
        ...

    async def deliver_observation(self, event: Event, actor_id: ActorId) -> None:
        """Deliver an observation event to an external actor.

        Args:
            event: The event to deliver.
            actor_id: The actor to deliver the observation to.
        """
        ...
