"""Memory Engine — actor long-term memory (PMF Plan Phase 4B).

Responsibilities:
- Episodic + semantic memory storage keyed by actor or team scope.
- Six retrieval modes (structured, temporal, semantic, importance,
  graph, hybrid) via ``MemoryQuery`` tagged union.
- LLM-driven episodic→semantic consolidation, cadence-configurable.
- Permission-gated cross-scope access with ledgered denials.
- Deterministic across replay (seeded RNG, content-hash embedding
  cache, tick-only timestamps, sorted retrieval tie-breaks).

Public surface:
    from volnix.core.protocols import MemoryEngineProtocol
    from volnix.core.memory_types import (
        MemoryRecord, MemoryRecall, MemoryQuery, MemoryWrite,
        MemoryScope, MemoryKind, MemoryTier, MemorySource,
        MemoryAccessDenied,
    )

The concrete ``MemoryEngine`` is imported only in
``volnix.registry.composition``. Callers depend on the protocol.

Status: in-progress (Step 2 ships ``MemoryConfig`` — this package
stub scaffolds for later steps).
"""

from __future__ import annotations
