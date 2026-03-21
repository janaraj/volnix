"""Central engine registry for the Terrarium framework.

Provides registration, lookup, protocol resolution, and topological
ordering of engines for initialisation.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.engine import BaseEngine
from terrarium.core.protocols import PipelineStep


class EngineRegistry:
    """Central registry of all engine instances.

    Supports lookup by name, protocol-based resolution, and dependency-
    aware initialisation ordering via topological sort.
    """

    def __init__(self) -> None:
        ...

    def register(self, engine: BaseEngine) -> None:
        """Register an engine instance.

        Args:
            engine: The engine to register.  Its ``engine_name`` is used as the key.
        """
        ...

    def get(self, engine_name: str) -> BaseEngine:
        """Retrieve a registered engine by name.

        Args:
            engine_name: The canonical engine name.

        Returns:
            The :class:`BaseEngine` instance.

        Raises:
            KeyError: If no engine is registered under *engine_name*.
        """
        ...

    def get_step(self, step_name: str) -> PipelineStep | None:
        """Retrieve a pipeline step by name, if one is registered.

        Args:
            step_name: The canonical step name.

        Returns:
            The :class:`PipelineStep` instance, or ``None`` if not found.
        """
        ...

    def get_protocol(self, engine_name: str, protocol_type: type) -> Any:
        """Retrieve an engine and verify it satisfies a protocol.

        Args:
            engine_name: The canonical engine name.
            protocol_type: The protocol type to check against.

        Returns:
            The engine instance, verified as implementing *protocol_type*.

        Raises:
            TypeError: If the engine does not satisfy the protocol.
        """
        ...

    def resolve_initialization_order(self) -> list[str]:
        """Compute a topological ordering of engines for initialisation.

        Uses the ``dependencies`` class variable of each engine to determine
        the correct start-up order.

        Returns:
            An ordered list of engine names (dependencies first).
        """
        ...

    def list_engines(self) -> list[str]:
        """Return the names of all registered engines.

        Returns:
            A list of engine name strings.
        """
        ...
