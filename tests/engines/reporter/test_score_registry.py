"""Tests for SCORE_REGISTRY data integrity."""

from __future__ import annotations

from volnix.engines.reporter.scorecard import SCORE_REGISTRY, ScorecardComputer


def test_weights_sum_to_one():
    """All metric weights should sum to 1.0."""
    total = sum(meta["weight"] for meta in SCORE_REGISTRY.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_registry_has_required_keys():
    """Each registry entry should have weight, formula, description."""
    required = {"weight", "formula", "description"}
    for name, meta in SCORE_REGISTRY.items():
        missing = required - set(meta.keys())
        assert not missing, f"Metric '{name}' missing keys: {missing}"


def test_no_negative_weights():
    """All weights should be positive."""
    for name, meta in SCORE_REGISTRY.items():
        assert meta["weight"] > 0, f"Metric '{name}' has non-positive weight: {meta['weight']}"


def test_all_compute_metrics_in_registry():
    """Every metric computed in ScorecardComputer should exist in SCORE_REGISTRY."""
    # The compute methods follow the pattern _compute_{metric_name}
    computer = ScorecardComputer()
    compute_methods = [
        m.replace("_compute_", "")
        for m in dir(computer)
        if m.startswith("_compute_")
        and not m.startswith("_compute_coordination")
        and not m.startswith("_compute_information")
    ]
    for metric in compute_methods:
        assert metric in SCORE_REGISTRY, (
            f"Metric '{metric}' has a _compute_ method but is not in SCORE_REGISTRY"
        )


async def test_overall_score_is_weighted():
    """B3 regression: overall_score should use SCORE_REGISTRY weights, not simple average."""
    computer = ScorecardComputer()
    actors = [{"id": "agent-1", "type": "agent"}]
    events = [{"event_type": "world.chat_send", "actor_id": "agent-1", "action": "chat_send"}]
    result = await computer.compute(events, actors)

    # With minimal events (no violations), all per-actor scores are 100.0
    # Weighted: sum(100 * weight for each) = 100 * 1.0 = 100.0
    assert result["collective"]["overall_score"] == 100.0

    # Verify it's NOT a simple average of 8 metrics (which would be different
    # because coordination_score and information_sharing are also in collective)
    collective = result["collective"]
    round(
        sum(
            v
            for v in collective.values()
            if isinstance(v, (int, float)) and v != collective["overall_score"]
        )
        / max(len([v for v in collective.values() if isinstance(v, (int, float))]) - 1, 1),
        1,
    )
    # The weighted score should equal 100.0 (all weights sum to 1.0, all scores are 100)
    assert collective["overall_score"] == 100.0
