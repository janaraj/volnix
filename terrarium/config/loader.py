"""Layered TOML configuration loader for the Terrarium framework.

Loads configuration from multiple layers (base, environment-specific, local
overrides, environment variables) and resolves cross-references before
producing a validated :class:`~terrarium.config.schema.TerrariumConfig`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from terrarium.config.schema import TerrariumConfig


class ConfigLoader:
    """Loads and merges layered TOML configuration files.

    Layer order (later layers override earlier):
        1. ``base.toml`` -- shared defaults
        2. ``{env}.toml`` -- environment-specific overrides
        3. ``local.toml`` -- machine-local developer overrides (git-ignored)
        4. Environment variables (``TERRARIUM__section__key``)
        5. Cross-reference resolution (``${section.key}`` placeholders)
    """

    def __init__(self, base_dir: Path | None = None, env: str = "development") -> None:
        ...

    def load(self) -> TerrariumConfig:
        """Load, merge, and validate all configuration layers.

        Returns:
            A fully resolved and validated :class:`TerrariumConfig`.
        """
        ...

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge *override* into *base*, returning a new dict.

        Args:
            base: The base configuration dictionary.
            override: The overriding configuration dictionary.

        Returns:
            A new merged dictionary.
        """
        ...

    def _apply_env_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply environment-variable overrides to the configuration dict.

        Environment variables are expected in the form
        ``TERRARIUM__section__key=value``.

        Args:
            config: The configuration dictionary to augment.

        Returns:
            The configuration dictionary with env overrides applied.
        """
        ...

    def _resolve_refs(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve ``${section.key}`` cross-reference placeholders.

        Args:
            config: The configuration dictionary containing potential refs.

        Returns:
            The configuration dictionary with all refs resolved.
        """
        ...

    @staticmethod
    def _coerce(value: str) -> Any:
        """Coerce a string value from an env var to its appropriate Python type.

        Args:
            value: The raw string value.

        Returns:
            The coerced value (bool, int, float, or str).
        """
        ...

    @staticmethod
    def _set_nested(config: dict[str, Any], keys: list[str], value: str) -> None:
        """Set a value at a nested key path within a configuration dict.

        Args:
            config: The configuration dictionary to modify in place.
            keys: The key path as a list of string segments.
            value: The value to set.
        """
        ...
