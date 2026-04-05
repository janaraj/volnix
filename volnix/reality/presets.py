"""Reality presets -- ideal, messy, hostile.

Each preset defines default labels for all five world-condition dimensions.
Built-in presets live in ``volnix/presets/``. User presets in ``~/.volnix/presets/``.
The label system resolves labels to full attribute values.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from volnix.core.errors import InvalidPresetError
from volnix.core.types import RealityPreset
from volnix.paths import list_presets, official_presets_dir, resolve_preset
from volnix.reality.dimensions import WorldConditions
from volnix.reality.labels import resolve_dimension, resolve_label

_PRESETS_DIR = official_presets_dir()


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

    Checks user presets (``~/.volnix/presets/``) first, then
    built-in presets (``volnix/presets/``).

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
    resolved = resolve_preset(preset)
    if resolved:
        return resolved
    available = [p["name"] for p in list_presets()]
    raise InvalidPresetError(
        f"Unknown preset: {preset!r}. Available: {available}",
        context={"preset": preset},
    )


def load_compiler_preset(name: str) -> dict[str, Any]:
    """Load a compiler preset YAML file (ideal, messy, hostile, or custom).

    Compiler presets are merged into the same file as reality presets.
    The ``compiler:`` section contains behavior, fidelity, mode, animator.

    Parameters
    ----------
    name:
        Preset name (e.g. ``"messy"``). Resolved via
        ``resolve_preset()`` (user → built-in).

    Returns
    -------
    dict:
        The compiler settings dict (has ``"compiler"`` top-level key).

    Raises
    ------
    InvalidPresetError:
        If no preset exists with that name.
    """
    resolved = resolve_preset(name)
    if not resolved:
        available = [p["name"] for p in list_presets()]
        raise InvalidPresetError(
            f"Unknown compiler preset: {name!r}. Available: {available}",
            context={"preset": name},
        )
    data = yaml.safe_load(resolved.read_text()) or {}
    # Return the compiler section; wrap if needed for backward compat
    if "compiler" in data:
        return data
    return {"compiler": data}
