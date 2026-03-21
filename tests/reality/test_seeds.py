"""Tests for terrarium.reality.seeds -- Seed model and SeedProcessor."""

import pytest

from terrarium.reality.seeds import Seed, SeedProcessor


class TestSeedModel:
    """Verify the Seed Pydantic model."""

    def test_seed_model_creation(self) -> None:
        """A Seed can be created with a description and optional fields."""
        ...


class TestSeedProcessor:
    """Verify SeedProcessor methods."""

    @pytest.mark.asyncio
    async def test_process_seeds_inserts_entities(self) -> None:
        """Processing seeds adds entries to the entity dictionary."""
        ...

    @pytest.mark.asyncio
    async def test_expand_nl_seed(self) -> None:
        """A natural-language description is expanded into a structured Seed."""
        ...

    def test_validate_seeds(self) -> None:
        """Validation returns errors for seeds inconsistent with schemas."""
        ...
