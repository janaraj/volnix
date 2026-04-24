"""Tests for the 6 new ledger entries added in Phase 4B Step 1.

Per test discipline: every ledger entry type needs an assertion on
shape + destination (the ``ENTRY_REGISTRY`` registration).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.core.types import ActorId
from volnix.ledger.entries import (
    ENTRY_REGISTRY,
    MemoryAccessDeniedEntry,
    MemoryConsolidationEntry,
    MemoryEvictionEntry,
    MemoryHydrationEntry,
    MemoryRecallEntry,
    MemoryWriteEntry,
    deserialize_entry,
)


class TestMemoryLedgerEntries:
    def test_negative_write_entry_missing_fields(self) -> None:
        with pytest.raises(ValidationError):
            MemoryWriteEntry()  # type: ignore[call-arg]

    def test_negative_recall_entry_missing_fields(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecallEntry()  # type: ignore[call-arg]

    def test_negative_consolidation_entry_missing_fields(self) -> None:
        with pytest.raises(ValidationError):
            MemoryConsolidationEntry()  # type: ignore[call-arg]

    def test_negative_access_denied_missing_fields(self) -> None:
        with pytest.raises(ValidationError):
            MemoryAccessDeniedEntry()  # type: ignore[call-arg]

    def test_positive_write_entry_shape(self) -> None:
        e = MemoryWriteEntry(
            caller_actor_id=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            record_id="r1",
            kind="episodic",
            source="implicit",
            importance=0.4,
            tick=0,
        )
        assert e.entry_type == "memory_write"
        assert e.model_config.get("frozen") is True

    def test_positive_recall_entry_shape(self) -> None:
        e = MemoryRecallEntry(
            caller_actor_id=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            query_mode="hybrid",
            query_id="q1",
            result_count=3,
            tick=0,
        )
        assert e.entry_type == "memory_recall"

    def test_positive_consolidation_entry_shape(self) -> None:
        e = MemoryConsolidationEntry(
            actor_id=ActorId("npc-1"),
            episodic_consumed=10,
            semantic_produced=2,
            episodic_pruned=10,
            tick=50,
        )
        assert e.entry_type == "memory_consolidation"

    def test_positive_eviction_and_hydration_shapes(self) -> None:
        e1 = MemoryEvictionEntry(actor_id=ActorId("npc-1"))
        assert e1.entry_type == "memory_eviction"
        e2 = MemoryHydrationEntry(actor_id=ActorId("npc-1"))
        assert e2.entry_type == "memory_hydration"

    def test_positive_access_denied_entry_shape(self) -> None:
        e = MemoryAccessDeniedEntry(
            caller_actor_id=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-2",
            op="read",
        )
        assert e.entry_type == "memory_access_denied"


class TestTypedIdDiscipline:
    """C3: caller_actor_id and actor_id must be typed ActorId, not
    plain str. C4: target_scope must be MemoryScope, not plain str —
    typo-accepted scopes silently break store filters."""

    # C4 — target_scope must reject non-Literal strings
    @pytest.mark.parametrize(
        "factory",
        [
            lambda s: MemoryWriteEntry(
                caller_actor_id=ActorId("a"),
                target_scope=s,
                target_owner="x",
                record_id="r",
                kind="episodic",
                source="implicit",
                importance=0.5,
                tick=0,
            ),
            lambda s: MemoryRecallEntry(
                caller_actor_id=ActorId("a"),
                target_scope=s,
                target_owner="x",
                query_mode="hybrid",
                query_id="q",
                result_count=0,
                tick=0,
            ),
            lambda s: MemoryAccessDeniedEntry(
                caller_actor_id=ActorId("a"),
                target_scope=s,
                target_owner="x",
                op="read",
            ),
        ],
        ids=["write", "recall", "access_denied"],
    )
    @pytest.mark.parametrize("bad_scope", ["actos", "ACTOR", "global", ""])
    def test_negative_invalid_target_scope_rejected(self, factory, bad_scope: str) -> None:
        with pytest.raises(ValidationError):
            factory(bad_scope)

    # C1/C2 — numeric range enforcement on ledger entries
    @pytest.mark.parametrize("bad_importance", [-0.1, 1.01])
    def test_negative_write_entry_importance_out_of_range(self, bad_importance: float) -> None:
        with pytest.raises(ValidationError):
            MemoryWriteEntry(
                caller_actor_id=ActorId("a"),
                target_scope="actor",
                target_owner="x",
                record_id="r",
                kind="episodic",
                source="implicit",
                importance=bad_importance,
                tick=0,
            )

    @pytest.mark.parametrize("bad_tick", [-1, -100])
    def test_negative_write_entry_tick_negative_rejected(self, bad_tick: int) -> None:
        with pytest.raises(ValidationError):
            MemoryWriteEntry(
                caller_actor_id=ActorId("a"),
                target_scope="actor",
                target_owner="x",
                record_id="r",
                kind="episodic",
                source="implicit",
                importance=0.5,
                tick=bad_tick,
            )

    @pytest.mark.parametrize("bad_count", [-1, -5])
    def test_negative_consolidation_counts_non_negative(self, bad_count: int) -> None:
        with pytest.raises(ValidationError):
            MemoryConsolidationEntry(
                actor_id=ActorId("a"),
                episodic_consumed=bad_count,
                semantic_produced=0,
                episodic_pruned=0,
                tick=0,
            )


class TestEntryRoundTrip:
    """M4: every new entry must round-trip through
    ``deserialize_entry`` — registration alone is insufficient.
    A schema drift between serialize and deserialize would surface
    here, not during a downstream integration test."""

    @pytest.mark.parametrize(
        "entry",
        [
            MemoryWriteEntry(
                caller_actor_id=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-1",
                record_id="r1",
                kind="episodic",
                source="implicit",
                importance=0.4,
                tick=10,
            ),
            MemoryRecallEntry(
                caller_actor_id=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-1",
                query_mode="hybrid",
                query_id="q1",
                result_count=3,
                tick=10,
            ),
            MemoryConsolidationEntry(
                actor_id=ActorId("npc-1"),
                episodic_consumed=10,
                semantic_produced=2,
                episodic_pruned=10,
                tick=50,
            ),
            MemoryEvictionEntry(actor_id=ActorId("npc-1")),
            MemoryHydrationEntry(actor_id=ActorId("npc-1")),
            MemoryAccessDeniedEntry(
                caller_actor_id=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-2",
                op="read",
            ),
        ],
        ids=[
            "write",
            "recall",
            "consolidation",
            "eviction",
            "hydration",
            "access_denied",
        ],
    )
    def test_round_trip_preserves_shape(self, entry) -> None:
        payload = entry.model_dump_json()
        row = {"entry_type": entry.entry_type, "payload": payload}
        back = deserialize_entry(row)
        assert type(back) is type(entry)
        assert back.entry_type == entry.entry_type
        # Value-equality across the boundary
        assert back.model_dump() == entry.model_dump()


class TestEntryRegistry:
    """All six new entry types must be registered — that is how
    typed deserialization finds them."""

    @pytest.mark.parametrize(
        "entry_type, cls",
        [
            ("memory_write", MemoryWriteEntry),
            ("memory_recall", MemoryRecallEntry),
            ("memory_consolidation", MemoryConsolidationEntry),
            ("memory_eviction", MemoryEvictionEntry),
            ("memory_hydration", MemoryHydrationEntry),
            ("memory_access_denied", MemoryAccessDeniedEntry),
        ],
    )
    def test_entry_registered(self, entry_type: str, cls: type) -> None:
        assert entry_type in ENTRY_REGISTRY, (
            f"{entry_type!r} missing from ENTRY_REGISTRY — "
            "typed deserialization will fall back to LedgerEntry"
        )
        assert ENTRY_REGISTRY[entry_type] is cls
