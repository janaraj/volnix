"""Protocol-exposed memory types for the Volnix MemoryEngine.

These types cross the engine boundary — callers (``NPCActivator``,
agent activators, research primitives) depend on them via
``MemoryEngineProtocol`` in :mod:`volnix.core.protocols`. Engine-internal
types (``Vector``, ``ConsolidationResult``, internal exceptions)
live in :mod:`volnix.engines.memory.types`.

Per ``DESIGN_PRINCIPLES`` (G2 of the Phase 4B gap analysis):
``volnix/core/*`` must not import from ``volnix/engines/*``. Every
protocol surface sources its value types from here so no circular
dependency ever forms.

See:
- Phase 4B plan: ``internal_docs/pmf/phase-4b-memory-engine.md``
- Approved corrections: ``.claude/plans/the-pdf-is-the-wiggly-matsumoto.md``
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from volnix.core.types import ActorId, MemoryRecordId

# Bounds used by Field validators below. Kept as module-level
# constants so tests and the store layer can reason about them without
# hardcoding.
_MAX_TOP_K: int = 1000
_MAX_LIMIT: int = 10_000
_MAX_GRAPH_DEPTH: int = 10
_MAX_QUERY_TEXT_LEN: int = 10_000  # M4 of Step 3 review: cap FTS5 query size
_CONTENT_HASH_PATTERN: str = r"^[a-f0-9]{64}$"


def content_hash_of(text: str) -> str:
    """Canonical SHA-256 hex digest used for ``MemoryRecord.content_hash``
    and the embedding cache key.

    Single source of truth — every caller (engine, store, tests) that
    computes a content hash goes through this function so the algorithm
    and encoding match. Change this and ``MemoryRecord`` validation
    simultaneously, never one without the other.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Discriminator literals
# ---------------------------------------------------------------------------

MemoryScope = Literal["actor", "team"]
"""Ownership scope of a memory record.

``actor`` — private to a single actor. ``team`` — shared across
members of a team (plumbed in 4B, exercised in 4D).
"""

MemoryKind = Literal["episodic", "semantic"]
"""Episodic = specific events (what happened).
Semantic = derived facts (what's true)."""

MemoryTier = Literal["tier1", "tier2"]
"""Tier 1 = hand-authored pack fixture, immutable at runtime.
Tier 2 = runtime-accumulated, distilled or explicitly remembered."""

MemorySource = Literal["implicit", "explicit", "consolidated", "pack_fixture"]
"""How the record entered memory:

- ``implicit`` — written by the activator's post-activation distiller.
- ``explicit`` — agent/NPC called the ``remember`` tool.
- ``consolidated`` — produced by the periodic consolidation pass.
- ``pack_fixture`` — Tier 1 fixture loaded at world compile time.
"""


# ---------------------------------------------------------------------------
# Value object: MemoryRecord
# ---------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """A single memory record. Crosses the protocol boundary, so it
    lives in core rather than engines.

    Frozen — once written, never mutated. The caller who reads a
    record cannot tamper with what the store holds.

    **Determinism note for store layer (Step 3):** ``metadata`` is a
    Python dict which is insertion-ordered but not automatically
    serialised with sorted keys. For same-seed replay determinism,
    the store must serialise metadata with ``json.dumps(..., sort_keys=True)``
    before hashing or writing. Tracked as gap D4 in Step 1 review.
    """

    model_config = ConfigDict(frozen=True)

    record_id: MemoryRecordId
    scope: MemoryScope
    owner_id: str
    """Stringified ``ActorId`` (for ``scope="actor"``) or ``TeamId``
    (for ``scope="team"``). Kept as a plain string so the protocol
    doesn't have to reach for a union type here."""

    kind: MemoryKind
    tier: MemoryTier
    source: MemorySource
    content: str
    content_hash: str = Field(pattern=_CONTENT_HASH_PATTERN)
    """SHA-256 hex digest of ``content`` (64 lowercase hex chars).
    Serves as the embedding cache key — identical content ⇒ identical
    vector, always. Typo-accepted hashes silently break cache lookups,
    so the pattern is validated at construction (N1)."""

    importance: float = Field(ge=0.0, le=1.0)
    """0.0–1.0. Used by importance-mode recall and hybrid ranking (C1)."""

    tags: list[str]
    created_tick: int = Field(ge=0)
    """Non-negative tick when the record was created (C2)."""

    consolidated_from: list[MemoryRecordId] | None = None
    """Back-links from a semantic record to the episodic records it
    was distilled from. ``None`` for episodic or pack-fixture records.
    Enforced by ``_validate_consolidation_backlink``."""

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_content_hash_matches_content(self) -> MemoryRecord:
        # C1 of Step 3 review: format-only validation was insufficient.
        # A caller could pass ``content="Hello", content_hash="a"*64``
        # and the record would be accepted — then the embedding cache
        # keys on the stale hash and returns a vector for different
        # content. Here we verify the hash is the canonical digest of
        # the content, catching the caller bug at construction time.
        expected = content_hash_of(self.content)
        if self.content_hash != expected:
            raise ValueError(
                f"MemoryRecord.content_hash ({self.content_hash!r}) does "
                f"not match sha256(content) ({expected!r}). Use "
                f"``content_hash_of(content)`` from "
                f"``volnix.core.memory_types`` rather than computing "
                f"the digest yourself, so the algorithm stays in sync."
            )
        return self

    @model_validator(mode="after")
    def _validate_consolidation_backlink(self) -> MemoryRecord:
        # N2: episodic records MUST NOT carry a consolidated_from link.
        # Back-links are a semantic-record concept — distillation
        # produces semantic records whose provenance traces to
        # episodes. Episode → episode links are nonsense and would
        # break the consolidation audit trail.
        if self.kind == "episodic" and self.consolidated_from is not None:
            raise ValueError(
                "MemoryRecord.consolidated_from must be None for "
                "episodic records; back-links are a semantic-record "
                "concept only."
            )
        # Pack-fixture semantic records are pre-authored, not
        # distilled, so they also must not link back.
        if self.source == "pack_fixture" and self.consolidated_from is not None:
            raise ValueError(
                "MemoryRecord.consolidated_from must be None for pack_fixture records."
            )
        return self


# ---------------------------------------------------------------------------
# MemoryQuery — tagged union
# ---------------------------------------------------------------------------


class StructuredQuery(BaseModel):
    """O(1) structured lookup against semantic records by tag keys."""

    model_config = ConfigDict(frozen=True)
    mode: Literal["structured"] = "structured"
    keys: list[str] = Field(min_length=1)


class TemporalQuery(BaseModel):
    """Records within a tick window, sorted newest-first.

    Cross-field invariant: when ``tick_end`` is provided it must be
    ``>= tick_start``. A backwards range (e.g. ``tick_start=100,
    tick_end=50``) silently matches nothing in ``_temporal`` — that
    is the silent-fail anti-pattern Test Discipline #5 forbids, so
    the validator rejects at construction (C4 of the bug-bounty
    review).
    """

    model_config = ConfigDict(frozen=True)
    mode: Literal["temporal"] = "temporal"
    tick_start: int = Field(ge=0)
    tick_end: int | None = Field(default=None, ge=0)
    limit: int = Field(default=50, ge=1, le=_MAX_LIMIT)

    @model_validator(mode="after")
    def _validate_tick_window(self) -> TemporalQuery:
        if self.tick_end is not None and self.tick_end < self.tick_start:
            raise ValueError(
                f"TemporalQuery: tick_end ({self.tick_end}) must be "
                f">= tick_start ({self.tick_start}). A backwards "
                f"range is almost always a caller bug — use a "
                f"coherent window."
            )
        return self


class SemanticQuery(BaseModel):
    """Top-K by embedding similarity.

    With ``FTS5Embedder`` (default) this becomes BM25 full-text
    search under the hood. With ``sentence-transformers`` or
    ``openai`` it runs vector cosine similarity.
    """

    model_config = ConfigDict(frozen=True)
    mode: Literal["semantic"] = "semantic"
    text: str = Field(min_length=1, max_length=_MAX_QUERY_TEXT_LEN)
    """Query text. Capped at ``_MAX_QUERY_TEXT_LEN`` chars so a caller
    can't DoS the FTS5 MATCH parser with a multi-MB query (M4 of
    Step 3 review)."""

    top_k: int = Field(default=5, ge=1, le=_MAX_TOP_K)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ImportanceQuery(BaseModel):
    """Top-K by distilled importance score."""

    model_config = ConfigDict(frozen=True)
    mode: Literal["importance"] = "importance"
    top_k: int = Field(default=5, ge=1, le=_MAX_TOP_K)
    min_importance: float = Field(default=0.0, ge=0.0, le=1.0)


class GraphQuery(BaseModel):
    """Entity → relationship traversal.

    Phase 4B ships the schema only — the engine raises
    ``NotImplementedError`` when this variant is passed (G11 of the
    gap analysis: fail fast, don't silently return empty). Phase 4D
    provides the concrete traversal.
    """

    model_config = ConfigDict(frozen=True)
    mode: Literal["graph"] = "graph"
    entity: str = Field(min_length=1)
    relationship: str | None = None
    depth: int = Field(default=1, ge=1, le=_MAX_GRAPH_DEPTH)


class HybridQuery(BaseModel):
    """Weighted combination of semantic + recency + importance.

    The modern default for prompt prefill. Weights sum-to-one is
    not enforced — callers may emphasise one signal over the others
    by setting weights explicitly. Individual weights are bounded
    ``[0.0, 1.0]`` (M2).
    """

    model_config = ConfigDict(frozen=True)
    mode: Literal["hybrid"] = "hybrid"
    semantic_text: str = Field(min_length=1, max_length=_MAX_QUERY_TEXT_LEN)
    """See ``SemanticQuery.text`` — capped at ``_MAX_QUERY_TEXT_LEN``
    for the same DoS-guard reason (M4 of Step 3 review)."""

    semantic_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    recency_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    importance_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    top_k: int = Field(default=5, ge=1, le=_MAX_TOP_K)


MemoryQuery = (
    StructuredQuery | TemporalQuery | SemanticQuery | ImportanceQuery | GraphQuery | HybridQuery
)
"""Tagged union of query variants dispatched by mode."""


# ---------------------------------------------------------------------------
# MemoryRecall + MemoryWrite
# ---------------------------------------------------------------------------


class MemoryRecall(BaseModel):
    """Result of a :meth:`MemoryEngineProtocol.recall` call."""

    model_config = ConfigDict(frozen=True)
    query_id: str = Field(min_length=1)
    """Stable identifier for this query, useful for ledger correlation."""

    records: list[MemoryRecord]
    total_matched: int = Field(ge=0)
    truncated: bool

    @model_validator(mode="after")
    def _validate_truncated_invariant(self) -> MemoryRecall:
        # N3: ``truncated`` must agree with the records/total_matched
        # relationship. Silent disagreement hides bugs — e.g. a store
        # returning all matches while claiming truncated=True would
        # make callers paginate for nothing.
        if len(self.records) > self.total_matched:
            raise ValueError(
                f"MemoryRecall: len(records)={len(self.records)} "
                f"exceeds total_matched={self.total_matched}"
            )
        expected_truncated = len(self.records) < self.total_matched
        if self.truncated != expected_truncated:
            raise ValueError(
                f"MemoryRecall.truncated={self.truncated} disagrees "
                f"with records/total_matched ({len(self.records)} "
                f"of {self.total_matched})"
            )
        return self


class MemoryWrite(BaseModel):
    """Input to :meth:`MemoryEngineProtocol.remember`."""

    model_config = ConfigDict(frozen=True)
    content: str = Field(min_length=1)
    kind: MemoryKind
    importance: float = Field(ge=0.0, le=1.0)
    """0.0–1.0 (M1)."""

    tags: list[str] = Field(default_factory=list)
    source: MemorySource = "explicit"
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Exceptions crossing the protocol boundary
# ---------------------------------------------------------------------------


class MemoryAccessDenied(Exception):
    """Raised when a caller is not permitted to access a memory scope.

    Lives in ``core.memory_types`` (not ``engines.memory.types``)
    because the protocol surface references it — exceptions that
    cross the protocol boundary must be importable without loading
    any engine (M5).
    """

    def __init__(
        self,
        caller: ActorId,
        target_scope: str,
        target_owner: str,
        op: str,
    ) -> None:
        super().__init__(
            f"MemoryAccessDenied: caller={caller} target={target_scope}:{target_owner} op={op}"
        )
        self.caller = caller
        self.target_scope = target_scope
        self.target_owner = target_owner
        self.op = op
