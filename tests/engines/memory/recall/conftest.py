"""Fixtures for the recall-quality harness (Phase 4B Step 4b).

Embedder-agnostic: the ``embedder_id`` fixture is parametrised so
Step 13 can extend the parameter list with ``sentence-transformers``
and the whole harness reruns on the new embedder with no other
edits.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from volnix.core.memory_types import MemoryRecord, content_hash_of
from volnix.core.types import MemoryRecordId
from volnix.engines.memory.store import SQLiteMemoryStore
from volnix.persistence.manager import create_database

_CORPUS_PATH = Path(__file__).parent / "corpus.json"


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    """Load the 30-record / 27-query fixture once per module."""
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


# ``params`` is a list so Step 13 only needs to append to it.
# Runtime dispatch on ``embedder_id`` happens inside ``seeded_store``.
@pytest.fixture(params=["fts5"])
def embedder_id(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
async def seeded_store(
    embedder_id: str, corpus: dict[str, Any]
) -> AsyncIterator[tuple[SQLiteMemoryStore, str]]:
    """Fresh in-memory SQLite, seeded with every record from the
    corpus. Yields ``(store, embedder_id)`` — the harness tests
    branch on embedder_id for thresholds but use the same store API.

    Step 13 will add a sentence-transformers branch here that
    constructs the store with a different tokenizer / embedder
    configuration.
    """
    db = await create_database(":memory:", wal_mode=False)
    # Default tokenizer includes ``remove_diacritics 2`` (see
    # MemoryConfig). Tokenizer customisation happens at the store
    # constructor, not here — if Step 13 needs a different
    # tokenizer, it branches on ``embedder_id``.
    store = SQLiteMemoryStore(db)
    await store.initialize()
    for rec in corpus["records"]:
        mr = MemoryRecord(
            record_id=MemoryRecordId(rec["id"]),
            scope="actor",
            owner_id=rec["owner_id"],
            kind="episodic",
            tier="tier2",
            source="explicit",
            content=rec["content"],
            content_hash=content_hash_of(rec["content"]),
            importance=0.5,
            tags=[],
            created_tick=0,
        )
        await store.insert(mr)
    try:
        yield store, embedder_id
    finally:
        await db.close()
