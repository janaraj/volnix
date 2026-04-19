"""Unit tests for the recall-harness metric helpers.

Purely synthetic inputs so the metric math is provably correct
before we feed it live retrieval results. If recall_at_k is off by
one here, the whole harness lies.
"""

from __future__ import annotations

import pytest

from tests.engines.memory.recall.metrics import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)


class TestRecallAtK:
    def test_empty_relevant_returns_zero(self) -> None:
        assert recall_at_k(["r1", "r2"], set(), 5) == 0.0

    def test_empty_retrieved_returns_zero(self) -> None:
        assert recall_at_k([], {"r1"}, 5) == 0.0

    def test_full_hit(self) -> None:
        assert recall_at_k(["r1", "r2"], {"r1", "r2"}, 5) == 1.0

    def test_partial_hit(self) -> None:
        assert recall_at_k(["r1", "x"], {"r1", "r2"}, 5) == 0.5

    def test_beyond_k_not_counted(self) -> None:
        # Relevant hit at position 6 when k=5 — must not count.
        retrieved = ["x"] * 5 + ["r1"]
        assert recall_at_k(retrieved, {"r1"}, 5) == 0.0

    def test_k_zero_returns_zero(self) -> None:
        assert recall_at_k(["r1"], {"r1"}, 0) == 0.0


class TestPrecisionAtK:
    def test_k_zero_returns_zero(self) -> None:
        assert precision_at_k(["r1"], {"r1"}, 0) == 0.0

    def test_empty_retrieved_returns_zero(self) -> None:
        assert precision_at_k([], {"r1"}, 5) == 0.0

    def test_all_relevant_precision_one(self) -> None:
        assert precision_at_k(["r1", "r2"], {"r1", "r2"}, 2) == 1.0

    def test_half_relevant_precision_half(self) -> None:
        assert precision_at_k(["r1", "x"], {"r1"}, 2) == 0.5

    def test_only_first_k_counted(self) -> None:
        # 3 retrieved, k=2, 1 relevant in first 2 → 0.5.
        assert precision_at_k(["x", "r1", "r2"], {"r1", "r2"}, 2) == 0.5


class TestMeanReciprocalRank:
    def test_no_hit_returns_zero(self) -> None:
        assert mean_reciprocal_rank(["x", "y"], {"r1"}) == 0.0

    def test_hit_at_position_one(self) -> None:
        assert mean_reciprocal_rank(["r1", "x"], {"r1"}) == 1.0

    def test_hit_at_position_three(self) -> None:
        # RR = 1/3 when first hit is at rank 3.
        assert mean_reciprocal_rank(["a", "b", "r1"], {"r1"}) == pytest.approx(1 / 3)

    def test_first_hit_wins(self) -> None:
        # Two hits at ranks 1 and 3 — reciprocal rank uses rank 1.
        assert mean_reciprocal_rank(["r1", "x", "r2"], {"r1", "r2"}) == 1.0
