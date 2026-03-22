"""Reality presets -- ideal, messy, hostile.

Each preset defines default labels for all five world-condition dimensions.
Preset data is stored in YAML files under ``reality/data/presets/``.
The label system resolves labels to full attribute values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from terrarium.core.errors import InvalidPresetError
from terrarium.core.types import RealityPreset
from terrarium.reality.dimensions import WorldConditions
from terrarium.reality.labels import resolve_dimension, resolve_label

_PRESETS_DIR = Path(__file__).parent / "data" / "presets"
_COMPILER_PRESETS_DIR = Path(__file__).parent / "data" / "compiler_presets"


def load_preset(preset: RealityPreset | str) -> WorldConditions:
    """Load a built-in preset from YAML, resolve labels, return WorldConditions.

    Parameters
    ----------
    preset:
        One of the built-in reality presets (``"ideal"``, ``"messy"``,
        ``"hostile"``), or a :class:`RealityPreset` enum member.

    Returns
    -------
    WorldConditions:
        Fully populated world conditions for the chosen preset.

    Raises
    ------
    InvalidPresetError:
        If the preset name does not match a built-in YAML file.
    """
    name = preset.value if isinstance(preset, RealityPreset) else str(preset)
    path = _get_preset_path(name)
    return load_from_yaml(path)


def load_from_yaml(path: str | Path) -> WorldConditions:
    """Load conditions from a YAML file containing dimension labels or dicts.

    Parameters
    ----------
    path:
        Filesystem path to a YAML file.  Each top-level key should be a
        dimension name with either a label string or a dict of attribute
        values.

    Returns
    -------
    WorldConditions:
        World conditions parsed and resolved from the file.
    """
    yaml_path = Path(path)
    try:
        with yaml_path.open("r") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        raise InvalidPresetError(f"YAML file not found: {path}")
    except yaml.YAMLError as e:
        raise InvalidPresetError(f"Invalid YAML in {path}: {e}")

    dims: dict[str, Any] = {}
    for dim_name in ["information", "reliability", "friction", "complexity", "boundaries"]:
        value = data.get(dim_name)
        if value is None:
            continue
        if isinstance(value, str):
            dims[dim_name] = resolve_label(dim_name, value)
        elif isinstance(value, dict):
            dims[dim_name] = resolve_dimension(dim_name, value)
        else:
            dims[dim_name] = resolve_label(dim_name, str(value))

    return WorldConditions(**dims)


def _get_preset_path(preset: str) -> Path:
    """Resolve preset name to YAML file path.

    Parameters
    ----------
    preset:
        Preset name (e.g. ``"messy"``).

    Returns
    -------
    Path:
        Absolute path to the preset YAML file.

    Raises
    ------
    InvalidPresetError:
        If no YAML file exists for the preset name.
    """
    path = _PRESETS_DIR / f"{preset}.yaml"
    if not path.exists():
        raise InvalidPresetError(
            f"Unknown preset: {preset!r}. "
            f"Available: {[p.stem for p in _PRESETS_DIR.glob('*.yaml')]}",
            context={"preset": preset},
        )
    return path


def load_compiler_preset(name: str) -> dict[str, Any]:
    """Load a compiler preset YAML file (ideal, messy, hostile, or custom).

    Compiler presets combine: reality + behavior + fidelity + mode + animator.
    They provide complete compilation parameters for a given world character.

    Parameters
    ----------
    name:
        Preset name (e.g. ``"messy"``). Looks up in
        ``reality/data/compiler_presets/{name}.yaml``.

    Returns
    -------
    dict:
        The compiler settings dict (has ``"compiler"`` top-level key).

    Raises
    ------
    InvalidPresetError:
        If no compiler preset exists with that name.
    """
    path = _COMPILER_PRESETS_DIR / f"{name}.yaml"
    if not path.exists():
        available = [p.stem for p in _COMPILER_PRESETS_DIR.glob("*.yaml")]
        raise InvalidPresetError(
            f"Unknown compiler preset: {name!r}. Available: {available}",
            context={"preset": name},
        )
    return yaml.safe_load(path.read_text())
