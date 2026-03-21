"""Run replay engine.

The :class:`RunReplayer` replays a completed run tick by tick,
supporting variable speed, pause/resume, and seeking to specific
ticks for debugging and analysis.
"""

from __future__ import annotations

from terrarium.core.types import RunId
from terrarium.persistence import ConnectionManager
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

    async def start_replay(self, run_id: RunId, speed: float = 1.0) -> None:
        """Begin replaying the specified run.

        Args:
            run_id: The run to replay.
            speed: Playback speed multiplier (1.0 = real time).
        """
        ...

    async def pause_replay(self) -> None:
        """Pause the current replay."""
        ...

    async def resume_replay(self) -> None:
        """Resume a paused replay."""
        ...

    async def seek_to_tick(self, tick: int) -> None:
        """Jump to a specific tick in the replay.

        Args:
            tick: The target tick number.
        """
        ...

    async def stop_replay(self) -> None:
        """Stop and reset the current replay."""
        ...

    async def get_replay_state(self) -> dict:
        """Return the current replay state.

        Returns:
            A dict with ``run_id``, ``tick``, ``paused``, ``speed``, and
            ``status`` keys.
        """
        ...
