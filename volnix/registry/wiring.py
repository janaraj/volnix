"""Engine wiring and dependency injection for the Volnix framework.

Provides utilities for connecting engines to the event bus, injecting
inter-engine dependencies, and initialising the full engine graph.
"""

from __future__ import annotations

import logging

from volnix.core.engine import BaseEngine
from volnix.config.schema import VolnixConfig
from volnix.registry.registry import EngineRegistry

logger = logging.getLogger(__name__)


async def wire_engines(
    registry: EngineRegistry,
    bus: object,
    config: VolnixConfig,
    engine_overrides: dict[str, dict] | None = None,
) -> None:
    """Wire all registered engines with the event bus and configuration.

    Initialises engines in dependency order, injecting the bus and
    engine-specific configuration into each.

    Args:
        registry: The engine registry containing all engines to wire.
        bus: The shared event bus instance.
        config: The root Volnix configuration.
        engine_overrides: Optional per-engine config overrides (e.g.,
            injected dependencies like ``{"state": {"_db": db_instance}}``).
    """
    overrides = engine_overrides or {}
    order = registry.resolve_initialization_order()
    for engine_name in order:
        engine = registry.get(engine_name)
        config_obj = getattr(config, engine_name, None)
        engine_config = config_obj.model_dump() if config_obj is not None else {}
        # Merge any overrides (e.g., injected DB instances)
        if engine_name in overrides:
            engine_config.update(overrides[engine_name])
        await engine.initialize(engine_config, bus)
        await inject_dependencies(engine, registry)
        await engine.start()


async def shutdown_engines(
    registry: EngineRegistry,
) -> None:
    """Shut down all registered engines in reverse dependency order.

    Args:
        registry: The engine registry containing all engines to stop.
    """
    try:
        order = registry.resolve_initialization_order()
    except Exception as exc:
        logger.warning("Could not resolve shutdown order, falling back to unordered: %s", exc)
        order = registry.list_engines()
    for engine_name in reversed(order):
        engine = registry.get(engine_name)
        try:
            await engine.stop()
            logger.info("Engine '%s' stopped", engine_name)
        except Exception:
            logger.exception("Failed to stop engine '%s'", engine_name)


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
    resolved = {}
    for dep_name in engine.dependencies:
        resolved[dep_name] = registry.get(dep_name)
    engine._dependencies = resolved
