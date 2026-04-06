"""Tunable field management for the Volnix configuration system.

Provides a registry of configuration fields that may be modified at runtime
(e.g. via dashboard or API), along with validation and change-notification
support.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


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
    """Registry of tunable configuration fields with change listeners.

    If a ``config_registry`` is provided, updates are also propagated to it
    so that both registries stay in sync.
    """

    def __init__(self, config_registry: Any | None = None) -> None:
        self._fields: dict[str, TunableField] = {}
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        self._config_registry = config_registry

    def register(self, field: TunableField) -> None:
        """Register a tunable field.

        Args:
            field: The tunable field descriptor to register.
        """
        key = f"{field.section}.{field.key}"
        self._fields[key] = field

    def update(self, section: str, key: str, value: Any) -> None:
        """Update a tunable field value after validation.

        Args:
            section: The configuration section.
            key: The key within the section.
            value: The new value to set.

        Raises:
            KeyError: If the field is not registered.
            ValueError: If any validator rejects the new value.
        """
        field_key = f"{section}.{key}"
        if field_key not in self._fields:
            raise KeyError(f"Tunable field '{field_key}' is not registered")

        tunable = self._fields[field_key]

        # Run all validators
        for validator in tunable.validators:
            if not validator(value):
                raise ValueError(f"Validation failed for '{field_key}' with value {value!r}")

        tunable.current_value = value

        # Propagate to ConfigRegistry if linked
        if self._config_registry is not None:
            self._config_registry.update_tunable(section, key, value)

        # Notify listeners
        for callback in self._listeners.get(field_key, []):
            callback(section, key, value)

    def get(self, section: str, key: str) -> Any:
        """Retrieve the current value of a tunable field.

        Args:
            section: The configuration section.
            key: The key within the section.

        Returns:
            The current value of the tunable field.

        Raises:
            KeyError: If the field is not registered.
        """
        field_key = f"{section}.{key}"
        if field_key not in self._fields:
            raise KeyError(f"Tunable field '{field_key}' is not registered")
        return self._fields[field_key].current_value

    def list_tunable(self) -> list[TunableField]:
        """Return all registered tunable fields.

        Returns:
            A list of all tunable field descriptors.
        """
        return list(self._fields.values())

    def add_listener(self, section: str, key: str, callback: Callable[..., Any]) -> None:
        """Register a callback to be invoked when a tunable field changes.

        Args:
            section: The configuration section.
            key: The key within the section.
            callback: A callable invoked with ``(section, key, new_value)``.
        """
        field_key = f"{section}.{key}"
        self._listeners[field_key].append(callback)
