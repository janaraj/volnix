"""Run Management -- lifecycle, snapshots, artifacts, comparison, and replay.

This package manages the lifecycle of evaluation runs, including creation,
state tracking, snapshotting, artifact storage, cross-run comparison,
and replay.

Re-exports the primary public API surface::

    from volnix.runs import RunManager, SnapshotManager, ArtifactStore
"""

from volnix.runs.artifacts import ArtifactStore
from volnix.runs.comparison import RunComparator
from volnix.runs.config import RunConfig
from volnix.runs.manager import RunManager
from volnix.runs.replay import RunReplayer
from volnix.runs.snapshot import SnapshotManager

__all__ = [
    "ArtifactStore",
    "RunComparator",
    "RunConfig",
    "RunManager",
    "RunReplayer",
    "SnapshotManager",
]
