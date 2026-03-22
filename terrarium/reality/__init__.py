"""Reality system -- world conditions that shape generated environments.

Reality presets define what kind of world agents live in.  Conditions are
compilation-time: they shape world data, not runtime behaviour.  Five
universal dimensions apply to any domain.

Re-exports the primary public API surface::

    from terrarium.reality import ConditionExpander, load_preset, WorldConditions
"""

from terrarium.reality.config import RealityConfig
from terrarium.reality.dimensions import (
    BaseDimension,
    BoundaryDimension,
    ComplexityDimension,
    InformationQualityDimension,
    ReliabilityDimension,
    SocialFrictionDimension,
    WorldConditions,
)
from terrarium.reality.expander import ConditionExpander
from terrarium.reality.labels import (
    LABEL_SCALES,
    is_valid_label,
    label_to_intensity,
    resolve_dimension,
    resolve_label,
)
from terrarium.reality.overlays import Overlay, OverlayRegistry
from terrarium.reality.presets import load_from_yaml, load_preset
from terrarium.reality.seeds import Seed, SeedProcessor

__all__ = [
    # Dimensions
    "BaseDimension",
    "BoundaryDimension",
    "ComplexityDimension",
    "InformationQualityDimension",
    "ReliabilityDimension",
    "SocialFrictionDimension",
    "WorldConditions",
    # Expander
    "ConditionExpander",
    # Labels
    "LABEL_SCALES",
    "is_valid_label",
    "label_to_intensity",
    "resolve_dimension",
    "resolve_label",
    # Overlays
    "Overlay",
    "OverlayRegistry",
    # Presets
    "load_from_yaml",
    "load_preset",
    # Seeds
    "Seed",
    "SeedProcessor",
    # Config
    "RealityConfig",
]
