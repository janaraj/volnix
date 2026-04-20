"""Shared utilities for the ``volnix.config`` package.

These are implementation details — do not import from outside
``volnix.config``. External consumers should use ``ConfigLoader``,
``ConfigBuilder``, or ``VolnixConfig.from_dict``.
"""

from __future__ import annotations

from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base``, returning a new dict.

    Lists (and other non-dict values) are replaced, not merged — TOML
    layers and ``ConfigBuilder`` section setters share this semantic.

    Args:
        base: The base configuration dictionary.
        override: The overriding configuration dictionary.

    Returns:
        A new merged dictionary (inputs are not mutated).
    """
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
