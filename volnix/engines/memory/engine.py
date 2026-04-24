"""MemoryEngine — the 11th Volnix engine (PMF Plan Phase 4B Step 7).

Owns long-term actor memory: episodic + semantic records, keyed by
actor or team scope, gated by an in-engine permission check
(G9 of the gap analysis — cross-actor access raises MemoryAccessDenied
and writes a ledger row).

Step 7 ships the core: public MemoryEngineProtocol surface,
lifecycle hooks, permission gate, ledger writes. Step 8 adds the
CohortRotationEvent subscription + flush-on-demote wiring. Step 10
wires the engine into app.py and composition root.
"""

from __future__ import annotations

import logging
import random
import uuid
from typing import Any, ClassVar

from volnix.core.engine import BaseEngine
from volnix.core.events import CohortRotationEvent
from volnix.core.memory_types import (
    MemoryAccessDenied,
    MemoryQuery,
    MemoryRecall,
    MemoryRecord,
    MemoryScope,
    MemoryWrite,
    content_hash_of,
)
from volnix.core.types import ActorId, MemoryRecordId, SessionId
from volnix.engines.memory.config import MemoryConfig
from volnix.engines.memory.consolidation import ConsolidationResult, Consolidator
from volnix.engines.memory.embedder import EmbedderProtocol
from volnix.engines.memory.recall import Recall
from volnix.engines.memory.store import MemoryStoreProtocol
from volnix.ledger.entries import (
    MemoryAccessDeniedEntry,
    MemoryConsolidationEntry,
    MemoryEvictionEntry,
    MemoryHydrationEntry,
    MemoryRecallEntry,
    MemoryWriteEntry,
)

logger = logging.getLogger(__name__)


class MemoryEngine(BaseEngine):
    """Actor memory engine. Implements ``MemoryEngineProtocol``.

    Invariants:
      - Every public method writes a ledger entry (D7-3).
      - Cross-scope access denied loudly via ``MemoryAccessDenied``
        (D7-2).
      - ``remember()`` produces deterministic record IDs given a
        seeded ``random.Random`` (D7-5).
      - ``consolidate()`` delegates to the injected Consolidator;
        the engine doesn't re-implement distillation.
      - ``recall()`` delegates to the injected Recall dispatcher;
        the engine doesn't re-implement query routing.
    """

    engine_name: ClassVar[str] = "memory"
    # Subscribes to Phase 4A's CohortRotationEvent (Step 8). Per-actor
    # eviction on demote + optional hydration on promote.
    subscriptions: ClassVar[list[str]] = ["cohort.rotated"]
    dependencies: ClassVar[list[str]] = []

    def __init__(
        self,
        *,
        memory_config: MemoryConfig,
        store: MemoryStoreProtocol,
        embedder: EmbedderProtocol,
        recall: Recall,
        consolidator: Consolidator,
        seed: int,
    ) -> None:
        super().__init__()
        self._memory_config = memory_config
        self._store = store
        self._embedder = embedder
        self._recall = recall
        self._consolidator = consolidator
        self._seed = seed
        # ``seed`` retained on the engine for future deterministic
        # pathways that want per-world reproducibility; the explicit-
        # remember path now generates record IDs via ``uuid.uuid4()``
        # (see ``_next_record_id``) to align with the Consolidator
        # and avoid cross-run UNIQUE-constraint collisions when
        # ``reset_on_world_start=False`` lets memory persist across
        # re-serves of the same world
        # (``tnl/session-scoped-memory.tnl``, audit-fold from live
        # validation). The old seeded-RNG contract (D7-5) applied
        # only inside a single run with a fresh DB; session scoping
        # invalidates that scope so we converge on uuid4 for both
        # write paths.
        self._rng = random.Random(seed)
        # ``_ledger`` is injected by app.py at wire time (D7-4).
        # Tests may also inject it directly.
        self._ledger: Any = None

    # ------------------------------------------------------------------
    # BaseEngine lifecycle
    # ------------------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Create schema on fresh DB; run v1 → v2 migration if
        needed; truncate only session-less data if
        ``reset_on_world_start`` is set
        (``tnl/session-scoped-memory.tnl`` — legacy compat).

        Emits exactly one deprecation warning per engine
        construction when ``reset_on_world_start=True`` because
        session scoping replaces it as the isolation mechanism.
        """
        if self._memory_config.reset_on_world_start:
            logger.warning(
                "MemoryConfig.reset_on_world_start is deprecated — session "
                "scoping is the supported isolation mechanism. "
                "This flag will be removed in 0.3.0. Set "
                "``reset_on_world_start=False`` (the new default) to silence "
                "this warning; cross-session isolation is preserved by "
                "session-id scoping regardless of this flag's value."
            )
        await self._store.initialize(reset=self._memory_config.reset_on_world_start)

    async def _on_start(self) -> None:
        """Optionally warm the embedder on start (D7-8)."""
        from volnix.engines.memory.embedder import FTS5Embedder

        # FTS5 embedder has no cold-start cost; skip. Use isinstance
        # rather than a string-literal provider_id compare so a future
        # FTS5V2Embedder inherits the skip automatically.
        if isinstance(self._embedder, FTS5Embedder):
            return
        # Step 13's dense embedders do a model-load on first embed().
        # Calling once at start amortises the cost off the hot path.
        from volnix.llm.types import EmbeddingRequest

        try:
            await self._embedder.embed(EmbeddingRequest(texts=["_warmup_"]))
        except Exception as e:  # noqa: BLE001
            logger.warning("MemoryEngine: embedder warmup failed: %s", e)

    async def _handle_event(self, event: Any) -> None:
        """Dispatch subscribed bus events.

        ``cohort.rotated`` (from Phase 4A's
        ``CohortManager.rotate_cohort``) triggers per-actor eviction
        + optional consolidation on demote, and optional hydration
        on promote. Any other event type logs at debug (defence-
        in-depth — the base class only routes subscribed topics
        here anyway).
        """
        if isinstance(event, CohortRotationEvent):
            await self._on_cohort_rotated(event)
            return
        logger.debug(
            "MemoryEngine received unexpected event type: %s",
            type(event).__name__,
        )

    async def _on_cohort_rotated(self, event: CohortRotationEvent) -> None:
        """Per-actor flush on demote + optional hydrate on promote.

        Per D8-5, a failure for one actor is logged and does not
        block processing of the rest of the batch.
        """
        should_consolidate_on_eviction = "on_eviction" in self._memory_config.consolidation_triggers
        hydrate_on_promote = self._memory_config.hydrate_on_promote

        # Demote: always evict; conditionally consolidate.
        for actor_id in event.demoted_ids:
            try:
                await self.evict(actor_id)
                if should_consolidate_on_eviction:
                    await self.consolidate(actor_id, tick=event.tick)
            except Exception as e:  # noqa: BLE001 — isolate per-actor failures
                logger.warning(
                    "MemoryEngine: evict/consolidate failed for %s: %s",
                    actor_id,
                    e,
                )

        # Promote: hydrate only if configured.
        if hydrate_on_promote:
            for actor_id in event.promoted_ids:
                try:
                    await self.hydrate(actor_id)
                except Exception as e:  # noqa: BLE001 — isolate per-actor failures
                    logger.warning(
                        "MemoryEngine: hydrate failed for %s: %s",
                        actor_id,
                        e,
                    )

    # ------------------------------------------------------------------
    # MemoryEngineProtocol surface
    # ------------------------------------------------------------------

    async def remember(
        self,
        *,
        caller: ActorId,
        target_scope: MemoryScope,
        target_owner: str,
        write: MemoryWrite,
        tick: int,
        session_id: SessionId | None = None,
    ) -> MemoryRecordId:
        """Persist a new memory record for ``target_owner``, scoped
        to ``session_id`` (``tnl/session-scoped-memory.tnl``).

        Gated by ``_gate`` — cross-scope writes raise
        ``MemoryAccessDenied`` and log a ledger row.
        """
        await self._gate(caller, target_scope, target_owner, op="write")
        record_id = self._next_record_id()
        record = MemoryRecord(
            record_id=record_id,
            scope=target_scope,
            owner_id=target_owner,
            session_id=session_id,
            kind=write.kind,
            tier="tier2",
            source=write.source,
            content=write.content,
            content_hash=content_hash_of(write.content),
            importance=write.importance,
            tags=list(write.tags),
            created_tick=tick,
            consolidated_from=None,
            metadata=dict(write.metadata),
        )
        await self._store.insert(record)
        await self._record_to_ledger(
            MemoryWriteEntry(
                caller_actor_id=caller,
                target_scope=target_scope,
                target_owner=target_owner,
                session_id=session_id,
                record_id=str(record_id),
                kind=write.kind,
                source=write.source,
                importance=write.importance,
                tick=tick,
            )
        )
        return record_id

    async def recall(
        self,
        *,
        caller: ActorId,
        target_scope: MemoryScope,
        target_owner: str,
        query: MemoryQuery,
        tick: int,
        session_id: SessionId | None = None,
    ) -> MemoryRecall:
        """Retrieve records from ``target_owner`` scoped to
        ``session_id`` via the configured ``Recall`` dispatcher.
        Gated by ``_gate`` (``tnl/session-scoped-memory.tnl``)."""
        await self._gate(caller, target_scope, target_owner, op="read")
        result = await self._recall.dispatch(target_owner, query, tick=tick, session_id=session_id)
        await self._record_to_ledger(
            MemoryRecallEntry(
                caller_actor_id=caller,
                target_scope=target_scope,
                target_owner=target_owner,
                session_id=session_id,
                query_mode=query.mode,
                query_id=result.query_id,
                result_count=len(result.records),
                tick=tick,
            )
        )
        return result

    async def consolidate(
        self,
        actor_id: ActorId,
        *,
        force: bool = False,
        tick: int = 0,
    ) -> ConsolidationResult:
        """Run one consolidation pass via the injected Consolidator.

        No cross-scope gate here — consolidation is always same-scope
        (the engine wouldn't have access to another actor's memory
        to consolidate).
        """
        result = await self._consolidator.consolidate(str(actor_id), tick, force=force)
        await self._record_to_ledger(
            MemoryConsolidationEntry(
                actor_id=actor_id,
                episodic_consumed=result.episodic_consumed,
                semantic_produced=result.semantic_produced,
                episodic_pruned=result.episodic_pruned,
                tick=tick,
            )
        )
        return result

    async def evict(self, actor_id: ActorId) -> None:
        """Flush-on-demote signal. Aggressively trims the actor's
        tier-2 episodic buffer to half the configured cap — the
        cohort considers them dormant, so freeing memory footprint
        dominates over preserving breadth of recall. Tier-1 records
        (immutable pack-authored beliefs) are exempt per the store's
        trimming rules. Consolidation is a separate concern driven by
        ``consolidation_triggers`` in ``_on_cohort_rotated``.

        Writes ``MemoryEvictionEntry`` to the ledger regardless of
        how many records were actually dropped — the ledger row is
        the "eviction intent" signal, trimming is the mechanism.

        Session scoping (``tnl/session-scoped-memory.tnl`` non-goal):
        only the ``session_id IS NULL`` slice is trimmed. Session-
        scoped episodic records accumulate indefinitely across
        cohort demotes; per-session eviction lands when a Rehearse
        consumer exercises cohort rotation with sessions.
        Audit-fold M2.
        """
        keep = max(1, self._memory_config.max_episodic_per_actor // 2)
        try:
            pruned = await self._store.prune_oldest_episodic(str(actor_id), keep=keep)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MemoryEngine.evict: prune failed for %s: %s", actor_id, exc)
            pruned = []
        await self._record_to_ledger(MemoryEvictionEntry(actor_id=actor_id))
        if pruned:
            logger.debug(
                "MemoryEngine.evict: trimmed %d episodic records for %s",
                len(pruned),
                actor_id,
            )

    async def hydrate(self, actor_id: ActorId) -> None:
        """Warm-on-promote signal. Pre-embeds the actor's most
        recent semantic+episodic records so the first post-promote
        recall hits a warm cache. When using ``FTS5Embedder``, this
        is a no-op (no vectors to cache) — the ledger entry still
        lands so operators can tell "hydrate fired, just nothing to
        warm" apart from "hydrate never fired".

        Lazy-on-first-recall remains the default (D7-10);
        ``hydrate_on_promote=True`` opts an actor into this eager
        path from ``_on_cohort_rotated``.

        Session scoping (``tnl/session-scoped-memory.tnl`` non-goal):
        ``hydrate`` is called from ``_on_cohort_rotated`` which the
        TNL explicitly leaves session-agnostic. This method reads
        only the ``session_id IS NULL`` slice; session-scoped
        records do not receive eager cache-warm on promote. Callers
        that need session-aware hydration should invoke recall
        directly with an explicit ``session_id``. Audit-fold H1.
        """
        from volnix.engines.memory.embedder import FTS5Embedder
        from volnix.llm.types import EmbeddingRequest

        if not isinstance(self._embedder, FTS5Embedder):
            try:
                records = await self._store.list_by_owner(
                    str(actor_id),
                    limit=self._memory_config.default_recall_top_k,
                )
                if records:
                    # Embed will populate the content-hash cache via
                    # store hooks on the dense-recall code path; here
                    # we force-seed the cache directly to avoid
                    # depending on a recall firing first.
                    provider_id = self._embedder.provider_id
                    # Cache misses only — avoid re-embedding already
                    # cached content.
                    misses_texts: list[str] = []
                    miss_records: list = []
                    for rec in records:
                        cached = await self._store.embedding_cache_get(
                            rec.content_hash, provider_id
                        )
                        if cached is None:
                            misses_texts.append(rec.content)
                            miss_records.append(rec)
                    if misses_texts:
                        import numpy as np

                        resp = await self._embedder.embed(EmbeddingRequest(texts=misses_texts))
                        for rec, vec in zip(miss_records, resp.vectors, strict=True):
                            blob = np.asarray(vec, dtype=np.float32).tobytes()
                            await self._store.embedding_cache_put(
                                rec.content_hash, provider_id, blob
                            )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MemoryEngine.hydrate: cache warm failed for %s: %s",
                    actor_id,
                    exc,
                )
        await self._record_to_ledger(MemoryHydrationEntry(actor_id=actor_id))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _gate(
        self,
        caller: ActorId,
        scope: MemoryScope,
        target_owner: str,
        *,
        op: str,
    ) -> None:
        """In-engine permission gate (D7-2).

        Rules:
          - Actor scope: ``caller == target_owner`` → pass.
          - Actor cross-scope: deny.
          - Team scope: always deny in 4B (exercised in 4D).

        Denial writes ``MemoryAccessDeniedEntry`` and raises
        ``MemoryAccessDenied``. Never silent.
        """
        allowed = False
        if scope == "actor":
            allowed = str(caller) == target_owner
        # team scope stays False in 4B
        if allowed:
            return
        await self._record_to_ledger(
            MemoryAccessDeniedEntry(
                caller_actor_id=caller,
                target_scope=scope,
                target_owner=target_owner,
                op=op,
            )
        )
        raise MemoryAccessDenied(
            caller=caller,
            target_scope=scope,
            target_owner=target_owner,
            op=op,
        )

    def _next_record_id(self) -> MemoryRecordId:
        """Globally unique record ID via ``uuid.uuid4()``.

        Previously used a seeded RNG for per-run replay determinism
        (D7-5), but that contract broke the moment
        ``reset_on_world_start=False`` became the default under
        session-scoped memory: re-serving the same world at the
        same seed reproduces the UUID sequence, colliding against
        persisted rows. Aligns with ``Consolidator`` which already
        uses ``uuid.uuid4()`` (D7-6 — previously documented as a
        known inconsistency). Live-validation finding from
        ``tnl/session-scoped-memory.tnl`` drove this change.
        """
        return MemoryRecordId(str(uuid.uuid4()))

    async def _record_to_ledger(self, entry: Any) -> None:
        """No-op when no ledger is wired (test configurations);
        append otherwise. Matches the injection pattern used by
        AgencyEngine, StateEngine, etc."""
        if self._ledger is None:
            return
        await self._ledger.append(entry)
