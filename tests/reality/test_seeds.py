"""Tests for terrarium.reality.seeds -- Seed model.

Tests creation, immutability, and default values for the generic Seed model.
The Seed model uses description + entity_hints + actor_hints (no domain-specific fields).
"""

from __future__ import annotations

import pytest

from terrarium.reality.seeds import Seed


class TestSeedCreation:
    """A Seed can be created with a description and optional hint dicts."""

    def test_seed_creation(self) -> None:
        seed = Seed(description="Customer disputes a legitimate charge")
        assert seed.description == "Customer disputes a legitimate charge"


class TestSeedFrozen:
    """Seed model is frozen and cannot be mutated after creation."""

    def test_seed_frozen(self) -> None:
        seed = Seed(description="A scenario")
        with pytest.raises(Exception):
            seed.description = "Changed"  # type: ignore[misc]


class TestEmptyHints:
    """Default hint dicts are empty."""

    def test_empty_hints(self) -> None:
        seed = Seed(description="Simple scenario")
        assert seed.entity_hints == {}
        assert seed.actor_hints == {}


class TestSeedWithHints:
    """Seed can be created with populated entity_hints and actor_hints."""

    def test_seed_with_hints(self) -> None:
        seed = Seed(
            description="Complex scenario",
            entity_hints={"customer_type": "enterprise", "region": "EMEA"},
            actor_hints={"personality": "aggressive", "experience": "senior"},
        )
        assert seed.entity_hints["customer_type"] == "enterprise"
        assert seed.entity_hints["region"] == "EMEA"
        assert seed.actor_hints["personality"] == "aggressive"
        assert seed.actor_hints["experience"] == "senior"
