"""Reality presets -- pristine, realistic, harsh.

Each preset defines default values for all five world-condition dimensions.
Preset data is stored in YAML files under ``reality/data/presets/``.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from terrarium.reality.dimensions import WorldConditions


class RealityPreset(enum.StrEnum):
    """Named reality presets."""

    PRISTINE = "pristine"    # Perfect world. Clean data, reliable services, no threats.
    REALISTIC = "realistic"  # The real world. Some noise, occasional failures, some threats.
    HARSH = "harsh"          # A bad day. Messy data, flaky services, frequent threats.


def load_preset(preset: RealityPreset) -> WorldConditions:
    """Load preset values from the bundled YAML data file.

    Parameters
    ----------
    preset:
        One of the built-in reality presets.

    Returns
    -------
    WorldConditions:
        Fully populated world conditions for the chosen preset.
    """
    ...


def load_preset_from_yaml(path: str) -> WorldConditions:
    """Load preset from a custom YAML file.

    Parameters
    ----------
    path:
        Filesystem path to a YAML file following the preset schema.

    Returns
    -------
    WorldConditions:
        World conditions parsed from the file.
    """
    ...
