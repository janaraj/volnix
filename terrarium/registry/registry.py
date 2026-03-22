"""Central engine registry for the Terrarium framework.

Provides registration, lookup, protocol resolution, and topological
ordering of engines for initialisation.
"""

from __future__ import annotations

import logging
from typing import Any

from terrarium.core.engine import BaseEngine
from terrarium.core.errors import EngineDependencyError
from terrarium.core.protocols import PipelineStep

logger = logging.getLogger(__name__)


class EngineRegistry:
    """Central registry of all engine instances.

    Supports lookup by name, protocol-based resolution, and dependency-
    aware initialisation ordering via topological sort.
    """

    def __init__(self) -> None:
        self._engines: dict[str, BaseEngine] = {}

    def register(self, engine: BaseEngine) -> None:
        """Register an engine instance.

        Args:
            engine: The engine to register.  Its ``engine_name`` is used as the key.
        """
        if not engine.engine_name:
            raise ValueError("Engine must have a non-empty engine_name")
        self._engines[engine.engine_name] = engine

    def get(self, engine_name: str) -> BaseEngine:
        """Retrieve a registered engine by name.

        Args:
            engine_name: The canonical engine name.

        Returns:
            The :class:`BaseEngine` instance.

        Raises:
            KeyError: If no engine is registered under *engine_name*.
        """
        if engine_name not in self._engines:
            available = sorted(self._engines.keys())
            raise KeyError(
                f"Engine '{engine_name}' not registered. "
                f"Available: {available}"
            )
        return self._engines[engine_name]

    def get_step(self, step_name: str) -> PipelineStep | None:
        """Retrieve a pipeline step by name, if one is registered.

        Args:
            step_name: The canonical step name.

        Returns:
            The :class:`PipelineStep` instance, or ``None`` if not found.
        """
        for engine in self._engines.values():
            if isinstance(engine, PipelineStep) and engine.step_name == step_name:
                return engine
        return None

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
        engine = self.get(engine_name)
        if not isinstance(engine, protocol_type):
            raise TypeError(
                f"Engine '{engine_name}' ({type(engine).__name__}) does not "
                f"satisfy protocol {protocol_type.__name__}"
            )
        return engine

    def get_pipeline_steps(self) -> dict[str, PipelineStep]:
        """Collect all engines implementing PipelineStep into a dict for the pipeline builder."""
        steps: dict[str, PipelineStep] = {}
        for engine in self._engines.values():
            if isinstance(engine, PipelineStep):
                steps[engine.step_name] = engine
        return steps

    def resolve_initialization_order(self) -> list[str]:
        """Compute a topological ordering of engines for initialisation.

        Uses the ``dependencies`` class variable of each engine to determine
        the correct start-up order.

        Returns:
            An ordered list of engine names (dependencies first).
        """
        in_degree: dict[str, int] = {name: 0 for name in self._engines}
        dependents: dict[str, list[str]] = {name: [] for name in self._engines}

        for name, engine in self._engines.items():
            for dep in engine.dependencies:
                if dep not in self._engines:
                    raise EngineDependencyError(
                        message=f"Engine '{name}' depends on '{dep}', which is not registered. "
                                f"Available: {sorted(self._engines.keys())}",
                        engine_name=name,
                    )
                dependents[dep].append(name)
                in_degree[name] += 1

        queue = sorted(n for n, d in in_degree.items() if d == 0)
        order: list[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for dependent in sorted(dependents[node]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
            queue.sort()

        if len(order) != len(self._engines):
            remaining = sorted(n for n in self._engines if n not in order)
            raise EngineDependencyError(
                message=f"Circular dependency detected among engines: {remaining}",
                engine_name=remaining[0] if remaining else "",
            )

        return order

    def list_engines(self) -> list[str]:
        """Return the names of all registered engines.

        Returns:
            A list of engine name strings.
        """
        return list(self._engines.keys())
