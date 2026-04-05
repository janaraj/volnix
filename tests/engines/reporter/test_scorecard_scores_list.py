"""Tests for structured scores list in scorecard output."""

from __future__ import annotations

import pytest

from volnix.engines.reporter.scorecard import SCORE_REGISTRY, ScorecardComputer


@pytest.fixture
def computer():
    return ScorecardComputer()


@pytest.fixture
def actors():
    return [{"id": "agent-1", "type": "agent"}]


async def test_scores_list_present(computer, actors):
    """Per-actor output should contain a 'scores' list."""
    result = await computer.compute([], actors)
    for actor_id, data in result["per_actor"].items():
        assert "scores" in data
        assert isinstance(data["scores"], list)


async def test_scores_list_structure(computer, actors):
    """Each score object should have name, value, weight, formula, description."""
    result = await computer.compute([], actors)
    required_keys = {"name", "value", "weight", "formula", "description"}
    for actor_id, data in result["per_actor"].items():
        for score in data["scores"]:
            assert required_keys.issubset(set(score.keys())), (
                f"Score {score.get('name')} missing keys: {required_keys - set(score.keys())}"
            )


async def test_scores_list_matches_flat_keys(computer, actors):
    """Structured scores should match the backward-compatible flat keys."""
    result = await computer.compute([], actors)
    for actor_id, data in result["per_actor"].items():
        for score in data["scores"]:
            assert score["name"] in data, f"Flat key '{score['name']}' missing"
            assert data[score["name"]] == score["value"], (
                f"Mismatch: flat {data[score['name']]} vs structured {score['value']}"
            )


async def test_scores_list_count(computer, actors):
    """Should have exactly 6 scores per actor (one per SCORE_REGISTRY entry)."""
    result = await computer.compute([], actors)
    for actor_id, data in result["per_actor"].items():
        assert len(data["scores"]) == len(SCORE_REGISTRY)


async def test_collective_has_overall(computer, actors):
    """Collective section should have overall_score."""
    result = await computer.compute([], actors)
    assert "overall_score" in result["collective"]
    assert isinstance(result["collective"]["overall_score"], float)
