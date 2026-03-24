"""Run replay engine.

The :class:`RunReplayer` replays a completed run tick by tick,
supporting variable speed, pause/resume, and seeking to specific
ticks for debugging and analysis.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.types import RunId
from terrarium.persistence import ConnectionManager
from terrarium.runs.artifacts import ArtifactStore
from terrarium.runs.config import RunConfig


class RunReplayer:
    """Replays a completed run at configurable speed.

    Args:
        config: Run configuration settings.
        persistence: Database connection manager.
    """

    def __init__(self, config: RunConfig, persistence: ConnectionManager) -> None:
        self._config = config
        self._persistence = persistence
        self._active_run_id: RunId | None = None
        self._paused: bool = False
        self._speed: float = 1.0
        self._current_tick: int = 0
        self._events: list[dict[str, Any]] = []
        self._artifact_store: ArtifactStore | None = None

    def _get_artifact_store(self) -> ArtifactStore:
        """Lazy-init ArtifactStore from config."""
        if self._artifact_store is None:
            self._artifact_store = ArtifactStore(self._config)
        return self._artifact_store

    async def start_replay(self, run_id: RunId, speed: float = 1.0) -> None:
        """Begin replaying the specified run."""
        store = self._get_artifact_store()
        events = await store.load_artifact(run_id, "event_log")
        self._events = events or []
        self._active_run_id = run_id
        self._current_tick = 0
        self._paused = False
        self._speed = speed

    async def pause_replay(self) -> None:
        """Pause the current replay."""
        self._paused = True

    async def resume_replay(self) -> None:
        """Resume a paused replay."""
        self._paused = False

    async def seek_to_tick(self, tick: int) -> None:
        """Jump to a specific tick in the replay."""
        self._current_tick = tick

    async def stop_replay(self) -> None:
        """Stop and reset the current replay."""
        self._active_run_id = None
        self._events = []
        self._current_tick = 0
        self._paused = False

    async def get_replay_state(self) -> dict:
        """Return the current replay state."""
        events_at_tick = [
            e for e in self._events
            if (e.get("tick", 0) if isinstance(e, dict) else 0) <= self._current_tick
        ]
        if self._active_run_id is None:
            status = "idle"
        elif self._paused:
            status = "paused"
        else:
            status = "replaying"
        return {
            "run_id": str(self._active_run_id) if self._active_run_id else None,
            "tick": self._current_tick,
            "paused": self._paused,
            "speed": self._speed,
            "status": status,
            "total_events": len(self._events),
            "events_at_tick": len(events_at_tick),
        }
