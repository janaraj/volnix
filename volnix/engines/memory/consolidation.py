"""Episodic → semantic consolidation via LLM distillation
(PMF Plan Phase 4B Step 6).

Reads recent episodic records for an actor, calls the LLM router
to distill them into semantic facts, links ``consolidated_from``
back. Optionally prunes consumed episodes.

Routed via :class:`LLMRouter.route` so budget tracking, retry,
provider selection, and ledger hooks all flow through the existing
stack (G10 of the gap analysis — unified budget accounting).

The Consolidator is stateless-per-call — the caller (Step 7's
MemoryEngine) decides when to fire based on cadence config.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from volnix.core.memory_types import MemoryRecord, content_hash_of
from volnix.core.types import MemoryRecordId
from volnix.engines.memory.store import MemoryStoreProtocol
from volnix.llm.router import LLMRouter
from volnix.llm.types import LLMRequest

logger = logging.getLogger(__name__)


class ConsolidationResult(BaseModel):
    """Frozen summary of one consolidation pass.

    Engine-internal type — the ``MemoryEngineProtocol.consolidate``
    return is typed ``Any`` so this class stays in ``engines/memory``
    and doesn't leak into ``core/``.
    """

    model_config = ConfigDict(frozen=True)

    actor_id: str
    episodic_consumed: int
    semantic_produced: int
    episodic_pruned: int


# ---------------------------------------------------------------------------
# Prompt + schema constants (module-level single source of truth)
# ---------------------------------------------------------------------------

_DISTILL_SYSTEM_PROMPT = """You are a memory consolidator. You will be given a list of episodic memories (timestamped events) belonging to an actor. Your job is to distill them into a small number of SEMANTIC FACTS that summarise preferences, relationships, patterns, or knowledge that would be useful for the actor to recall later.

Return JSON in the form:
{"facts": [{"content": "...", "importance": 0.0-1.0, "tags": ["..."]}]}

Rules:
- Do NOT invent facts not supported by the episodes.
- Each fact should be concise (1-2 sentences).
- Importance: 0.8+ for strong preferences or identity, 0.5 for moderate patterns, 0.2 for weak observations.
- Tags: lowercase, short; used for structured lookup later.
- If no facts can be distilled, return {"facts": []}.
"""

_DISTILL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "minLength": 1},
                    "importance": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content", "importance"],
            },
        },
    },
    "required": ["facts"],
}


class Consolidator:
    """Drives one consolidation pass per call.

    Not a background task — the caller (Step 7's MemoryEngine) decides
    when to fire based on cadence triggers and tick intervals.
    """

    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        llm_router: LLMRouter,
        use_case: str,
        episodic_window: int,
        prune_after_consolidation: bool = True,
        distillation_enabled: bool = True,
        llm_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        if episodic_window < 1:
            raise ValueError(f"episodic_window must be >= 1, got {episodic_window}")
        self._store = store
        self._router = llm_router
        self._use_case = use_case
        self._episodic_window = episodic_window
        self._prune = prune_after_consolidation
        # When false, ``consolidate()`` short-circuits before the LLM
        # call — zero semantic records produced, zero pruned. The
        # MemoryEvictionEntry / consolidate ledger row still lands so
        # operators can distinguish "distiller disabled" from
        # "distiller silently broken". Wired from
        # ``MemoryConfig.distillation_enabled``.
        self._distillation_enabled = distillation_enabled
        # PMF 4B cleanup commit 6 — cap concurrent distill LLM calls.
        # None falls back to "unbounded" (useful for tests that
        # don't care); composition always passes a real semaphore
        # built from ``MemoryConfig.max_concurrent_distill``.
        self._llm_semaphore = llm_semaphore

    async def consolidate(
        self,
        owner_id: str,
        tick: int,
        *,
        force: bool = False,
    ) -> ConsolidationResult:
        """Run one consolidation pass for ``owner_id`` at ``tick``.

        Behavior on LLM errors (graceful degradation — D6-5):
          - Garbage JSON → logged, 0 semantics produced, 0 pruned.
          - Empty facts list → 0 semantics produced, 0 pruned.
          - Network error / provider timeout → LLMRouter handles
            retry; final error becomes empty facts. Caller (Step 7)
            ledgers the attempt regardless.

        ``force=True`` bypasses the empty-episodes short-circuit
        (D6-9) — useful for tests that want to exercise the LLM
        call path with no input.
        """
        episodes = await self._store.list_by_owner(
            owner_id, kind="episodic", limit=self._episodic_window
        )
        if not episodes and not force:
            return ConsolidationResult(
                actor_id=owner_id,
                episodic_consumed=0,
                semantic_produced=0,
                episodic_pruned=0,
            )

        # MemoryConfig.distillation_enabled gate — short-circuits the
        # LLM call path. ``episodic_consumed`` still reports the read
        # so the ledger shows the work the Consolidator observed.
        if not self._distillation_enabled:
            logger.info(
                "Consolidator: distillation_enabled=False for %s — "
                "skipping LLM call; %d episodes observed, 0 produced.",
                owner_id,
                len(episodes),
            )
            return ConsolidationResult(
                actor_id=owner_id,
                episodic_consumed=len(episodes),
                semantic_produced=0,
                episodic_pruned=0,
            )

        facts = await self._distill(episodes, tick=tick)
        produced = await self._insert_semantic_records(owner_id, facts, episodes, tick=tick)

        pruned_count = 0
        if self._prune and produced > 0:
            # Keep the episodic_window most-recent episodes; anything
            # older is eligible for pruning now that it's reflected
            # in semantic memory.
            pruned_ids = await self._store.prune_oldest_episodic(
                owner_id, keep=self._episodic_window
            )
            pruned_count = len(pruned_ids)

        return ConsolidationResult(
            actor_id=owner_id,
            episodic_consumed=len(episodes),
            semantic_produced=produced,
            episodic_pruned=pruned_count,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _distill(self, episodes: list[MemoryRecord], *, tick: int) -> list[dict[str, Any]]:
        """Call the LLM router to distill episodes into facts.

        Determinism (D6-3): episodes sorted by ``record_id`` before
        prompt construction so the same set produces the same prompt
        regardless of insertion order.

        Concurrency (PMF 4B cleanup commit 6): when a semaphore is
        injected at construction, the LLM call is guarded by it so
        cohort-rotation-driven bursts (K demoted actors → K distill
        calls) don't blow past the configured concurrency cap.
        """
        if self._llm_semaphore is not None:
            async with self._llm_semaphore:
                return await self._distill_inner(episodes, tick=tick)
        return await self._distill_inner(episodes, tick=tick)

    async def _distill_inner(
        self, episodes: list[MemoryRecord], *, tick: int
    ) -> list[dict[str, Any]]:
        ordered = sorted(episodes, key=lambda r: r.record_id)
        request = LLMRequest(
            system_prompt=_DISTILL_SYSTEM_PROMPT,
            user_content=self._build_user_content(ordered, tick=tick),
            output_schema=_DISTILL_OUTPUT_SCHEMA,
            temperature=0.0,  # D6-3 deterministic where the provider honours it
            max_tokens=2000,
        )
        response = await self._router.route(request, engine_name="memory", use_case=self._use_case)
        if response.error:
            logger.warning("Consolidator: distill LLM error: %s", response.error)
            return []
        return self._parse_facts(response.content, response.structured_output)

    def _build_user_content(self, episodes: list[MemoryRecord], *, tick: int) -> str:
        lines = [f"Current tick: {tick}", "Episodic memories:"]
        for e in episodes:
            lines.append(f"- tick={e.created_tick}: {e.content}")
        return "\n".join(lines)

    def _parse_facts(self, content: str, structured: dict | list | None) -> list[dict[str, Any]]:
        """Extract ``facts`` list from the LLM response.

        Tries ``response.structured_output`` first (router-unwrapped
        JSON when ``output_schema`` was honoured), falls back to
        ``json.loads(response.content)``. Rejects malformed shape
        at every layer without crashing.
        """
        payload: Any = structured if structured else None
        if payload is None and content:
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning("Consolidator: failed to parse distill content: %s", e)
                return []
        if not isinstance(payload, dict):
            logger.warning(
                "Consolidator: distill payload is not a dict (got %s)",
                type(payload).__name__,
            )
            return []
        facts = payload.get("facts", [])
        if not isinstance(facts, list):
            logger.warning("Consolidator: 'facts' is not a list")
            return []
        return [f for f in facts if isinstance(f, dict) and "content" in f]

    async def _insert_semantic_records(
        self,
        owner_id: str,
        facts: list[dict[str, Any]],
        episodes: list[MemoryRecord],
        *,
        tick: int,
    ) -> int:
        """Materialise facts as ``MemoryRecord`` rows.

        D6-7: ``consolidated_from`` links back to every consumed
        episode (we can't tell which contributed to which fact).
        D6-8: importance clamped to ``[0.0, 1.0]`` before
        constructing the record.
        """
        if not facts:
            return 0
        # Determinism: ``consolidated_from`` must be stable across
        # runs. ``list_by_owner`` returns episodes newest-first
        # (created_tick DESC), so raw order is insertion-dependent.
        # Sort by record_id ASC for a deterministic provenance list.
        source_ids = sorted((e.record_id for e in episodes), key=lambda rid: str(rid))
        scope = episodes[0].scope if episodes else "actor"
        produced = 0
        for fact in facts:
            content = str(fact.get("content", "")).strip()
            if not content:
                continue
            raw_importance = float(fact.get("importance", 0.5))
            importance = max(0.0, min(1.0, raw_importance))
            if importance != raw_importance:
                logger.info(
                    "Consolidator: clamped importance %r -> %r (D6-8)",
                    raw_importance,
                    importance,
                )
            tags = list(fact.get("tags", []))
            tags = [str(t) for t in tags if isinstance(t, str)]
            try:
                record = MemoryRecord(
                    record_id=MemoryRecordId(f"semantic-{uuid.uuid4().hex}"),
                    scope=scope,
                    owner_id=owner_id,
                    kind="semantic",
                    tier="tier2",
                    source="consolidated",
                    content=content,
                    content_hash=content_hash_of(content),
                    importance=importance,
                    tags=tags,
                    created_tick=tick,
                    consolidated_from=source_ids,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Consolidator: skip invalid fact (%s): %r",
                    type(e).__name__,
                    content[:80],
                )
                continue
            await self._store.insert(record)
            produced += 1
        return produced
