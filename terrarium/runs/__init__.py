"""Run Management -- lifecycle, snapshots, artifacts, comparison, and replay.

This package manages the lifecycle of evaluation runs, including creation,
state tracking, snapshotting, artifact storage, cross-run comparison,
and replay.

Re-exports the primary public API surface::

    from terrarium.runs import RunManager, SnapshotManager, ArtifactStore
"""

from terrarium.runs.artifacts import ArtifactStore
from terrarium.runs.comparison import RunComparator
from terrarium.runs.config import RunConfig
from terrarium.runs.manager import RunManager
from terrarium.runs.replay import RunReplayer
from terrarium.runs.snapshot import SnapshotManager

__all__ = [
    "ArtifactStore",
    "RunComparator",
    "RunConfig",
    "RunManager",
    "RunReplayer",
    "SnapshotManager",
]
