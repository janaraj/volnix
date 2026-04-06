"""ReplayLog -- records all decisions for exact replay.

In record mode: saves every LLM prompt/output and pipeline result.
In replay mode: returns recorded LLM output instead of calling LLM.

Uses asyncio.to_thread for file I/O (non-blocking).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ReplayEntry(BaseModel, frozen=True):
    """Records everything needed for exact replay of one action."""

    logical_time: float
    envelope_id: str
    actor_id: str
    activation_reason: str
    activation_tier: int
    llm_prompt: str | None = None
    llm_output: str | None = None
    pipeline_result_event_id: str | None = None
    actor_state_after: dict[str, Any] | None = None


class ReplayLog:
    """Records all decisions for exact replay. JSON lines format."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._entries: list[ReplayEntry] = []
        self._replay_mode = False
        self._replay_index: dict[tuple[float, str], str] = {}  # (time, actor_id) -> llm_output

    async def record(self, entry: ReplayEntry) -> None:
        """Record an entry. If path is set, also append to file."""
        self._entries.append(entry)
        if self._path:
            line = entry.model_dump_json() + "\n"
            await asyncio.to_thread(self._append_line, line)

    def _append_line(self, line: str) -> None:
        """Append a single JSON line to the replay file. Called via to_thread."""
        if self._path:
            with open(self._path, "a") as f:
                f.write(line)

    def replay_mode(self) -> bool:
        """Return whether the log is in replay mode."""
        return self._replay_mode

    def enable_replay(self, entries: list[ReplayEntry]) -> None:
        """Switch to replay mode with pre-loaded entries."""
        self._replay_mode = True
        self._entries = list(entries)
        self._replay_index = {
            (e.logical_time, e.actor_id): e.llm_output for e in entries if e.llm_output is not None
        }

    async def get_recorded_output(self, logical_time: float, actor_id: str) -> str | None:
        """In replay mode, return the recorded LLM output for the given time/actor."""
        return self._replay_index.get((logical_time, actor_id))

    def get_entries(self) -> list[ReplayEntry]:
        """Return a copy of all recorded entries."""
        return list(self._entries)

    def clear(self) -> None:
        """Clear all in-memory entries and replay index."""
        self._entries.clear()
        self._replay_index.clear()
        self._replay_mode = False
