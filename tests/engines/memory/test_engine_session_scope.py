"""Engine-layer session-scope tests.

Locks ``MemoryEngine.remember`` / ``.recall`` session-scoping
semantics + ledger entry population
(``tnl/session-scoped-memory.tnl``).

Reuses the ``_build_bundle`` construction pattern from
``test_memory_engine.py`` (authored locally so this file is
self-contained and doesn't depend on cross-file fixture plumbing).
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from volnix.core.memory_types import HybridQuery, MemoryWrite
from volnix.core.types import ActorId, SessionId
from volnix.engines.memory.config import MemoryConfig
from volnix.engines.memory.consolidation import Consolidator
from volnix.engines.memory.embedder import FTS5Embedder
from volnix.engines.memory.engine import MemoryEngine
from volnix.engines.memory.recall import Recall
from volnix.engines.memory.store import SQLiteMemoryStore
from volnix.ledger.entries import MemoryRecallEntry, MemoryWriteEntry
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage
from volnix.persistence.manager import create_database


class _RecordingLedger:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def append(self, entry: Any) -> int:
        self.entries.append(entry)
        return len(self.entries)

    def of_type(self, cls: type) -> list[Any]:
        return [e for e in self.entries if isinstance(e, cls)]


class _StubLLMProvider(LLMProvider):
    provider_name: ClassVar[str] = "stub"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content='{"facts": []}',
            usage=LLMUsage(prompt_tokens=1, completion_tokens=1),
            model="stub",
            provider=self.provider_name,
        )


def _router() -> LLMRouter:
    cfg = LLMConfig(
        defaults=LLMProviderEntry(type="stub", default_model="stub"),
        providers={"stub": LLMProviderEntry(type="stub")},
        routing={},
        max_retries=0,
    )
    reg = ProviderRegistry()
    reg.register("stub", _StubLLMProvider())
    return LLMRouter(config=cfg, registry=reg)


@pytest.fixture
async def bundle():
    db = await create_database(":memory:", wal_mode=False)
    store = SQLiteMemoryStore(db)
    await store.initialize()
    embedder = FTS5Embedder()
    recall = Recall(store=store, embedder=embedder)
    consolidator = Consolidator(
        store=store,
        llm_router=_router(),
        use_case="memory_distill",
        episodic_window=10,
    )
    engine = MemoryEngine(
        memory_config=MemoryConfig(enabled=True),
        store=store,
        embedder=embedder,
        recall=recall,
        consolidator=consolidator,
        seed=42,
    )
    ledger = _RecordingLedger()
    engine._ledger = ledger
    try:
        yield engine, ledger, store
    finally:
        await db.close()


def _write(content: str) -> MemoryWrite:
    return MemoryWrite(content=content, kind="episodic", importance=0.5, source="explicit")


# ---------------------------------------------------------------------------
# remember() — stamps session_id onto records + ledger
# ---------------------------------------------------------------------------


class TestRememberStampsSessionId:
    async def test_positive_remember_persists_session_id(self, bundle) -> None:
        engine, _, store = bundle
        caller = ActorId("actor-1")
        record_id = await engine.remember(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            write=_write("alpha content"),
            tick=7,
            session_id=SessionId("sess-alpha"),
        )
        rec = await store.get(record_id)
        assert rec is not None
        assert rec.session_id == SessionId("sess-alpha")

    async def test_positive_ledger_write_entry_carries_session_id(self, bundle) -> None:
        engine, ledger, _ = bundle
        caller = ActorId("actor-1")
        await engine.remember(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            write=_write("alpha"),
            tick=1,
            session_id=SessionId("sess-alpha"),
        )
        write_entries = ledger.of_type(MemoryWriteEntry)
        assert len(write_entries) == 1
        assert write_entries[0].session_id == SessionId("sess-alpha")

    async def test_positive_remember_without_session_id_persists_null(self, bundle) -> None:
        engine, ledger, store = bundle
        caller = ActorId("actor-1")
        record_id = await engine.remember(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            write=_write("legacy"),
            tick=1,
        )
        rec = await store.get(record_id)
        assert rec is not None and rec.session_id is None
        entries = ledger.of_type(MemoryWriteEntry)
        assert entries[-1].session_id is None


# ---------------------------------------------------------------------------
# recall() — scoped to session_id; ledger entry carries session_id
# ---------------------------------------------------------------------------


class TestRecallScopedToSession:
    async def test_negative_recall_wrong_session_returns_empty(self, bundle) -> None:
        engine, _, _ = bundle
        caller = ActorId("actor-1")
        await engine.remember(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            write=_write("unique-alpha-token"),
            tick=1,
            session_id=SessionId("sess-alpha"),
        )
        result = await engine.recall(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            query=HybridQuery(semantic_text="unique-alpha-token", top_k=5),
            tick=2,
            session_id=SessionId("sess-beta"),
        )
        assert result.records == []
        assert result.total_matched == 0

    async def test_positive_recall_filters_by_session_id(self, bundle) -> None:
        engine, _, _ = bundle
        caller = ActorId("actor-1")
        await engine.remember(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            write=_write("apple-banana-alpha"),
            tick=1,
            session_id=SessionId("sess-alpha"),
        )
        await engine.remember(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            write=_write("apple-banana-beta"),
            tick=1,
            session_id=SessionId("sess-beta"),
        )
        result = await engine.recall(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            query=HybridQuery(semantic_text="apple-banana", top_k=5),
            tick=2,
            session_id=SessionId("sess-alpha"),
        )
        assert len(result.records) == 1
        assert result.records[0].content == "apple-banana-alpha"
        assert result.records[0].session_id == SessionId("sess-alpha")

    async def test_positive_ledger_recall_entry_carries_session_id(self, bundle) -> None:
        engine, ledger, _ = bundle
        caller = ActorId("actor-1")
        await engine.recall(
            caller=caller,
            target_scope="actor",
            target_owner=str(caller),
            query=HybridQuery(semantic_text="anything", top_k=5),
            tick=1,
            session_id=SessionId("sess-ledger-check"),
        )
        recall_entries = ledger.of_type(MemoryRecallEntry)
        assert len(recall_entries) == 1
        assert recall_entries[0].session_id == SessionId("sess-ledger-check")


# ---------------------------------------------------------------------------
# Deprecation warning on reset_on_world_start=True
# ---------------------------------------------------------------------------


class TestResetOnWorldStartDeprecation:
    """``reset_on_world_start=True`` MUST log exactly one deprecation
    warning per engine initialization
    (``tnl/session-scoped-memory.tnl``)."""

    async def test_positive_warning_fires_when_flag_true(self, caplog) -> None:
        import logging

        db = await create_database(":memory:", wal_mode=False)
        try:
            store = SQLiteMemoryStore(db)
            embedder = FTS5Embedder()
            recall = Recall(store=store, embedder=embedder)
            consolidator = Consolidator(
                store=store,
                llm_router=_router(),
                use_case="memory_distill",
                episodic_window=10,
            )
            engine = MemoryEngine(
                memory_config=MemoryConfig(enabled=True, reset_on_world_start=True),
                store=store,
                embedder=embedder,
                recall=recall,
                consolidator=consolidator,
                seed=42,
            )
            with caplog.at_level(logging.WARNING, logger="volnix.engines.memory.engine"):
                await engine._on_initialize()
            deprecation_msgs = [
                rec
                for rec in caplog.records
                if "reset_on_world_start is deprecated" in rec.getMessage()
            ]
            # Exactly one warning per MUST clause, not zero and not
            # multiple.
            assert len(deprecation_msgs) == 1
        finally:
            await db.close()

    async def test_negative_warning_silent_when_flag_false(self, caplog) -> None:
        import logging

        db = await create_database(":memory:", wal_mode=False)
        try:
            store = SQLiteMemoryStore(db)
            embedder = FTS5Embedder()
            recall = Recall(store=store, embedder=embedder)
            consolidator = Consolidator(
                store=store,
                llm_router=_router(),
                use_case="memory_distill",
                episodic_window=10,
            )
            engine = MemoryEngine(
                memory_config=MemoryConfig(enabled=True, reset_on_world_start=False),
                store=store,
                embedder=embedder,
                recall=recall,
                consolidator=consolidator,
                seed=42,
            )
            with caplog.at_level(logging.WARNING, logger="volnix.engines.memory.engine"):
                await engine._on_initialize()
            deprecation_msgs = [
                rec
                for rec in caplog.records
                if "reset_on_world_start is deprecated" in rec.getMessage()
            ]
            assert deprecation_msgs == []
        finally:
            await db.close()
