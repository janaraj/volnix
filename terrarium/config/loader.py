"""Layered TOML configuration loader for the Terrarium framework.

Loads configuration from multiple layers (base, environment-specific, local
overrides, environment variables) and resolves cross-references before
producing a validated :class:`~terrarium.config.schema.TerrariumConfig`.
"""

from __future__ import annotations

import os
import tomllib
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
        self._base_dir = base_dir or Path.cwd()
        self._env = env

    def load(self) -> TerrariumConfig:
        """Load, merge, and validate all configuration layers.

        Returns:
            A fully resolved and validated :class:`TerrariumConfig`.
        """
        config: dict[str, Any] = {}

        # Layer 1: base config
        base_path = self._base_dir / "terrarium.toml"
        if base_path.is_file():
            config = self._load_toml(base_path)

        # Layer 2: environment-specific overrides
        env_path = self._base_dir / f"terrarium.{self._env}.toml"
        if env_path.is_file():
            env_config = self._load_toml(env_path)
            config = self._deep_merge(config, env_config)

        # Layer 3: local overrides
        local_path = self._base_dir / "terrarium.local.toml"
        if local_path.is_file():
            local_config = self._load_toml(local_path)
            config = self._deep_merge(config, local_config)

        # Layer 4: environment variable overrides
        config = self._apply_env_overrides(config)

        # Layer 5: resolve secure refs
        config = self._resolve_refs(config)

        # Layer 6: default data paths to ~/.terrarium/data/ (if not overridden)
        config = self._apply_user_data_defaults(config)

        return TerrariumConfig.model_validate(config)

    @staticmethod
    def _load_toml(path: Path) -> dict[str, Any]:
        """Load a TOML file and return its contents as a dictionary.

        Args:
            path: Path to the TOML file.

        Returns:
            The parsed TOML dictionary.
        """
        with open(path, "rb") as f:
            return tomllib.load(f)

    @staticmethod
    def _apply_user_data_defaults(config: dict[str, Any]) -> dict[str, Any]:
        """Set default data paths to ``~/.terrarium/data/`` if not overridden.

        Only applies when no explicit path was set by TOML layers or env vars.
        Development overrides (e.g. ``./dev_data/``) take precedence.
        """
        from terrarium.paths import user_data_dir

        data_dir = user_data_dir()
        defaults = {
            ("persistence", "base_dir"): str(data_dir),
            ("state", "db_path"): str(data_dir / "state.db"),
            ("state", "snapshot_dir"): str(data_dir / "snapshots"),
            ("runs", "data_dir"): str(data_dir / "runs"),
            ("worlds", "data_dir"): str(data_dir / "worlds"),
            ("bus", "db_path"): str(data_dir / "bus.db"),
            ("ledger", "db_path"): str(data_dir / "ledger.db"),
        }
        for (section, key), default_val in defaults.items():
            config.setdefault(section, {}).setdefault(key, default_val)
        return config

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge *override* into *base*, returning a new dict.

        Args:
            base: The base configuration dictionary.
            override: The overriding configuration dictionary.

        Returns:
            A new merged dictionary.
        """
        merged = dict(base)
        for key, value in override.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = ConfigLoader._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _apply_env_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply environment-variable overrides to the configuration dict.

        Environment variables are expected in the form
        ``TERRARIUM__section__key=value``.

        Args:
            config: The configuration dictionary to augment.

        Returns:
            The configuration dictionary with env overrides applied.
        """
        prefix = "TERRARIUM__"
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix):
                parts = env_key[len(prefix) :].lower().split("__")
                if parts:
                    self._set_nested(config, parts, env_value)
        return config

    def _resolve_refs(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve secure ``*_ref`` fields from environment variables.

        Any field ending in ``_ref`` whose value is a non-empty string will be
        looked up as an environment variable. If the env var exists, a
        corresponding field without the ``_ref`` suffix is set to its value.
        If the env var does not exist, the ref is left as-is.

        Args:
            config: The configuration dictionary containing potential refs.

        Returns:
            The configuration dictionary with all refs resolved.
        """
        return self._resolve_refs_recursive(config)

    @staticmethod
    def _resolve_refs_recursive(config: dict[str, Any]) -> dict[str, Any]:
        """Recursively walk the config dict resolving *_ref fields."""
        result = dict(config)
        for key, value in list(result.items()):
            if isinstance(value, dict):
                result[key] = ConfigLoader._resolve_refs_recursive(value)
            elif isinstance(key, str) and key.endswith("_ref") and isinstance(value, str) and value:
                resolved_key = key[: -len("_ref")]
                env_val = os.environ.get(value)
                if env_val is not None:
                    result[resolved_key] = env_val
        return result

    @staticmethod
    def _coerce(value: str) -> Any:
        """Coerce a string value from an env var to its appropriate Python type.

        Args:
            value: The raw string value.

        Returns:
            The coerced value (bool, int, float, or str).
        """
        # Check int/float BEFORE boolean to avoid "0"→False, "1"→True
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        if value.lower() in ("true", "yes", "on"):
            return True
        if value.lower() in ("false", "no", "off"):
            return False
        return value

    @staticmethod
    def _set_nested(config: dict[str, Any], keys: list[str], value: str) -> None:
        """Set a value at a nested key path within a configuration dict.

        Args:
            config: The configuration dictionary to modify in place.
            keys: The key path as a list of string segments.
            value: The value to set.
        """
        current = config
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = ConfigLoader._coerce(value)
