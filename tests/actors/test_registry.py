"""Tests for terrarium.actors.registry -- ActorRegistry lookup methods."""

import pytest

from terrarium.core.types import ActorId, ActorType
from terrarium.actors.definition import ActorDefinition
from terrarium.actors.registry import ActorRegistry


class TestActorRegistry:
    """Verify ActorRegistry registration and query methods."""

    def test_register_and_get(self) -> None:
        """Registering an actor makes it retrievable by ID."""
        ...

    def test_list_actors(self) -> None:
        """list_actors returns all registered actors."""
        ...

    def test_get_by_role(self) -> None:
        """get_by_role filters actors by their role string."""
        ...

    def test_get_by_type(self) -> None:
        """get_by_type filters actors by ActorType."""
        ...

    def test_get_adversarial(self) -> None:
        """get_adversarial returns only actors with adversarial traits."""
        ...

    def test_get_agents(self) -> None:
        """get_agents returns only actors of type AGENT."""
        ...
