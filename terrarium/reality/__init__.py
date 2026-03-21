"""Reality system -- world conditions that shape generated environments.

Reality presets define what kind of world agents live in.  Conditions are
compilation-time: they shape world data, not runtime behaviour.  Five
universal dimensions apply to any domain.

Re-exports the primary public API surface::

    from terrarium.reality import RealityPreset, WorldConditions, ConditionExpander
"""

from terrarium.reality.presets import RealityPreset
from terrarium.reality.dimensions import WorldConditions
from terrarium.reality.expander import ConditionExpander
from terrarium.reality.overlays import OverlayRegistry
from terrarium.reality.seeds import SeedProcessor
from terrarium.reality.config import RealityConfig

__all__ = [
    "RealityPreset",
    "WorldConditions",
    "ConditionExpander",
    "OverlayRegistry",
    "SeedProcessor",
    "RealityConfig",
]
