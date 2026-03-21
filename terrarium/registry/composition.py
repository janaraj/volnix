"""Composition root for the Terrarium framework.

This is the **only** module that imports concrete engine classes.  All other
code depends on abstract protocols and the engine registry.
"""

from __future__ import annotations

from terrarium.registry.registry import EngineRegistry


def create_default_registry() -> EngineRegistry:
    """Create an :class:`EngineRegistry` pre-populated with default engines.

    This is the composition root -- the single place where concrete engine
    implementations are imported and instantiated.  All downstream code
    retrieves engines by name or protocol from the registry.

    Returns:
        A fully populated :class:`EngineRegistry` with the default engine set.
    """
    ...
