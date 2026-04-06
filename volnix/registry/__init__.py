"""Engine registry and dependency injection for the Volnix framework.

Provides the central :class:`EngineRegistry` for registering and resolving
engines, wiring utilities for dependency injection, a composition root
for default setup, and a health aggregator.

Re-exports the primary public API surface::

    from volnix.registry import EngineRegistry, create_default_registry
"""

from volnix.registry.composition import create_default_registry
from volnix.registry.health import HealthAggregator
from volnix.registry.registry import EngineRegistry
from volnix.registry.wiring import inject_dependencies, shutdown_engines, wire_engines

__all__ = [
    "EngineRegistry",
    "HealthAggregator",
    "create_default_registry",
    "inject_dependencies",
    "shutdown_engines",
    "wire_engines",
]
