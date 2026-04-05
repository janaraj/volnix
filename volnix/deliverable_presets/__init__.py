"""Deliverable preset loader.

Each preset is a YAML file defining a schema and prompt instructions
for a specific type of deliverable that a lead actor can produce at
the end of a collaborative session.

Available presets: synthesis, decision, recommendation, prediction,
brainstorm, assessment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PRESETS_DIR = Path(__file__).parent

# Cache loaded presets to avoid repeated disk I/O
_cache: dict[str, dict[str, Any]] = {}

AVAILABLE_PRESETS: tuple[str, ...] = (
    "synthesis",
    "decision",
    "recommendation",
    "prediction",
    "brainstorm",
    "assessment",
)


def load_preset(name: str) -> dict[str, Any]:
    """Load a deliverable preset by name.

    Returns a dict with keys: name, description, schema,
    prompt_instructions.

    Raises ``FileNotFoundError`` if the preset YAML does not exist.
    Raises ``ValueError`` if the YAML is malformed or missing
    required keys.
    """
    if name in _cache:
        return _cache[name]

    path = _PRESETS_DIR / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(AVAILABLE_PRESETS)
        raise FileNotFoundError(
            f"Deliverable preset '{name}' not found. "
            f"Available presets: {available}"
        )

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"Preset '{name}' YAML must be a mapping, got {type(data).__name__}"
        )

    required_keys = {"name", "description", "schema", "prompt_instructions"}
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(
            f"Preset '{name}' missing required keys: {', '.join(sorted(missing))}"
        )

    _cache[name] = data
    return data


def list_presets() -> list[dict[str, str]]:
    """Return summary info for all available presets.

    Each entry has 'name' and 'description' keys.
    """
    result = []
    for name in AVAILABLE_PRESETS:
        try:
            preset = load_preset(name)
            result.append({
                "name": preset["name"],
                "description": preset["description"],
            })
        except (FileNotFoundError, ValueError):
            continue
    return result
