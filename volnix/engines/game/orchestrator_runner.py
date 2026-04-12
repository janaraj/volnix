"""OrchestratorRunner — thin CLI adapter for the event-driven GameOrchestrator.

The CLI's runner protocol expects an object with:

- ``async run()`` that blocks until the game terminates and returns a
  result object with ``.reason`` and optional ``.winner`` attributes
- ``set_mission(mission)`` no-op method for compatibility with the
  ``SimulationRunner`` interface

:class:`GameOrchestrator` does not itself expose ``run()`` because it
lives in the event-driven world and is driven entirely by the bus —
``_on_start`` triggers the first activation, and the bus fanout drives
every subsequent move. The CLI, however, needs a blocking handle to
wait on until termination.

This wrapper is the narrow compatibility shim that lets us plug the
orchestrator into the existing CLI ``_setup_simulation`` / ``runner.run()``
flow without changing upstream code. It delegates to
:meth:`GameOrchestrator.await_result` which resolves when the
:class:`GameTerminatedEvent` is published.

Historical note: the legacy round-based ``volnix/game/runner.py`` and
the CLI's dual-runner detection were deleted in Cycle B.10. This file
is the event-driven replacement; it lives on indefinitely as the CLI
compatibility shim.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.engines.game.definition import GameResult
from volnix.engines.game.orchestrator import GameOrchestrator

logger = logging.getLogger(__name__)


class OrchestratorRunner:
    """Minimal CLI-compatible wrapper around :class:`GameOrchestrator`.

    Instances are cheap — the constructor just stores references; the
    orchestrator's lifecycle is already managed by the composition root
    (``wire_engines``) and configured by ``app.configure_game``.

    Attributes:
        _orchestrator: The configured :class:`GameOrchestrator` instance.
        _agency: The agency engine reference (passed by the CLI for
            symmetry with :class:`SimulationRunner`; currently unused
            here but kept for future hooks).
        _event_queue: The simulation event queue (unused in event-driven
            mode; kept so the CLI can continue passing it).
    """

    def __init__(
        self,
        orchestrator: GameOrchestrator,
        agency: Any,
        event_queue: Any | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._agency = agency
        self._event_queue = event_queue
        self._mission: str = ""

    def set_mission(self, mission: str) -> None:
        """Store the mission for logging (no runtime effect in event-driven mode).

        The orchestrator reads its game definition from ``configure()``,
        not from the mission string. This method exists purely so the
        CLI's ``runner.set_mission(...)`` call doesn't need a conditional.
        """
        self._mission = mission

    async def run(self) -> GameResult:
        """Block until the orchestrator publishes ``GameTerminatedEvent``.

        Returns:
            The :class:`GameResult` resolved by
            :meth:`GameOrchestrator.await_result`. The CLI formats it
            via ``_format_run_result`` (which reads ``.reason`` and
            ``.winner`` attributes).

        Raises:
            RuntimeError: If the orchestrator was never configured or
                never started (result future is None).
        """
        logger.info("OrchestratorRunner: awaiting game termination")
        result = await self._orchestrator.await_result()
        logger.info(
            "OrchestratorRunner: game terminated reason=%s winner=%s",
            result.reason,
            result.winner,
        )
        return result
