"""Health aggregator for the Volnix engine ecosystem.

Collects health-check results from all registered engines and provides
a unified system health view.
"""

from __future__ import annotations

import logging

from volnix.registry.registry import EngineRegistry

logger = logging.getLogger(__name__)


class HealthAggregator:
    """Aggregates health-check results from all registered engines."""

    def __init__(self, registry: EngineRegistry) -> None:
        self._registry = registry
        self._last_results: dict[str, dict] = {}

    async def check_all(self) -> dict[str, dict]:
        """Run health checks on all registered engines.

        Returns:
            A dict mapping engine names to their health-check results.
        """
        results: dict[str, dict] = {}
        for name in self._registry.list_engines():
            engine = self._registry.get(name)
            try:
                results[name] = await engine.health_check()
            except Exception as exc:
                results[name] = {"engine": name, "started": False, "healthy": False, "error": str(exc)}
        self._last_results = results
        return results

    async def check_engine(self, engine_name: str) -> dict:
        """Run a health check on a single engine.

        Args:
            engine_name: The name of the engine to check.

        Returns:
            The health-check result dict for the engine.
        """
        engine = self._registry.get(engine_name)
        try:
            result = await engine.health_check()
        except Exception as exc:
            result = {"engine": engine_name, "started": False, "healthy": False, "error": str(exc)}
        self._last_results[engine_name] = result
        return result

    def is_healthy(self) -> bool:
        """Return whether all engines are considered healthy.

        Returns:
            ``True`` if every engine's last health check passed.
        """
        if not self._last_results:
            return False
        return all(r.get("healthy", False) for r in self._last_results.values())
