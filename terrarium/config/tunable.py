"""Tunable field management for the Terrarium configuration system.

Provides a registry of configuration fields that may be modified at runtime
(e.g. via dashboard or API), along with validation and change-notification
support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TunableField:
    """Descriptor for a single tunable configuration field.

    Attributes:
        section: The configuration section this field belongs to.
        key: The key within the section.
        current_value: The current runtime value.
        default_value: The original default value.
        validators: A list of callables that validate proposed new values.
    """

    section: str
    key: str
    current_value: Any
    default_value: Any
    validators: list[Callable[..., bool]] = field(default_factory=list)


class TunableRegistry:
    """Registry of tunable configuration fields with change listeners."""

    def register(self, field: TunableField) -> None:
        """Register a tunable field.

        Args:
            field: The tunable field descriptor to register.
        """
        ...

    def update(self, section: str, key: str, value: Any) -> None:
        """Update a tunable field value after validation.

        Args:
            section: The configuration section.
            key: The key within the section.
            value: The new value to set.
        """
        ...

    def get(self, section: str, key: str) -> Any:
        """Retrieve the current value of a tunable field.

        Args:
            section: The configuration section.
            key: The key within the section.

        Returns:
            The current value of the tunable field.
        """
        ...

    def list_tunable(self) -> list[TunableField]:
        """Return all registered tunable fields.

        Returns:
            A list of all tunable field descriptors.
        """
        ...

    def add_listener(self, section: str, key: str, callback: Callable[..., Any]) -> None:
        """Register a callback to be invoked when a tunable field changes.

        Args:
            section: The configuration section.
            key: The key within the section.
            callback: A callable invoked with ``(section, key, new_value)``.
        """
        ...
