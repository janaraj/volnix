"""Artifact storage for evaluation runs.

The :class:`ArtifactStore` persists reports, scorecards, event logs,
and configuration snapshots associated with a run.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from volnix.core.types import RunId
from volnix.runs.config import RunConfig

_ALLOWED_ARTIFACT_TYPES = frozenset(
    {
        "report",
        "scorecard",
        "event_log",
        "config",
        "metadata",
        "captured_surface",
        "deliverable",
        "governance_report",
        "decision_trace",
    }
)


def _sanitize_name(name: str) -> str:
    """Strip path separators and traversal components from a name."""
    return name.replace("/", "").replace("\\", "").replace("..", "")


class ArtifactStore:
    """Stores and retrieves run artifacts (reports, scorecards, logs, configs).

    Args:
        config: Run configuration settings.
    """

    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._data_dir = Path(config.data_dir)

    async def save_report(self, run_id: RunId, report: dict) -> str:
        """Save a run report and return its storage path."""
        return await self._write_artifact(run_id, "report", report)

    async def save_scorecard(self, run_id: RunId, scorecard: dict) -> str:
        """Save a scorecard and return its storage path."""
        return await self._write_artifact(run_id, "scorecard", scorecard)

    async def save_event_log(self, run_id: RunId, events: list) -> str:
        """Save an event log and return its storage path."""
        serialized = [self._serialize_event(e) for e in events]
        return await self._write_artifact(run_id, "event_log", serialized)

    async def save_deliverable(self, run_id: RunId, deliverable: dict) -> str:
        """Save a deliverable artifact and return its storage path."""
        return await self._write_artifact(run_id, "deliverable", deliverable)

    async def save_config(self, run_id: RunId, config: dict) -> str:
        """Save a configuration snapshot and return its storage path."""
        return await self._write_artifact(run_id, "config", config)

    async def list_artifacts(self, run_id: RunId) -> list[dict]:
        """List all artifacts for a run."""
        run_dir = self._data_dir / str(run_id)
        exists = await asyncio.to_thread(run_dir.exists)
        if not exists:
            return []
        files = await asyncio.to_thread(lambda: sorted(run_dir.glob("*.json")))
        results: list[dict] = []
        for f in files:
            if f.stem == "metadata":
                continue
            stat = await asyncio.to_thread(f.stat)
            results.append(
                {
                    "type": f.stem,
                    "path": str(f),
                    "size_bytes": stat.st_size,
                }
            )
        return results

    async def load_artifact(self, run_id: RunId, artifact_type: str) -> Any:
        """Load a specific artifact by type."""
        if artifact_type not in _ALLOWED_ARTIFACT_TYPES:
            msg = f"Invalid artifact type: {artifact_type!r}"
            raise ValueError(msg)
        path = self._data_dir / str(run_id) / f"{artifact_type}.json"
        exists = await asyncio.to_thread(path.exists)
        if not exists:
            return None
        text = await asyncio.to_thread(path.read_text)
        return json.loads(text)

    async def save(self, run_id: RunId, artifact_type: str, data: Any) -> str:
        """Save an artifact by type name.

        Generic entry point — validates against ``_ALLOWED_ARTIFACT_TYPES``
        and delegates to ``_write_artifact``.
        """
        return await self._write_artifact(run_id, artifact_type, data)

    # ── Private helpers ──────────────────────────────────────────

    async def _write_artifact(self, run_id: RunId, name: str, data: Any) -> str:
        """Write data as JSON and return the file path."""
        name = _sanitize_name(name)
        if name not in _ALLOWED_ARTIFACT_TYPES:
            msg = f"Invalid artifact type: {name!r}"
            raise ValueError(msg)
        run_dir = self._data_dir / str(run_id)
        await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=True)
        path = run_dir / f"{name}.json"
        content = json.dumps(data, indent=2, default=str)
        await asyncio.to_thread(path.write_text, content)
        return str(path)

    def _serialize_event(self, event: Any) -> dict:
        """Convert an event object to a JSON-serializable dict."""
        if hasattr(event, "model_dump"):
            return event.model_dump(mode="json")
        if isinstance(event, dict):
            return event
        return {
            "event_type": str(getattr(event, "event_type", "")),
            "data": str(event),
        }
