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
from volnix.core.types import ActorId, MemoryRecordId
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
        # Seeded RNG for deterministic record_id generation (D7-5).
        # Only the explicit-remember path uses this; the Consolidator
        # has its own uuid.uuid4() (D7-6 — known limitation).
        self._rng = random.Random(seed)
        # ``_ledger`` is injected by app.py at wire time (D7-4).
        # Tests may also inject it directly.
        self._ledger: Any = None

    # ------------------------------------------------------------------
    # BaseEngine lifecycle
    # ------------------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Create schema on fresh DB; truncate data if
        ``reset_on_world_start`` is configured (G15, D10-5).

        Step 7 shipped this method without forwarding the flag,
        so ``reset_on_world_start=True`` never fired. Step 10 plumbs
        it; the paired regression test locks the branch.
        """
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
    ) -> MemoryRecordId:
        """Persist a new memory record for ``target_owner``.

        Gated by ``_gate`` — cross-scope writes raise
        ``MemoryAccessDenied`` and log a ledger row.
        """
        await self._gate(caller, target_scope, target_owner, op="write")
        record_id = self._next_record_id()
        record = MemoryRecord(
            record_id=record_id,
            scope=target_scope,
            owner_id=target_owner,
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
    ) -> MemoryRecall:
        """Retrieve records from ``target_owner`` via the configured
        ``Recall`` dispatcher. Gated by ``_gate``."""
        await self._gate(caller, target_scope, target_owner, op="read")
        result = await self._recall.dispatch(target_owner, query, tick=tick)
        await self._record_to_ledger(
            MemoryRecallEntry(
                caller_actor_id=caller,
                target_scope=target_scope,
                target_owner=target_owner,
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
        """Flush-on-demote signal. Step 7 writes the ledger entry
        only (D7-9); Step 8 wires the actual consolidation trigger
        based on ``config.memory.consolidation_triggers``."""
        await self._record_to_ledger(MemoryEvictionEntry(actor_id=actor_id))

    async def hydrate(self, actor_id: ActorId) -> None:
        """Warm-on-promote signal. Step 7 writes the ledger entry
        only (D7-10 — lazy-on-recall is the default)."""
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
        """Deterministic UUID-format record ID (D7-5).

        Uses the engine's seeded ``random.Random`` so two runs with
        the same seed + same remember() call sequence produce
        byte-identical IDs.
        """
        return MemoryRecordId(str(uuid.UUID(int=self._rng.getrandbits(128), version=4)))

    async def _record_to_ledger(self, entry: Any) -> None:
        """No-op when no ledger is wired (test configurations);
        append otherwise. Matches the injection pattern used by
        AgencyEngine, StateEngine, etc."""
        if self._ledger is None:
            return
        await self._ledger.append(entry)
