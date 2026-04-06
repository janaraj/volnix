"""LLM usage tracker for the Volnix framework.

Records LLM request/response metrics and provides aggregation by actor,
engine, and total usage.  Optionally integrates with the event ledger
for persistent auditing.
"""

from __future__ import annotations

import asyncio

from volnix.core.protocols import LedgerProtocol
from volnix.core.types import ActorId
from volnix.ledger.entries import LLMCallEntry
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage


class UsageTracker:
    """Tracks LLM token usage and cost across actors and engines."""

    def __init__(self, ledger: LedgerProtocol | None = None) -> None:
        self._ledger = ledger
        self._lock = asyncio.Lock()
        self._by_actor: dict[str, LLMUsage] = {}
        self._by_engine: dict[str, LLMUsage] = {}
        self._total = LLMUsage()

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
        async with self._lock:
            # Append ledger entry if a ledger is configured
            if self._ledger:
                entry = LLMCallEntry(
                    provider=response.provider,
                    model=response.model,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    cost_usd=response.usage.cost_usd,
                    latency_ms=response.latency_ms,
                    success=response.error is None,
                    engine_name=engine_name,
                )
                await self._ledger.append(entry)

            # Update in-memory aggregates
            self._update_aggregate(self._by_engine, engine_name, response.usage)
            if actor_id:
                self._update_aggregate(self._by_actor, str(actor_id), response.usage)
            self._total = self._merge_usage(self._total, response.usage)

    def _update_aggregate(self, store: dict[str, LLMUsage], key: str, usage: LLMUsage) -> None:
        """Merge *usage* into the aggregate stored at *key*.

        Args:
            store: The aggregate dictionary.
            key: The aggregation key (actor id or engine name).
            usage: The usage to merge in.
        """
        existing = store.get(key, LLMUsage())
        store[key] = self._merge_usage(existing, usage)

    def _merge_usage(self, a: LLMUsage, b: LLMUsage) -> LLMUsage:
        """Sum two :class:`LLMUsage` records.

        Args:
            a: First usage record.
            b: Second usage record.

        Returns:
            A new :class:`LLMUsage` with summed fields.
        """
        return LLMUsage(
            prompt_tokens=a.prompt_tokens + b.prompt_tokens,
            completion_tokens=a.completion_tokens + b.completion_tokens,
            total_tokens=a.total_tokens + b.total_tokens,
            cost_usd=a.cost_usd + b.cost_usd,
        )

    async def get_usage_by_actor(self, actor_id: ActorId) -> LLMUsage:
        """Return aggregate LLM usage for a specific actor.

        Args:
            actor_id: The actor identifier.

        Returns:
            Aggregated usage across all requests by this actor.
        """
        return self._by_actor.get(str(actor_id), LLMUsage())

    async def get_usage_by_engine(self, engine_name: str) -> LLMUsage:
        """Return aggregate LLM usage for a specific engine.

        Args:
            engine_name: The engine name.

        Returns:
            Aggregated usage across all requests by this engine.
        """
        return self._by_engine.get(engine_name, LLMUsage())

    async def get_total_usage(self) -> LLMUsage:
        """Return total aggregate LLM usage across all actors and engines.

        Returns:
            Aggregated usage for the entire system.
        """
        return self._total

    async def get_cost_by_actor(self, actor_id: ActorId) -> float:
        """Return the total LLM cost in USD for a specific actor.

        Args:
            actor_id: The actor identifier.

        Returns:
            Total cost in US dollars.
        """
        usage = self._by_actor.get(str(actor_id), LLMUsage())
        return usage.cost_usd
