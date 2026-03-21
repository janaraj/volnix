"""Tests for terrarium.actors.definition -- ActorDefinition model."""

import pytest

from terrarium.core.types import ActorId, ActorType
from terrarium.actors.definition import ActorDefinition
from terrarium.actors.personality import Personality


class TestActorDefinition:
    """Verify ActorDefinition creation and field defaults."""

    def test_actor_definition_creation(self) -> None:
        """An ActorDefinition can be created with required fields."""
        ...

    def test_actor_definition_with_personality(self) -> None:
        """An ActorDefinition can include a Personality."""
        ...

    def test_actor_definition_defaults(self) -> None:
        """Optional fields default to None or empty containers."""
        ...
