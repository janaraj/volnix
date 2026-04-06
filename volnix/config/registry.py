"""Runtime configuration registry for the Volnix framework.

Provides a centralised access point for reading configuration values,
subscribing to changes on specific keys, and updating tunable parameters
at runtime.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from pydantic import BaseModel

from volnix.config.schema import VolnixConfig


class ConfigRegistry:
    """Centralised registry providing typed access to configuration sections.

    Supports runtime subscriptions for tunable parameter changes.
    """

    def __init__(self, config: VolnixConfig) -> None:
        self._config = config
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def get(self, section: str, key: str) -> Any:
        """Retrieve a single configuration value by section and key.

        Args:
            section: The configuration section name.
            key: The key within that section.

        Returns:
            The configuration value.

        Raises:
            AttributeError: If the section or key does not exist.
        """
        section_model = self.get_section(section)
        return getattr(section_model, key)

    def get_section(self, section: str) -> BaseModel:
        """Retrieve an entire configuration section model.

        Args:
            section: The configuration section name.

        Returns:
            The Pydantic model for the requested section.

        Raises:
            AttributeError: If the section does not exist.
        """
        return getattr(self._config, section)

    def subscribe(self, section: str, key: str, callback: Callable[..., Any]) -> None:
        """Register a callback to be notified when a tunable value changes.

        Args:
            section: The configuration section name.
            key: The key within that section.
            callback: A callable invoked with ``(section, key, new_value)``.
        """
        listener_key = f"{section}.{key}"
        self._listeners[listener_key].append(callback)

    def update_tunable(self, section: str, key: str, value: Any) -> None:
        """Update a tunable configuration value at runtime.

        Notifies all subscribers registered for this section/key.

        Args:
            section: The configuration section name.
            key: The key within that section.
            value: The new value to set.
        """
        section_model = self.get_section(section)
        # Validate the new value against the Pydantic schema
        updated_data = section_model.model_dump()
        updated_data[key] = value
        updated_model = type(section_model).model_validate(updated_data)
        # Replace the section on the root config
        self._config = self._config.model_copy(update={section: updated_model})

        # Notify listeners
        listener_key = f"{section}.{key}"
        for callback in self._listeners.get(listener_key, []):
            callback(section, key, value)
