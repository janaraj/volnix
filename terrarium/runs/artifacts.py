"""Artifact storage for evaluation runs.

The :class:`ArtifactStore` persists reports, scorecards, event logs,
and configuration snapshots associated with a run.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.types import RunId
from terrarium.runs.config import RunConfig


class ArtifactStore:
    """Stores and retrieves run artifacts (reports, scorecards, logs, configs).

    Args:
        config: Run configuration settings.
    """

    def __init__(self, config: RunConfig) -> None:
        self._config = config

    async def save_report(self, run_id: RunId, report: dict) -> str:
        """Save a run report and return its storage path.

        Args:
            run_id: The run this report belongs to.
            report: The report data.

        Returns:
            Filesystem path where the report was saved.
        """
        ...

    async def save_scorecard(self, run_id: RunId, scorecard: dict) -> str:
        """Save a scorecard and return its storage path.

        Args:
            run_id: The run this scorecard belongs to.
            scorecard: The scorecard data.

        Returns:
            Filesystem path where the scorecard was saved.
        """
        ...

    async def save_event_log(self, run_id: RunId, events: list) -> str:
        """Save an event log and return its storage path.

        Args:
            run_id: The run this log belongs to.
            events: List of event dicts to persist.

        Returns:
            Filesystem path where the log was saved.
        """
        ...

    async def save_config(self, run_id: RunId, config: dict) -> str:
        """Save a configuration snapshot and return its storage path.

        Args:
            run_id: The run this config belongs to.
            config: The configuration data.

        Returns:
            Filesystem path where the config was saved.
        """
        ...

    async def list_artifacts(self, run_id: RunId) -> list[dict]:
        """List all artifacts for a run.

        Args:
            run_id: The run whose artifacts to list.

        Returns:
            A list of artifact metadata dicts.
        """
        ...

    async def load_artifact(self, run_id: RunId, artifact_type: str) -> Any:
        """Load a specific artifact by type.

        Args:
            run_id: The run to load from.
            artifact_type: The type of artifact (``"report"``, ``"scorecard"``,
                ``"event_log"``, ``"config"``).

        Returns:
            The loaded artifact data.
        """
        ...
