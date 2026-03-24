"""Snapshot management for evaluation runs.

The :class:`SnapshotManager` creates, restores, and lists point-in-time
snapshots of world state within a run.  Supports both explicit and
automatic (interval-based) snapshotting.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.types import RunId, SnapshotId
from terrarium.persistence import ConnectionManager
from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.snapshot import SnapshotStore
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
        self._snapshot_store: SnapshotStore | None = None
        self._tick_counter: dict[str, int] = {}

    def _get_store(self) -> SnapshotStore:
        """Lazy-init SnapshotStore using the runs data_dir."""
        if self._snapshot_store is None:
            self._snapshot_store = SnapshotStore(
                PersistenceConfig(base_dir=self._config.data_dir)
            )
        return self._snapshot_store

    async def take_snapshot(self, run_id: RunId, label: str, tick: int) -> SnapshotId:
        """Create a named snapshot of the current world state."""
        store = self._get_store()
        db = await self._persistence.get_connection("state")
        snapshot_id = await store.save_snapshot(run_id, f"{label}_t{tick}", db)
        self._tick_counter[str(run_id)] = tick
        return snapshot_id

    async def restore_snapshot(self, snapshot_id: SnapshotId) -> None:
        """Restore world state to a previously taken snapshot."""
        store = self._get_store()
        await store.load_snapshot(snapshot_id)

    async def list_snapshots(self, run_id: RunId) -> list[dict]:
        """List all snapshots for a given run, ordered by tick."""
        store = self._get_store()
        return await store.list_snapshots(run_id=run_id)

    async def auto_snapshot(self, run_id: RunId, tick: int) -> SnapshotId | None:
        """Conditionally take an automatic snapshot based on the configured interval."""
        interval = self._config.snapshot_interval_ticks
        if interval <= 0:
            return None
        last = self._tick_counter.get(str(run_id), 0)
        if tick - last >= interval:
            return await self.take_snapshot(run_id, "auto", tick)
        return None
