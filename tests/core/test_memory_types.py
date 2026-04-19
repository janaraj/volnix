"""Tests for the protocol-exposed memory types (PMF Plan Phase 4B, Step 1).

Per the test-discipline principles (``DESIGN_PRINCIPLES.md`` §Test Discipline):
negative cases first, assert side effects (immutability), observability at
the shape level.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.core.memory_types import (
    GraphQuery,
    HybridQuery,
    ImportanceQuery,
    MemoryAccessDenied,
    MemoryRecall,
    MemoryRecord,
    MemoryWrite,
    SemanticQuery,
    StructuredQuery,
    TemporalQuery,
    content_hash_of,
)
from volnix.core.types import ActorId, MemoryRecordId


def _base_record_kwargs(**overrides):
    """Builder for a valid MemoryRecord. Individual tests override
    the fields they're testing — keeps each test focused on its
    invariant.

    ``content_hash`` is recomputed from ``content`` so overrides that
    change one without the other don't accidentally produce an
    invalid record (C1 of Step 3 review enforces the hash matches).
    """
    defaults = {
        "record_id": MemoryRecordId("r1"),
        "scope": "actor",
        "owner_id": "npc-1",
        "kind": "episodic",
        "tier": "tier2",
        "source": "explicit",
        "content": "hello",
        "importance": 0.5,
        "tags": [],
        "created_tick": 0,
    }
    defaults.update(overrides)
    # Compute content_hash from the final content, unless the test
    # explicitly wants to supply a malformed one.
    if "content_hash" not in defaults:
        defaults["content_hash"] = content_hash_of(defaults["content"])
    return defaults


class TestMemoryRecord:
    """MemoryRecord frozen value object — negative first per test discipline."""

    def test_negative_mutation_raises(self) -> None:
        rec = MemoryRecord(**_base_record_kwargs())
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            rec.importance = 0.9  # type: ignore[misc]

    def test_negative_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecord(**_base_record_kwargs(scope="global"))  # type: ignore[arg-type]

    def test_negative_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecord(**_base_record_kwargs(kind="procedural"))  # type: ignore[arg-type]

    def test_negative_invalid_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecord(**_base_record_kwargs(source="invented"))  # type: ignore[arg-type]

    # C1 — importance range enforcement
    @pytest.mark.parametrize("bad_importance", [-0.1, 1.01, -100.0, 42.0])
    def test_negative_importance_out_of_range_rejected(self, bad_importance: float) -> None:
        with pytest.raises(ValidationError):
            MemoryRecord(**_base_record_kwargs(importance=bad_importance))

    # C2 — created_tick non-negative
    @pytest.mark.parametrize("bad_tick", [-1, -100])
    def test_negative_created_tick_rejects_negative(self, bad_tick: int) -> None:
        with pytest.raises(ValidationError):
            MemoryRecord(**_base_record_kwargs(created_tick=bad_tick))

    # N1 — content_hash pattern
    @pytest.mark.parametrize(
        "bad_hash",
        [
            "deadbeef",  # too short
            "",  # empty
            "A" * 64,  # uppercase (pattern requires lowercase)
            "g" * 64,  # non-hex char
            "a" * 63,  # off-by-one too short
            "a" * 65,  # off-by-one too long
        ],
    )
    def test_negative_content_hash_pattern_enforced(self, bad_hash: str) -> None:
        with pytest.raises(ValidationError):
            MemoryRecord(**_base_record_kwargs(content_hash=bad_hash))

    # C1 of Step 3 review: content_hash must match sha256(content).
    # A valid-shaped but wrong digest (e.g., all zeros) must be rejected.
    def test_negative_content_hash_does_not_match_content_rejected(self) -> None:
        wrong_but_valid_shape = "0" * 64  # matches pattern, wrong digest
        with pytest.raises(ValidationError, match="does not match"):
            MemoryRecord(
                **_base_record_kwargs(
                    content="Hello world",
                    content_hash=wrong_but_valid_shape,
                )
            )

    def test_positive_content_hash_of_helper_produces_valid_record(self) -> None:
        # The canonical way to build a record: compute the hash via
        # the exported helper so algorithm + encoding stay in sync.
        rec = MemoryRecord(
            **_base_record_kwargs(
                content="canonical content",
                content_hash=content_hash_of("canonical content"),
            )
        )
        assert rec.content_hash == content_hash_of("canonical content")

    def test_positive_consolidated_from_backlink_on_semantic(self) -> None:
        rec = MemoryRecord(
            **_base_record_kwargs(
                record_id=MemoryRecordId("s1"),
                kind="semantic",
                source="consolidated",
                content="NPC-1 prefers evenings",
                importance=0.8,
                tags=["preference"],
                created_tick=100,
                consolidated_from=[MemoryRecordId("e1"), MemoryRecordId("e2")],
            )
        )
        assert rec.consolidated_from == [MemoryRecordId("e1"), MemoryRecordId("e2")]

    # N2 — episodic records must not carry consolidated_from
    def test_negative_episodic_with_consolidated_from_rejected(self) -> None:
        with pytest.raises(ValidationError, match="episodic"):
            MemoryRecord(
                **_base_record_kwargs(
                    kind="episodic",
                    consolidated_from=[MemoryRecordId("e1")],
                )
            )

    # N2 — pack_fixture records must not carry consolidated_from
    def test_negative_pack_fixture_with_consolidated_from_rejected(self) -> None:
        with pytest.raises(ValidationError, match="pack_fixture"):
            MemoryRecord(
                **_base_record_kwargs(
                    kind="semantic",
                    tier="tier1",
                    source="pack_fixture",
                    consolidated_from=[MemoryRecordId("e1")],
                )
            )


class TestMemoryQueryVariants:
    """Each query variant validates and carries its discriminator."""

    def test_negative_structured_requires_keys(self) -> None:
        with pytest.raises(ValidationError):
            StructuredQuery()  # type: ignore[call-arg]

    def test_negative_semantic_requires_text(self) -> None:
        with pytest.raises(ValidationError):
            SemanticQuery()  # type: ignore[call-arg]

    def test_negative_temporal_requires_tick_start(self) -> None:
        with pytest.raises(ValidationError):
            TemporalQuery()  # type: ignore[call-arg]

    def test_negative_hybrid_requires_semantic_text(self) -> None:
        with pytest.raises(ValidationError):
            HybridQuery()  # type: ignore[call-arg]

    def test_negative_graph_requires_entity(self) -> None:
        with pytest.raises(ValidationError):
            GraphQuery()  # type: ignore[call-arg]

    def test_discriminators_are_fixed(self) -> None:
        # The ``mode`` field is a Literal; changing it post-construction
        # would break tagged-union dispatch. Frozen models enforce.
        q = StructuredQuery(keys=["x"])
        assert q.mode == "structured"
        assert SemanticQuery(text="x").mode == "semantic"
        assert TemporalQuery(tick_start=0).mode == "temporal"
        assert ImportanceQuery().mode == "importance"
        assert GraphQuery(entity="e").mode == "graph"
        assert HybridQuery(semantic_text="x").mode == "hybrid"

    # M3 — all six variants must be frozen, not just StructuredQuery
    @pytest.mark.parametrize(
        "query",
        [
            StructuredQuery(keys=["a"]),
            TemporalQuery(tick_start=0),
            SemanticQuery(text="hi"),
            ImportanceQuery(),
            GraphQuery(entity="e"),
            HybridQuery(semantic_text="hi"),
        ],
        ids=[
            "structured",
            "temporal",
            "semantic",
            "importance",
            "graph",
            "hybrid",
        ],
    )
    def test_all_query_variants_frozen(self, query) -> None:
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            query.mode = "something_else"  # type: ignore[misc]

    # M1 — top_k upper bound on all variants carrying top_k
    @pytest.mark.parametrize("bad_top_k", [0, -1, 1001, 10**9])
    def test_negative_semantic_top_k_bounds(self, bad_top_k: int) -> None:
        with pytest.raises(ValidationError):
            SemanticQuery(text="x", top_k=bad_top_k)

    @pytest.mark.parametrize("bad_top_k", [0, -1, 1001])
    def test_negative_importance_top_k_bounds(self, bad_top_k: int) -> None:
        with pytest.raises(ValidationError):
            ImportanceQuery(top_k=bad_top_k)

    @pytest.mark.parametrize("bad_top_k", [0, -1, 1001])
    def test_negative_hybrid_top_k_bounds(self, bad_top_k: int) -> None:
        with pytest.raises(ValidationError):
            HybridQuery(semantic_text="x", top_k=bad_top_k)

    # M1 — temporal limit bounds
    @pytest.mark.parametrize("bad_limit", [0, -1, 10_001, 10**9])
    def test_negative_temporal_limit_bounds(self, bad_limit: int) -> None:
        with pytest.raises(ValidationError):
            TemporalQuery(tick_start=0, limit=bad_limit)

    # M1 — temporal tick_start non-negative
    def test_negative_temporal_tick_start_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TemporalQuery(tick_start=-1)

    # C4 of the Steps 1-5 bug-bounty review: cross-field validator
    # rejects backwards ranges. Without this, _temporal silently
    # matches nothing — Test Discipline #5 anti-pattern.
    def test_negative_temporal_tick_end_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="tick_end.*>= tick_start"):
            TemporalQuery(tick_start=100, tick_end=50)

    def test_positive_temporal_tick_end_equal_to_start_allowed(self) -> None:
        # Single-tick window is legitimate — not a regression.
        q = TemporalQuery(tick_start=42, tick_end=42)
        assert q.tick_start == q.tick_end == 42

    def test_positive_temporal_tick_end_none_is_open_ended(self) -> None:
        # None means "no upper bound" — validator skips the check.
        q = TemporalQuery(tick_start=42, tick_end=None)
        assert q.tick_end is None

    # M1 — graph depth bounds
    @pytest.mark.parametrize("bad_depth", [0, -1, 11, 100])
    def test_negative_graph_depth_bounds(self, bad_depth: int) -> None:
        with pytest.raises(ValidationError):
            GraphQuery(entity="e", depth=bad_depth)

    # M2 — score/weight ranges enforced on every variant that carries them
    @pytest.mark.parametrize("bad_score", [-0.1, 1.01, -1.0])
    def test_negative_semantic_min_score_bounds(self, bad_score: float) -> None:
        with pytest.raises(ValidationError):
            SemanticQuery(text="x", min_score=bad_score)

    @pytest.mark.parametrize("bad_score", [-0.1, 1.01])
    def test_negative_importance_min_importance_bounds(self, bad_score: float) -> None:
        with pytest.raises(ValidationError):
            ImportanceQuery(min_importance=bad_score)

    @pytest.mark.parametrize(
        "weight_name", ["semantic_weight", "recency_weight", "importance_weight"]
    )
    @pytest.mark.parametrize("bad_weight", [-0.1, 1.01])
    def test_negative_hybrid_weights_bounds(self, weight_name: str, bad_weight: float) -> None:
        with pytest.raises(ValidationError):
            HybridQuery(semantic_text="x", **{weight_name: bad_weight})

    # Min-length string fields — empty text/entity/keys rejected
    def test_negative_structured_empty_keys_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuredQuery(keys=[])

    def test_negative_semantic_empty_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SemanticQuery(text="")

    def test_negative_graph_empty_entity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GraphQuery(entity="")

    def test_negative_hybrid_empty_semantic_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HybridQuery(semantic_text="")


class TestMemoryRecall:
    def test_negative_requires_all_fields(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecall()  # type: ignore[call-arg]

    def test_positive_empty_records(self) -> None:
        r = MemoryRecall(query_id="q1", records=[], total_matched=0, truncated=False)
        assert r.records == []
        assert r.truncated is False

    # N3 — truncated invariant enforcement
    def test_negative_truncated_disagrees_with_counts(self) -> None:
        # Claims truncation but records equal total — contradiction.
        with pytest.raises(ValidationError, match="truncated"):
            MemoryRecall(
                query_id="q",
                records=[],
                total_matched=0,
                truncated=True,
            )

    def test_negative_not_truncated_but_records_under_total(self) -> None:
        rec = MemoryRecord(**_base_record_kwargs())
        with pytest.raises(ValidationError, match="truncated"):
            MemoryRecall(
                query_id="q",
                records=[rec],
                total_matched=5,
                truncated=False,
            )

    def test_negative_records_exceed_total_matched(self) -> None:
        rec = MemoryRecord(**_base_record_kwargs())
        with pytest.raises(ValidationError, match="total_matched"):
            MemoryRecall(
                query_id="q",
                records=[rec, rec],
                total_matched=1,
                truncated=True,
            )

    def test_negative_empty_query_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecall(query_id="", records=[], total_matched=0, truncated=False)

    def test_positive_truncated_consistent(self) -> None:
        rec = MemoryRecord(**_base_record_kwargs())
        r = MemoryRecall(
            query_id="q",
            records=[rec],
            total_matched=5,
            truncated=True,
        )
        assert r.truncated is True


class TestMemoryWrite:
    def test_negative_requires_content(self) -> None:
        with pytest.raises(ValidationError):
            MemoryWrite(kind="episodic", importance=0.5)  # type: ignore[call-arg]

    def test_negative_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryWrite(content="", kind="episodic", importance=0.5)

    # M1 — importance range enforcement symmetric with MemoryRecord (C1)
    @pytest.mark.parametrize("bad_importance", [-0.1, 1.01, -5.0, 42.0])
    def test_negative_importance_out_of_range_rejected(self, bad_importance: float) -> None:
        with pytest.raises(ValidationError):
            MemoryWrite(content="x", kind="episodic", importance=bad_importance)

    def test_default_source_is_explicit(self) -> None:
        w = MemoryWrite(content="x", kind="episodic", importance=0.5)
        assert w.source == "explicit"
        assert w.tags == []


class TestMemoryAccessDenied:
    """M5 — exception is importable from core.memory_types (not engines).

    Protocol-exposed exceptions live in core; this anchors the
    contract that consumers can catch the exception without loading
    any engine package.
    """

    def test_exception_is_raised_with_context(self) -> None:
        exc = MemoryAccessDenied(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-2",
            op="read",
        )
        assert exc.caller == ActorId("npc-1")
        assert exc.target_scope == "actor"
        assert exc.target_owner == "npc-2"
        assert exc.op == "read"
        # Message embeds context for debugging
        assert "npc-1" in str(exc)
        assert "npc-2" in str(exc)
        assert "read" in str(exc)

    def test_exception_is_catchable(self) -> None:
        with pytest.raises(MemoryAccessDenied):
            raise MemoryAccessDenied(
                caller=ActorId("a"),
                target_scope="actor",
                target_owner="b",
                op="write",
            )
