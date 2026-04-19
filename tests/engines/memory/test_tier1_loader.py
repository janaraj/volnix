"""Tests for Tier-1 fixture loader (Phase 4B Step 9).

Uses real SQLiteMemoryStore + real YAML parsing. Negative-case
first per test discipline — every malformed fixture variant has a
dedicated rejection test BEFORE the positive happy-path tests.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from volnix.engines.memory.store import SQLiteMemoryStore
from volnix.engines.memory.tier1_loader import Tier1Fixture, load_tier1_fixtures
from volnix.persistence.manager import create_database

_FIXTURES_DIR = Path(__file__).parent / "tier1_fixtures"


@pytest.fixture
async def store() -> AsyncIterator[SQLiteMemoryStore]:
    db = await create_database(":memory:", wal_mode=False)
    s = SQLiteMemoryStore(db)
    await s.initialize()
    try:
        yield s
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Tier1Fixture frozen Pydantic
# ---------------------------------------------------------------------------


class TestTier1Fixture:
    def test_negative_missing_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Tier1Fixture(importance=0.5, tags=[])  # type: ignore[call-arg]

    def test_negative_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Tier1Fixture(content="", importance=0.5)

    def test_negative_importance_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Tier1Fixture(content="x", importance=1.5)

    def test_negative_importance_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Tier1Fixture(content="x", importance=-0.1)

    def test_negative_extra_field_rejected(self) -> None:
        # D9-5: extra="forbid" — typos fail at load time.
        with pytest.raises(ValidationError):
            Tier1Fixture.model_validate({"content": "x", "importance": 0.5, "unknown": "typo"})

    def test_positive_minimal_shape_accepted(self) -> None:
        f = Tier1Fixture(content="hello", importance=0.5)
        assert f.tags == []

    def test_frozen(self) -> None:
        f = Tier1Fixture(content="x", importance=0.5)
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            f.importance = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Missing / empty file (D9-3)
# ---------------------------------------------------------------------------


class TestMissingOrEmptyFile:
    async def test_missing_file_returns_zero(self, store: SQLiteMemoryStore) -> None:
        count = await load_tier1_fixtures(Path("/definitely/does/not/exist.yaml"), store)
        assert count == 0

    async def test_empty_file_returns_zero(self, store: SQLiteMemoryStore) -> None:
        count = await load_tier1_fixtures(_FIXTURES_DIR / "empty.yaml", store)
        assert count == 0


# ---------------------------------------------------------------------------
# Malformed inputs (D9-4, D9-5)
# ---------------------------------------------------------------------------


class TestMalformedInputs:
    async def test_malformed_yaml_raises(self, store: SQLiteMemoryStore) -> None:
        with pytest.raises(yaml.YAMLError):
            await load_tier1_fixtures(_FIXTURES_DIR / "malformed_yaml.yaml", store)

    async def test_top_level_list_rejected(self, store: SQLiteMemoryStore) -> None:
        with pytest.raises(ValueError, match="top-level mapping"):
            await load_tier1_fixtures(_FIXTURES_DIR / "top_level_list.yaml", store)

    async def test_owner_value_not_list_rejected(self, store: SQLiteMemoryStore) -> None:
        with pytest.raises(ValueError, match="must map to a list"):
            await load_tier1_fixtures(_FIXTURES_DIR / "owner_value_not_list.yaml", store)

    async def test_extra_field_in_fixture_rejected(self, store: SQLiteMemoryStore) -> None:
        with pytest.raises(ValidationError):
            await load_tier1_fixtures(_FIXTURES_DIR / "extra_field.yaml", store)

    async def test_out_of_range_importance_rejected(self, store: SQLiteMemoryStore) -> None:
        with pytest.raises(ValidationError):
            await load_tier1_fixtures(_FIXTURES_DIR / "out_of_range_importance.yaml", store)

    async def test_missing_content_field_rejected(self, store: SQLiteMemoryStore) -> None:
        with pytest.raises(ValidationError):
            await load_tier1_fixtures(_FIXTURES_DIR / "missing_content.yaml", store)


# ---------------------------------------------------------------------------
# Happy path (D9-6, D9-7)
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_valid_fixture_loads_all_records(self, store: SQLiteMemoryStore) -> None:
        count = await load_tier1_fixtures(_FIXTURES_DIR / "valid.yaml", store)
        assert count == 3  # 2 alice + 1 bob

    async def test_record_ids_follow_tier1_format(self, store: SQLiteMemoryStore) -> None:
        await load_tier1_fixtures(_FIXTURES_DIR / "valid.yaml", store)
        alice_records = await store.list_by_owner("actor-alice", kind="semantic")
        ids = {str(r.record_id) for r in alice_records}
        assert ids == {"tier1:actor-alice:0", "tier1:actor-alice:1"}

    async def test_records_are_tier1_pack_fixture(self, store: SQLiteMemoryStore) -> None:
        await load_tier1_fixtures(_FIXTURES_DIR / "valid.yaml", store)
        records = await store.list_by_owner("actor-alice", kind="semantic")
        for r in records:
            assert r.tier == "tier1"
            assert r.source == "pack_fixture"
            assert r.kind == "semantic"
            assert r.consolidated_from is None
            assert r.created_tick == 0

    async def test_tags_and_importance_preserved(self, store: SQLiteMemoryStore) -> None:
        await load_tier1_fixtures(_FIXTURES_DIR / "valid.yaml", store)
        alice = await store.list_by_owner("actor-alice", kind="semantic")
        r0 = next(r for r in alice if str(r.record_id) == "tier1:actor-alice:0")
        assert r0.importance == 0.9
        assert "preference" in r0.tags
        assert "identity" in r0.tags


# ---------------------------------------------------------------------------
# Determinism (D9-6)
# ---------------------------------------------------------------------------


class TestLoaderDeterminism:
    async def test_two_runs_produce_identical_record_ids(self) -> None:
        """D9-6: same YAML + same store shape → same record_ids."""

        async def _run() -> set[str]:
            db = await create_database(":memory:", wal_mode=False)
            s = SQLiteMemoryStore(db)
            await s.initialize()
            try:
                await load_tier1_fixtures(_FIXTURES_DIR / "valid.yaml", s)
                alice = await s.list_by_owner("actor-alice", kind="semantic")
                bob = await s.list_by_owner("actor-bob", kind="semantic")
                return {str(r.record_id) for r in (*alice, *bob)}
            finally:
                await db.close()

        a = await _run()
        b = await _run()
        assert a == b


# ---------------------------------------------------------------------------
# Re-load collision (D9-8)
# ---------------------------------------------------------------------------


class TestReloadCollision:
    async def test_loading_same_file_twice_fails_on_pk_collision(
        self, store: SQLiteMemoryStore
    ) -> None:
        # D9-8: record_ids are deterministic, so running the loader
        # twice against the same store hits SQLite's PRIMARY KEY
        # constraint on the second pass. Loud failure is correct —
        # the composition root (Step 10) is responsible for resetting
        # the DB (via reset_on_world_start) before loading.
        await load_tier1_fixtures(_FIXTURES_DIR / "valid.yaml", store)
        with pytest.raises(sqlite3.IntegrityError):
            await load_tier1_fixtures(_FIXTURES_DIR / "valid.yaml", store)
