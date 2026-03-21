"""Engine wiring and dependency injection for the Terrarium framework.

Provides utilities for connecting engines to the event bus, injecting
inter-engine dependencies, and initialising the full engine graph.
"""

from __future__ import annotations

from terrarium.core.engine import BaseEngine
from terrarium.config.schema import TerrariumConfig
from terrarium.registry.registry import EngineRegistry


async def wire_engines(
    registry: EngineRegistry,
    bus: object,
    config: TerrariumConfig,
) -> None:
    """Wire all registered engines with the event bus and configuration.

    Initialises engines in dependency order, injecting the bus and
    engine-specific configuration into each.

    Args:
        registry: The engine registry containing all engines to wire.
        bus: The shared event bus instance.
        config: The root Terrarium configuration.
    """
    ...


async def inject_dependencies(
    engine: BaseEngine,
    registry: EngineRegistry,
) -> None:
    """Inject inter-engine dependencies into a single engine.

    Resolves each name in the engine's ``dependencies`` class variable
    and makes the resolved engine available to the target.

    Args:
        engine: The engine to inject dependencies into.
        registry: The engine registry for dependency resolution.
    """
    ...
