"""Configuration models for the reality system.

These Pydantic models map to the ``reality:`` section of the Volnix
compiler settings YAML.  Two-level config: each dimension can be overridden
with a label string OR a dict of per-attribute values.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from volnix.reality.seeds import Seed as SeedConfig  # noqa: F401 — re-export for back-compat


class RealityConfig(BaseModel):
    """Top-level reality configuration section.

    The ``preset`` field selects the base preset (ideal / messy / hostile).
    Each dimension field can be:
    - ``None`` -- use the preset default
    - A label string -- override with this label's default values
    - A dict of attribute values -- override with specific numbers
    """

    model_config = ConfigDict(frozen=True)

    preset: str = "messy"
    # Per-dimension overrides (label string or attribute dict)
    information: str | dict[str, Any] | None = None
    reliability: str | dict[str, Any] | None = None
    friction: str | dict[str, Any] | None = None
    complexity: str | dict[str, Any] | None = None
    boundaries: str | dict[str, Any] | None = None
    overlays: list[str] = Field(default_factory=list)
