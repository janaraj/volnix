"""Plan reviewer -- formats, validates, and serialises world plans."""

from __future__ import annotations

from typing import Any


class PlanReviewer:
    """Formats, validates, and serialises world plans for human review."""

    def format_plan(self, world_plan: dict[str, Any]) -> str:
        """Format a world plan as a human-readable string."""
        ...

    def to_yaml(self, world_plan: dict[str, Any]) -> str:
        """Serialise a world plan to YAML."""
        ...

    def from_yaml(self, yaml_str: str) -> dict[str, Any]:
        """Deserialise a world plan from YAML."""
        ...

    def validate_plan(self, world_plan: dict[str, Any]) -> list[str]:
        """Validate a world plan, returning a list of error messages."""
        ...
