"""Runtime configuration registry for the Terrarium framework.

Provides a centralised access point for reading configuration values,
subscribing to changes on specific keys, and updating tunable parameters
at runtime.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from terrarium.config.schema import TerrariumConfig


class ConfigRegistry:
    """Centralised registry providing typed access to configuration sections.

    Supports runtime subscriptions for tunable parameter changes.
    """

    def __init__(self, config: TerrariumConfig) -> None:
        ...

    def get(self, section: str, key: str) -> Any:
        """Retrieve a single configuration value by section and key.

        Args:
            section: The configuration section name.
            key: The key within that section.

        Returns:
            The configuration value.
        """
        ...

    def get_section(self, section: str) -> BaseModel:
        """Retrieve an entire configuration section model.

        Args:
            section: The configuration section name.

        Returns:
            The Pydantic model for the requested section.
        """
        ...

    def subscribe(self, section: str, key: str, callback: Callable[..., Any]) -> None:
        """Register a callback to be notified when a tunable value changes.

        Args:
            section: The configuration section name.
            key: The key within that section.
            callback: A callable invoked with ``(section, key, new_value)``.
        """
        ...

    def update_tunable(self, section: str, key: str, value: Any) -> None:
        """Update a tunable configuration value at runtime.

        Notifies all subscribers registered for this section/key.

        Args:
            section: The configuration section name.
            key: The key within that section.
            value: The new value to set.
        """
        ...
