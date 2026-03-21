"""Registry for custom functions available in policy condition expressions."""

from __future__ import annotations

from typing import Any, Callable


class PolicyFunctionRegistry:
    """Manages named functions that policy conditions can invoke."""

    def __init__(self) -> None:
        self._registry: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, func: Callable[..., Any]) -> None:
        """Register a function under the given name."""
        ...

    def get(self, name: str) -> Callable[..., Any] | None:
        """Retrieve a registered function by name."""
        ...

    def list_functions(self) -> list[str]:
        """Return the names of all registered functions."""
        ...
