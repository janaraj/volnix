"""Tests for MemoryEngineProtocol (PMF Plan Phase 4B, Step 1).

Structural (runtime_checkable) — any class satisfying the method
signatures should register as compatible via ``isinstance``.
"""

from __future__ import annotations

from typing import Any

from volnix.core.memory_types import MemoryQuery, MemoryRecall, MemoryScope, MemoryWrite
from volnix.core.protocols import MemoryEngineProtocol
from volnix.core.types import ActorId, MemoryRecordId


class _StubMemoryEngine:
    """Minimal stub that satisfies the protocol shape."""

    async def remember(
        self,
        *,
        caller: ActorId,
        target_scope: MemoryScope,
        target_owner: str,
        write: MemoryWrite,
        tick: int,
    ) -> MemoryRecordId:
        return MemoryRecordId("stub")

    async def recall(
        self,
        *,
        caller: ActorId,
        target_scope: MemoryScope,
        target_owner: str,
        query: MemoryQuery,
        tick: int,
    ) -> MemoryRecall:
        return MemoryRecall(query_id="q", records=[], total_matched=0, truncated=False)

    async def consolidate(
        self, actor_id: ActorId, *, force: bool = False, tick: int = 0
    ) -> Any:
        return None

    async def evict(self, actor_id: ActorId) -> None:
        return None

    async def hydrate(self, actor_id: ActorId) -> None:
        return None


class _IncompleteStub:
    """Missing ``evict`` and ``hydrate`` — must NOT satisfy the protocol."""

    async def remember(self, **kwargs: Any) -> MemoryRecordId:
        return MemoryRecordId("x")

    async def recall(self, **kwargs: Any) -> MemoryRecall:
        return MemoryRecall(query_id="q", records=[], total_matched=0, truncated=False)

    async def consolidate(self, *args: Any, **kwargs: Any) -> Any:
        return None


class TestMemoryEngineProtocol:
    def test_negative_incomplete_stub_does_not_conform(self) -> None:
        # runtime_checkable Protocols check method presence structurally;
        # missing methods should fail the isinstance check.
        assert not isinstance(_IncompleteStub(), MemoryEngineProtocol)

    def test_positive_complete_stub_conforms(self) -> None:
        assert isinstance(_StubMemoryEngine(), MemoryEngineProtocol)

    def test_protocol_methods_documented(self) -> None:
        # Five public methods — any silent removal breaks consumers.
        expected = {"remember", "recall", "consolidate", "evict", "hydrate"}
        actual = {
            name
            for name in dir(MemoryEngineProtocol)
            if not name.startswith("_")
        }
        missing = expected - actual
        assert not missing, f"protocol missing methods: {missing}"
