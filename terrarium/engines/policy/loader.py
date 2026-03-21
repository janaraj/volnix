"""Policy definition loader -- YAML files, world defs, and built-in templates."""

from __future__ import annotations

from typing import Any

from terrarium.engines.policy.templates import PolicyTemplate


class PolicyLoader:
    """Loads policy definitions from various sources."""

    def load_from_yaml(self, yaml_path: str) -> list[dict[str, Any]]:
        """Load policy definitions from a YAML file."""
        ...

    def load_from_world_def(self, world_def: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract policy definitions from a compiled world definition."""
        ...

    def load_builtin_templates(self) -> list[PolicyTemplate]:
        """Load all built-in policy templates shipped with the engine."""
        ...
