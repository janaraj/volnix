"""Phase 4C Step 9 — snapshot(label, tick) fix tests.

Pre-Step-9 ``StateEngine.snapshot(label)`` hardcoded ``tick=0`` on
the ``SnapshotEntry`` it wrote to the ledger. Step 9 adds a ``tick``
kwarg (default 0) so consumers auditing snapshots know when in
simulation time the snapshot was captured.

Negative ratio: 1/2 = 50%.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from volnix.engines.state.engine import StateEngine


@pytest.fixture
async def engine(tmp_path):
    e = StateEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    bus.publish = AsyncMock()
    await e.initialize(
        {
            "db_path": str(tmp_path / "state.db"),
            "snapshot_dir": str(tmp_path / "snap"),
        },
        bus,
    )
    await e.start()
    yield e
    await e.stop()


class _RecordingLedger:
    def __init__(self) -> None:
        self.entries: list = []

    async def append(self, entry) -> int:
        self.entries.append(entry)
        return len(self.entries)


async def test_positive_snapshot_entry_carries_real_tick(engine) -> None:
    """Passing ``tick=42`` lands on the SnapshotEntry — not the
    pre-Step-9 hardcoded ``0``."""
    ledger = _RecordingLedger()
    engine._ledger = ledger
    await engine.snapshot("checkpoint-42", tick=42)
    snap_entries = [e for e in ledger.entries if type(e).__name__ == "SnapshotEntry"]
    assert len(snap_entries) == 1
    assert snap_entries[0].tick == 42


async def test_negative_snapshot_default_tick_is_zero(engine) -> None:
    """The default preserves pre-Step-9 behaviour byte-identical —
    callers that don't pass ``tick`` still see ``tick=0`` on the
    ledger entry."""
    ledger = _RecordingLedger()
    engine._ledger = ledger
    await engine.snapshot("legacy-label")
    snap_entries = [e for e in ledger.entries if type(e).__name__ == "SnapshotEntry"]
    assert len(snap_entries) == 1
    assert snap_entries[0].tick == 0
