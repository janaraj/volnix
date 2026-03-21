"""Tests for terrarium.actors.generator -- ActorGenerator async methods."""

import pytest

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.generator import ActorGenerator
from terrarium.actors.personality import Personality
from terrarium.reality.dimensions import WorldConditions


class TestActorGenerator:
    """Verify ActorGenerator personality and actor generation."""

    @pytest.mark.asyncio
    async def test_generate_personalities(self) -> None:
        """Generating personalities populates personality fields on actors."""
        ...

    @pytest.mark.asyncio
    async def test_generate_adversarial_actors(self) -> None:
        """Generating adversarial actors returns the requested count."""
        ...

    @pytest.mark.asyncio
    async def test_generate_human_personality(self) -> None:
        """Generating a human personality returns a valid Personality model."""
        ...
