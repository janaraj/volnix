"""Run lifecycle manager.

The :class:`RunManager` handles creation, state transitions, and querying
of evaluation runs.  Each run is identified by a :class:`RunId` and
progresses through created -> running -> completed/failed states.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

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
        self._data_dir = Path(config.data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, dict[str, Any]] = {}
        self._active_run: str | None = None
        self._tags: dict[str, str] = {}
        self._load_existing_runs()

    async def create_run(
        self,
        world_def: dict,
        config_snapshot: dict,
        mode: str = "governed",
        reality_preset: str = "messy",
        fidelity_mode: str = "auto",
        tag: str | None = None,
    ) -> RunId:
        """Create a new run record and return its identifier."""
        run_id = RunId(f"run_{uuid4().hex[:12]}")
        self._runs[str(run_id)] = {
            "run_id": str(run_id),
            "status": "created",
            "mode": mode,
            "reality_preset": reality_preset,
            "fidelity_mode": fidelity_mode,
            "tag": tag,
            "created_at": datetime.now(UTC).isoformat(),
            "started_at": None,
            "completed_at": None,
            "world_def": world_def,
            "config_snapshot": config_snapshot,
        }
        if tag:
            self._tags[tag] = str(run_id)
        await asyncio.to_thread(self._save_run_metadata, run_id)
        return run_id

    async def start_run(self, run_id: RunId) -> None:
        """Transition a run from *created* to *running*."""
        run = self._get_or_raise(run_id)
        run["status"] = "running"
        run["started_at"] = datetime.now(UTC).isoformat()
        self._active_run = str(run_id)
        await asyncio.to_thread(self._save_run_metadata, run_id)

    async def complete_run(
        self,
        run_id: RunId,
        status: str = "completed",
        summary: dict[str, Any] | None = None,
    ) -> None:
        """Mark a run as completed, optionally storing run summary.

        Args:
            run_id: The run to complete.
            status: Final status (default: ``"completed"``).
            summary: Optional dict of computed summary fields to persist
                in metadata (event_count, current_tick, governance_score, etc.).
        """
        run = self._get_or_raise(run_id)
        run["status"] = status
        run["completed_at"] = datetime.now(UTC).isoformat()
        if summary:
            run["summary"] = summary
        if self._active_run == str(run_id):
            self._active_run = None
        await asyncio.to_thread(self._save_run_metadata, run_id)

    async def fail_run(self, run_id: RunId, error: str) -> None:
        """Mark a run as failed with an error message."""
        run = self._get_or_raise(run_id)
        run["status"] = "failed"
        run["error"] = error
        run["completed_at"] = datetime.now(UTC).isoformat()
        if self._active_run == str(run_id):
            self._active_run = None
        await asyncio.to_thread(self._save_run_metadata, run_id)

    async def get_run(self, run_id: RunId) -> dict | None:
        """Retrieve metadata for a single run. Resolves tags."""
        rid = self._resolve_id(run_id)
        return self._runs.get(rid)

    async def list_runs(self, limit: int = 50) -> list[dict]:
        """List recent runs, newest first."""
        runs = sorted(
            self._runs.values(),
            key=lambda r: r["created_at"],
            reverse=True,
        )
        return runs[:limit]

    async def get_active_run(self) -> RunId | None:
        """Return the currently active (running) run, if any."""
        if self._active_run:
            return RunId(self._active_run)
        return None

    # ── Private helpers ──────────────────────────────────────────

    def _resolve_id(self, run_id_or_tag: str | RunId) -> str:
        """Resolve tag → run_id, 'last' → most recent, or pass through."""
        s = str(run_id_or_tag)
        if s in self._tags:
            return self._tags[s]
        if s == "last":
            runs = sorted(
                self._runs.values(),
                key=lambda r: r["created_at"],
                reverse=True,
            )
            return runs[0]["run_id"] if runs else ""
        return s

    def _get_or_raise(self, run_id: RunId) -> dict:
        """Resolve and fetch a run, raising KeyError if not found."""
        rid = self._resolve_id(run_id)
        run = self._runs.get(rid)
        if run is None:
            raise KeyError(f"Run not found: {run_id}")
        return run

    def _save_run_metadata(self, run_id: RunId) -> None:
        """Persist run metadata to a JSON file on disk."""
        run_dir = self._data_dir / str(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        meta_path = run_dir / "metadata.json"
        meta_path.write_text(
            json.dumps(self._runs[str(run_id)], indent=2, default=str)
        )

    def _load_existing_runs(self) -> None:
        """Reload previously persisted runs from disk."""
        if not self._data_dir.exists():
            return
        for meta_path in self._data_dir.glob("*/metadata.json"):
            try:
                data = json.loads(meta_path.read_text())
                rid = data["run_id"]
                self._runs[rid] = data
                if data.get("tag"):
                    self._tags[data["tag"]] = rid
                if data.get("status") == "running":
                    self._active_run = rid
            except (json.JSONDecodeError, KeyError):
                continue
