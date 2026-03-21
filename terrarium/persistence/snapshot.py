"""Snapshot storage for world state.

SnapshotStore manages the creation, retrieval, listing, and deletion
of point-in-time snapshots of Terrarium world databases.
"""

from __future__ import annotations

from terrarium.core.types import RunId, SnapshotId

from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.database import Database


class SnapshotStore:
    """Manages point-in-time snapshots of world state databases.

    Parameters:
        config: Persistence configuration controlling storage location
                and related settings.
    """

    def __init__(self, config: PersistenceConfig) -> None:
        ...

    async def save_snapshot(self, run_id: RunId, label: str, db: Database) -> SnapshotId:
        """Create a snapshot of the given database.

        Args:
            run_id: The run this snapshot belongs to.
            label: Human-readable label for the snapshot.
            db: The database to snapshot.

        Returns:
            The unique identifier for the created snapshot.
        """
        ...

    async def load_snapshot(self, snapshot_id: SnapshotId) -> Database:
        """Load a previously saved snapshot as a database.

        Args:
            snapshot_id: Identifier of the snapshot to load.

        Returns:
            A :class:`Database` instance backed by the snapshot data.
        """
        ...

    async def list_snapshots(self, run_id: RunId | None = None) -> list[dict]:
        """List available snapshots with metadata.

        Args:
            run_id: If provided, only list snapshots for this run.

        Returns:
            List of dicts containing snapshot metadata.
        """
        ...

    async def delete_snapshot(self, snapshot_id: SnapshotId) -> None:
        """Delete a snapshot and free its storage.

        Args:
            snapshot_id: Identifier of the snapshot to delete.
        """
        ...

    async def get_snapshot_metadata(self, snapshot_id: SnapshotId) -> dict:
        """Retrieve metadata for a specific snapshot.

        Args:
            snapshot_id: Identifier of the snapshot.

        Returns:
            Dict containing snapshot metadata (run_id, label, timestamp,
            size, etc.).
        """
        ...
