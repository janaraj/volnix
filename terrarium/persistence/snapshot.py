"""Snapshot storage for world state.

SnapshotStore manages the creation, retrieval, listing, and deletion
of point-in-time snapshots of Terrarium world databases.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from terrarium.core.types import RunId, SnapshotId
from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.database import Database
from terrarium.persistence.sqlite import SQLiteDatabase


class SnapshotStore:
    """Manages point-in-time snapshots of world state databases.

    Parameters:
        config: Persistence configuration controlling storage location
                and related settings.
    """

    def __init__(self, config: PersistenceConfig) -> None:
        self._config = config
        self._snapshots_dir = Path(config.base_dir) / "snapshots"

    async def save_snapshot(self, run_id: RunId, label: str, db: Database) -> SnapshotId:
        """Create a snapshot of the given database.

        Args:
            run_id: The run this snapshot belongs to.
            label: Human-readable label for the snapshot.
            db: The database to snapshot.

        Returns:
            The unique identifier for the created snapshot.
        """
        await asyncio.to_thread(self._snapshots_dir.mkdir, parents=True, exist_ok=True)

        snapshot_id = SnapshotId(f"snap_{run_id}_{label}_{uuid4().hex[:8]}")
        db_file = self._snapshots_dir / f"{snapshot_id}.db"
        meta_file = self._snapshots_dir / f"{snapshot_id}.json"

        # Use the SQLite backup method if available
        if isinstance(db, SQLiteDatabase):
            await db.backup(str(db_file))
        else:
            raise TypeError("Only SQLiteDatabase instances support backup-based snapshots")

        stat_result = await asyncio.to_thread(db_file.stat)
        size = stat_result.st_size

        metadata = {
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "label": label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size,
        }
        await asyncio.to_thread(meta_file.write_text, json.dumps(metadata, indent=2))

        return snapshot_id

    async def load_snapshot(self, snapshot_id: SnapshotId) -> Database:
        """Load a previously saved snapshot as a database.

        Args:
            snapshot_id: Identifier of the snapshot to load.

        Returns:
            A :class:`Database` instance backed by the snapshot data.
        """
        db_file = self._snapshots_dir / f"{snapshot_id}.db"
        if not await asyncio.to_thread(db_file.exists):
            raise FileNotFoundError(f"Snapshot database not found: {db_file}")

        db = SQLiteDatabase(str(db_file), wal_mode=False)
        await db.connect()
        return db

    async def list_snapshots(self, run_id: RunId | None = None) -> list[dict]:
        """List available snapshots with metadata.

        Args:
            run_id: If provided, only list snapshots for this run.

        Returns:
            List of dicts containing snapshot metadata.
        """
        if not await asyncio.to_thread(self._snapshots_dir.exists):
            return []

        meta_files = await asyncio.to_thread(
            lambda: sorted(self._snapshots_dir.glob("*.json"))
        )
        results: list[dict] = []
        for meta_file in meta_files:
            text = await asyncio.to_thread(meta_file.read_text)
            metadata = json.loads(text)
            if run_id is not None and metadata.get("run_id") != run_id:
                continue
            results.append(metadata)
        return results

    async def delete_snapshot(self, snapshot_id: SnapshotId) -> None:
        """Delete a snapshot and free its storage.

        Args:
            snapshot_id: Identifier of the snapshot to delete.
        """
        db_file = self._snapshots_dir / f"{snapshot_id}.db"
        meta_file = self._snapshots_dir / f"{snapshot_id}.json"

        if await asyncio.to_thread(db_file.exists):
            await asyncio.to_thread(db_file.unlink)
        if await asyncio.to_thread(meta_file.exists):
            await asyncio.to_thread(meta_file.unlink)

    async def get_snapshot_metadata(self, snapshot_id: SnapshotId) -> dict:
        """Retrieve metadata for a specific snapshot.

        Args:
            snapshot_id: Identifier of the snapshot.

        Returns:
            Dict containing snapshot metadata (run_id, label, timestamp,
            size, etc.).
        """
        meta_file = self._snapshots_dir / f"{snapshot_id}.json"
        if not await asyncio.to_thread(meta_file.exists):
            raise FileNotFoundError(f"Snapshot metadata not found: {meta_file}")
        text = await asyncio.to_thread(meta_file.read_text)
        return json.loads(text)
