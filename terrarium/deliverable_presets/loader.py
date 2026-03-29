"""Load deliverable presets from YAML files.

Each preset defines a JSON schema and prompt instructions for the lead
actor to produce a structured deliverable at the end of a collaboration.
Presets are generic — adding a new one is just creating a YAML file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PRESETS_DIR = Path(__file__).parent


def load_preset(preset_name: str) -> dict[str, Any] | None:
    """Load a deliverable preset by name.

    Returns dict with ``name``, ``description``, ``schema``,
    ``prompt_instructions``.  Returns ``None`` if not found.
    """
    path = PRESETS_DIR / f"{preset_name}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text())


def list_presets() -> list[str]:
    """List available preset names."""
    return sorted(
        p.stem for p in PRESETS_DIR.glob("*.yaml")
    )
