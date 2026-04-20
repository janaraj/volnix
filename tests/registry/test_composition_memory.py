"""Unit tests for ``build_memory_engine`` (PMF 4B Step 10).

Negative cases first — composition is an integration seam and the
gate logic (disabled → None; unknown embedder → raise) is where
silent bugs slip in.

Real ``ConnectionManager`` + SQLite files under ``tmp_path`` — no
mocks on the path under test. The composition returns a fully-built
engine that is ready to ``initialize()``; tests verify shape, not
lifecycle (lifecycle belongs to ``app.py``).
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from volnix.engines.memory.config import MemoryConfig
from volnix.persistence.config import PersistenceConfig
from volnix.persistence.manager import ConnectionManager
from volnix.registry.composition import build_memory_engine


def _router() -> MagicMock:
    r = MagicMock()
    r.route = AsyncMock()
    return r


@pytest.fixture
async def conn_mgr(tmp_path: Path) -> AsyncIterator[ConnectionManager]:
    cfg = PersistenceConfig(base_dir=str(tmp_path), wal_mode=False)
    mgr = ConnectionManager(cfg)
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.shutdown()


# ---------------------------------------------------------------------------
# Disabled path
# ---------------------------------------------------------------------------


class TestDisabledReturnsNone:
    async def test_negative_disabled_returns_none(self, conn_mgr: ConnectionManager) -> None:
        cfg = MemoryConfig(enabled=False)
        out = await build_memory_engine(
            memory_config=cfg,
            world_seed=1,
            llm_router=_router(),
            connection_manager=conn_mgr,
        )
        assert out is None


# ---------------------------------------------------------------------------
# Unknown / dense embedder paths (4B ships FTS5 only)
# ---------------------------------------------------------------------------


class TestUnknownEmbedderRaises:
    async def test_negative_disabled_config_skips_embedder_check_entirely(
        self, conn_mgr: ConnectionManager
    ) -> None:
        """Short-circuit contract: when ``enabled=False``, the builder
        returns ``None`` BEFORE touching the embedder. Even a
        dense-embedder value that would load a model when enabled
        must simply return None when disabled — no model download,
        no import of extras."""
        cfg = MemoryConfig(enabled=False, embedder="sentence-transformers:all-MiniLM-L6-v2")
        out = await build_memory_engine(
            memory_config=cfg,
            world_seed=1,
            llm_router=_router(),
            connection_manager=conn_mgr,
        )
        assert out is None

    async def test_negative_openai_embedder_still_raises(self, conn_mgr: ConnectionManager) -> None:
        """D13-1: OpenAI intentionally deferred beyond 4B. Builder
        must still raise a loud NotImplementedError — silent FTS5
        fallback would diverge from what the user configured."""
        cfg = MemoryConfig(enabled=True, embedder="openai:text-embedding-3-small")
        with pytest.raises(NotImplementedError, match="OpenAI"):
            await build_memory_engine(
                memory_config=cfg,
                world_seed=1,
                llm_router=_router(),
                connection_manager=conn_mgr,
            )


class TestSentenceTransformersComposition:
    """PMF 4B Step 13 — composition constructs a real
    ``SentenceTransformersEmbedder`` when the config opts in.

    Skipped cleanly when the ``embeddings`` extra is missing."""

    async def test_positive_sentence_transformers_builds_engine(
        self, conn_mgr: ConnectionManager
    ) -> None:
        pytest.importorskip("sentence_transformers")
        from volnix.engines.memory.embedder import SentenceTransformersEmbedder

        cfg = MemoryConfig(enabled=True, embedder="sentence-transformers:all-MiniLM-L6-v2")
        engine = await build_memory_engine(
            memory_config=cfg,
            world_seed=1,
            llm_router=_router(),
            connection_manager=conn_mgr,
        )
        assert engine is not None
        assert isinstance(engine._embedder, SentenceTransformersEmbedder)
        assert engine._embedder.provider_id == "sentence-transformers:all-MiniLM-L6-v2"
        assert engine._embedder.dimensions == 384

    async def test_positive_sentence_transformers_default_model_when_no_colon(
        self, conn_mgr: ConnectionManager
    ) -> None:
        """D13-3: bare ``sentence-transformers`` (no colon suffix)
        falls back to ``all-MiniLM-L6-v2``."""
        pytest.importorskip("sentence_transformers")
        cfg = MemoryConfig(enabled=True, embedder="sentence-transformers")
        engine = await build_memory_engine(
            memory_config=cfg,
            world_seed=1,
            llm_router=_router(),
            connection_manager=conn_mgr,
        )
        assert engine is not None
        assert engine._embedder.provider_id == "sentence-transformers:all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Enabled happy path
# ---------------------------------------------------------------------------


class TestEnabledReturnsEngine:
    async def test_positive_fts5_returns_memory_engine(self, conn_mgr: ConnectionManager) -> None:
        from volnix.engines.memory.engine import MemoryEngine

        cfg = MemoryConfig(enabled=True)
        engine = await build_memory_engine(
            memory_config=cfg,
            world_seed=42,
            llm_router=_router(),
            connection_manager=conn_mgr,
        )
        assert isinstance(engine, MemoryEngine)
        assert engine._seed == 42
        assert engine._memory_config is cfg
        # Subscriptions still match Step 8 contract.
        assert engine.subscriptions == ["cohort.rotated"]

    async def test_positive_default_storage_db_name_reaches_conn_mgr(
        self, conn_mgr: ConnectionManager
    ) -> None:
        """G5: builder must pass the logical DB name through
        ``ConnectionManager.get_connection`` — not construct a new
        SQLiteDatabase inside the builder."""
        cfg = MemoryConfig(enabled=True)
        engine = await build_memory_engine(
            memory_config=cfg,
            world_seed=1,
            llm_router=_router(),
            connection_manager=conn_mgr,
        )
        assert engine is not None
        # The store's DB came from the connection manager under the
        # configured logical name.
        assert engine._store._db is conn_mgr._connections["volnix_memory"]

    async def test_positive_custom_storage_db_name_honoured(
        self, conn_mgr: ConnectionManager
    ) -> None:
        cfg = MemoryConfig(enabled=True, storage_db_name="custom_memory_db")
        engine = await build_memory_engine(
            memory_config=cfg,
            world_seed=1,
            llm_router=_router(),
            connection_manager=conn_mgr,
        )
        assert engine is not None
        assert "custom_memory_db" in conn_mgr._connections


# ---------------------------------------------------------------------------
# Signature guard (G8 / D10-1)
# ---------------------------------------------------------------------------


class TestSignatureGuard:
    def test_signature_matches_g8_revised(self) -> None:
        sig = inspect.signature(build_memory_engine)
        params = list(sig.parameters.values())
        names = [p.name for p in params]
        assert names[:4] == [
            "memory_config",
            "world_seed",
            "llm_router",
            "connection_manager",
        ]
        assert sig.parameters["fixtures_path"].kind == inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters["fixtures_path"].default is None

    def test_is_async(self) -> None:
        assert inspect.iscoroutinefunction(build_memory_engine)
