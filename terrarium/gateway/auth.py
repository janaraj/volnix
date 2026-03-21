"""Authentication for the Terrarium gateway.

Provides request authentication and token validation, returning the
authenticated :class:`~terrarium.core.types.ActorId` on success.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.types import ActorId


class Authenticator:
    """Authenticates inbound gateway requests."""

    def __init__(self, config: dict[str, Any]) -> None:
        ...

    async def authenticate(
        self,
        raw_request: Any,
        protocol: str,
    ) -> ActorId | None:
        """Authenticate a raw request and return the actor identity.

        Args:
            raw_request: The raw request payload.
            protocol: The protocol the request arrived on.

        Returns:
            The authenticated :class:`ActorId`, or ``None`` if authentication fails.
        """
        ...

    async def validate_token(self, token: str) -> ActorId | None:
        """Validate a bearer token and return the associated actor.

        Args:
            token: The bearer token string.

        Returns:
            The :class:`ActorId` associated with the token, or ``None`` if invalid.
        """
        ...
