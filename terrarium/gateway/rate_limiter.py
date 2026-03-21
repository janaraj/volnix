"""Rate limiter for the Terrarium gateway.

Enforces per-actor, per-role request rate limits using a sliding-window
approach.
"""

from __future__ import annotations

from terrarium.core.types import ActorId


class RateLimiter:
    """Sliding-window rate limiter keyed by actor identity and role."""

    def __init__(self, config: dict[str, int]) -> None:
        """Initialize the rate limiter.

        Args:
            config: A mapping of actor role to maximum requests per minute.
        """
        ...

    async def check(self, actor_id: ActorId, actor_role: str) -> bool:
        """Check whether the actor is within their rate limit.

        Args:
            actor_id: The actor to check.
            actor_role: The role of the actor (used to look up the limit).

        Returns:
            ``True`` if the request is allowed, ``False`` if rate-limited.
        """
        ...

    async def record(self, actor_id: ActorId) -> None:
        """Record a request for rate-limiting purposes.

        Args:
            actor_id: The actor who made the request.
        """
        ...

    async def reset(self, actor_id: ActorId) -> None:
        """Reset the rate-limit window for an actor.

        Args:
            actor_id: The actor whose rate-limit counters should be cleared.
        """
        ...
