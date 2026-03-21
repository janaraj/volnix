"""Health aggregator for the Terrarium engine ecosystem.

Collects health-check results from all registered engines and provides
a unified system health view.
"""

from __future__ import annotations

from terrarium.registry.registry import EngineRegistry


class HealthAggregator:
    """Aggregates health-check results from all registered engines."""

    def __init__(self, registry: EngineRegistry) -> None:
        ...

    async def check_all(self) -> dict[str, dict]:
        """Run health checks on all registered engines.

        Returns:
            A dict mapping engine names to their health-check results.
        """
        ...

    async def check_engine(self, engine_name: str) -> dict:
        """Run a health check on a single engine.

        Args:
            engine_name: The name of the engine to check.

        Returns:
            The health-check result dict for the engine.
        """
        ...

    def is_healthy(self) -> bool:
        """Return whether all engines are considered healthy.

        Returns:
            ``True`` if every engine's last health check passed.
        """
        ...
