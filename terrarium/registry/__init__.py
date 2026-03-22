"""Engine registry and dependency injection for the Terrarium framework.

Provides the central :class:`EngineRegistry` for registering and resolving
engines, wiring utilities for dependency injection, a composition root
for default setup, and a health aggregator.

Re-exports the primary public API surface::

    from terrarium.registry import EngineRegistry, create_default_registry
"""

from terrarium.registry.composition import create_default_registry
from terrarium.registry.health import HealthAggregator
from terrarium.registry.registry import EngineRegistry
from terrarium.registry.wiring import inject_dependencies, shutdown_engines, wire_engines

__all__ = [
    "EngineRegistry",
    "HealthAggregator",
    "create_default_registry",
    "inject_dependencies",
    "shutdown_engines",
    "wire_engines",
]
