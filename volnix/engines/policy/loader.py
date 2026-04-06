"""Policy definition loader -- YAML files, world defs, and built-in templates."""

from __future__ import annotations

from typing import Any

from volnix.engines.policy.templates import PolicyTemplate


class PolicyLoader:
    """Loads policy definitions from various sources."""

    def load_from_yaml(self, yaml_path: str) -> list[dict[str, Any]]:
        """Load policy definitions from a YAML file."""
        from pathlib import Path

        import yaml

        path = Path(yaml_path)
        if not path.exists():
            return []

        with open(path) as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            return data.get("policies", [])
        if isinstance(data, list):
            return data
        return []

    def load_from_world_def(self, world_def: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract policy definitions from a compiled world definition."""
        return world_def.get("policies", [])

    def load_from_plan(self, plan: Any) -> list[dict[str, Any]]:
        """Extract policy definitions from a WorldPlan object."""
        if hasattr(plan, "policies"):
            return list(plan.policies)
        return []

    def load_builtin_templates(self) -> list[PolicyTemplate]:
        """Load all built-in policy templates shipped with the engine."""
        return []
