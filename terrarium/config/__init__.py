"""Configuration system for the Terrarium framework.

Provides layered TOML-based configuration loading, Pydantic schema models,
a runtime registry for configuration access, tunable field management,
and cross-section validation.

Re-exports the primary public API surface::

    from terrarium.config import ConfigLoader, TerrariumConfig, ConfigRegistry
"""

from terrarium.config.loader import ConfigLoader
from terrarium.config.registry import ConfigRegistry
from terrarium.config.schema import TerrariumConfig
from terrarium.config.tunable import TunableField, TunableRegistry
from terrarium.config.validation import ConfigValidator

__all__ = [
    "ConfigLoader",
    "ConfigRegistry",
    "ConfigValidator",
    "TerrariumConfig",
    "TunableField",
    "TunableRegistry",
]
