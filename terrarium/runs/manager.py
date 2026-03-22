"""Run lifecycle manager.

The :class:`RunManager` handles creation, state transitions, and querying
of evaluation runs.  Each run is identified by a :class:`RunId` and
progresses through created -> running -> completed/failed states.
"""

from __future__ import annotations

from terrarium.core.types import RunId
from terrarium.persistence import ConnectionManager
from terrarium.runs.config import RunConfig


class RunManager:
    """Manages the lifecycle of evaluation runs.

    Args:
        config: Run configuration settings.
        persistence: Database connection manager.
    """

    def __init__(self, config: RunConfig, persistence: ConnectionManager) -> None:
        self._config = config
        self._persistence = persistence

    async def create_run(
        self,
        world_def: dict,
        config_snapshot: dict,
        mode: str = "governed",
        reality_preset: str = "messy",
        fidelity_mode: str = "auto",
    ) -> RunId:
        """Create a new run record and return its identifier.

        Args:
            world_def: The world definition used for this run.
            config_snapshot: Snapshot of the configuration at run creation.
            mode: World mode (governed or ungoverned).
            reality_preset: Reality preset applied to the world.
            fidelity_mode: Fidelity resolution mode.

        Returns:
            The unique :class:`RunId` for the new run.
        """
        ...

    async def start_run(self, run_id: RunId) -> None:
        """Transition a run from *created* to *running*.

        Args:
            run_id: The run to start.
        """
        ...

    async def complete_run(self, run_id: RunId, status: str = "completed") -> None:
        """Mark a run as completed.

        Args:
            run_id: The run to complete.
            status: Final status label (default ``"completed"``).
        """
        ...

    async def fail_run(self, run_id: RunId, error: str) -> None:
        """Mark a run as failed with an error message.

        Args:
            run_id: The run that failed.
            error: Human-readable error description.
        """
        ...

    async def get_run(self, run_id: RunId) -> dict | None:
        """Retrieve metadata for a single run.

        Args:
            run_id: The run to look up.

        Returns:
            Run metadata dict, or ``None`` if not found.
        """
        ...

    async def list_runs(self, limit: int = 50) -> list[dict]:
        """List recent runs, newest first.

        Args:
            limit: Maximum number of runs to return.

        Returns:
            A list of run metadata dicts.
        """
        ...

    async def get_active_run(self) -> RunId | None:
        """Return the currently active (running) run, if any.

        Returns:
            The :class:`RunId` of the active run, or ``None``.
        """
        ...
