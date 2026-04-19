"""Recall/precision/MRR helpers (Phase 4B Step 4b).

Pure functions — no fixtures here so the functions are unit-testable
on synthetic inputs before we feed them real retrieval results. If
``recall_at_k`` is off by one here, the whole harness lies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryMetrics:
    """Per-query rollup used when we want more than just recall."""

    query_id: str
    category: str
    recall_at_1: float
    recall_at_5: float
    precision_at_5: float
    mrr: float


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant records that appear in the top ``k``
    retrieved.

    Boundary cases:
        - empty ``relevant`` or ``k <= 0`` returns ``0.0`` (no signal).
        - more retrieved than ``k`` only counts the first ``k``.
    """
    if not relevant or k <= 0:
        return 0.0
    hit = sum(1 for r in retrieved[:k] if r in relevant)
    return hit / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of the top ``k`` retrieved that are relevant.

    Different from recall: recall divides by total relevant,
    precision divides by ``k``. Both matter — low precision with
    high recall means "we found it but buried it in garbage."
    """
    if k <= 0 or not retrieved:
        return 0.0
    hit = sum(1 for r in retrieved[:k] if r in relevant)
    return hit / k


def mean_reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """Reciprocal rank of the first relevant hit.

    Returns ``1.0`` if the first retrieved is relevant, ``0.5`` if
    at rank 2, etc. ``0.0`` on miss. For a single query this is
    just "reciprocal rank"; averaged across queries it's MRR —
    the harness does the averaging at the test layer.
    """
    for i, r in enumerate(retrieved, start=1):
        if r in relevant:
            return 1.0 / i
    return 0.0
