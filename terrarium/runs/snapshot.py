"""Snapshot management for evaluation runs.

The :class:`SnapshotManager` creates, restores, and lists point-in-time
snapshots of world state within a run.  Supports both explicit and
automatic (interval-based) snapshotting.
"""

from __future__ import annotations

from terrarium.core.types import RunId, SnapshotId
from terrarium.persistence import ConnectionManager
from terrarium.runs.config import RunConfig


class SnapshotManager:
    """Manages point-in-time snapshots within evaluation runs.

    Args:
        config: Run configuration settings.
        persistence: Database connection manager.
    """

    def __init__(self, config: RunConfig, persistence: ConnectionManager) -> None:
        self._config = config
        self._persistence = persistence

    async def take_snapshot(self, run_id: RunId, label: str, tick: int) -> SnapshotId:
        """Create a named snapshot of the current world state.

        Args:
            run_id: The run this snapshot belongs to.
            label: Human-readable label for the snapshot.
            tick: The logical tick at the time of snapshot.

        Returns:
            The unique :class:`SnapshotId` for the new snapshot.
        """
        ...

    async def restore_snapshot(self, snapshot_id: SnapshotId) -> None:
        """Restore world state to a previously taken snapshot.

        Args:
            snapshot_id: The snapshot to restore.
        """
        ...

    async def list_snapshots(self, run_id: RunId) -> list[dict]:
        """List all snapshots for a given run.

        Args:
            run_id: The run whose snapshots to list.

        Returns:
            A list of snapshot metadata dicts, ordered by tick.
        """
        ...

    async def auto_snapshot(self, run_id: RunId, tick: int) -> SnapshotId | None:
        """Conditionally take an automatic snapshot based on the configured interval.

        Args:
            run_id: The current run.
            tick: The current logical tick.

        Returns:
            The :class:`SnapshotId` if a snapshot was taken, or ``None``.
        """
        ...
