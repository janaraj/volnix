"""LLM usage tracker for the Terrarium framework.

Records LLM request/response metrics and provides aggregation by actor,
engine, and total usage.  Optionally integrates with the event ledger
for persistent auditing.
"""

from __future__ import annotations

from terrarium.core.protocols import LedgerProtocol
from terrarium.core.types import ActorId
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage


class UsageTracker:
    """Tracks LLM token usage and cost across actors and engines."""

    def __init__(self, ledger: LedgerProtocol | None = None) -> None:
        ...

    async def record(
        self,
        request: LLMRequest,
        response: LLMResponse,
        engine_name: str,
        actor_id: ActorId | None = None,
    ) -> None:
        """Record usage from a completed LLM request/response pair.

        Args:
            request: The original LLM request.
            response: The LLM response received.
            engine_name: Name of the engine that initiated the request.
            actor_id: Optional actor who triggered the request.
        """
        ...

    async def get_usage_by_actor(self, actor_id: ActorId) -> LLMUsage:
        """Return aggregate LLM usage for a specific actor.

        Args:
            actor_id: The actor identifier.

        Returns:
            Aggregated usage across all requests by this actor.
        """
        ...

    async def get_usage_by_engine(self, engine_name: str) -> LLMUsage:
        """Return aggregate LLM usage for a specific engine.

        Args:
            engine_name: The engine name.

        Returns:
            Aggregated usage across all requests by this engine.
        """
        ...

    async def get_total_usage(self) -> LLMUsage:
        """Return total aggregate LLM usage across all actors and engines.

        Returns:
            Aggregated usage for the entire system.
        """
        ...

    async def get_cost_by_actor(self, actor_id: ActorId) -> float:
        """Return the total LLM cost in USD for a specific actor.

        Args:
            actor_id: The actor identifier.

        Returns:
            Total cost in US dollars.
        """
        ...
