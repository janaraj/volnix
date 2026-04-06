"""Tests for volnix.actors.definition -- ActorDefinition model."""

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.actors.personality import FrictionProfile, Personality
from volnix.core.types import ActorId, ActorType


class TestActorDefinition:
    """Verify ActorDefinition creation, defaults, and frozen model behavior."""

    def test_required_fields(self) -> None:
        """An ActorDefinition requires id, type, and role."""
        actor = ActorDefinition(
            id=ActorId("a1"),
            type=ActorType.HUMAN,
            role="customer",
        )
        assert actor.id == ActorId("a1")
        assert actor.type == ActorType.HUMAN
        assert actor.role == "customer"

    def test_with_personality(self) -> None:
        """An ActorDefinition can carry a Personality."""
        p = Personality(style="cautious", description="Careful thinker")
        actor = ActorDefinition(
            id=ActorId("a2"),
            type=ActorType.HUMAN,
            role="customer",
            personality=p,
        )
        assert actor.personality is not None
        assert actor.personality.style == "cautious"

    def test_with_friction_profile(self) -> None:
        """An ActorDefinition can carry a FrictionProfile."""
        fp = FrictionProfile(category="hostile", intensity=80)
        actor = ActorDefinition(
            id=ActorId("a3"),
            type=ActorType.HUMAN,
            role="customer",
            friction_profile=fp,
        )
        assert actor.friction_profile is not None
        assert actor.friction_profile.category == "hostile"

    def test_metadata_extensibility(self) -> None:
        """metadata dict accepts arbitrary domain-specific keys."""
        actor = ActorDefinition(
            id=ActorId("a4"),
            type=ActorType.HUMAN,
            role="customer",
            metadata={"priority": "vip", "language": "en"},
        )
        assert actor.metadata["priority"] == "vip"
        assert actor.metadata["language"] == "en"

    def test_personality_hint(self) -> None:
        """personality_hint carries raw YAML personality text for LLM."""
        actor = ActorDefinition(
            id=ActorId("a5"),
            type=ActorType.HUMAN,
            role="customer",
            personality_hint="Mix of patient and frustrated users",
        )
        assert actor.personality_hint == "Mix of patient and frustrated users"

    def test_frozen(self) -> None:
        """ActorDefinition instances are immutable (frozen model)."""
        actor = ActorDefinition(
            id=ActorId("a8"),
            type=ActorType.HUMAN,
            role="customer",
        )
        with pytest.raises(Exception):
            actor.role = "agent"

    def test_permissions_budget(self) -> None:
        """permissions and budget dict fields work correctly."""
        actor = ActorDefinition(
            id=ActorId("a9"),
            type=ActorType.AGENT,
            role="support-agent",
            permissions={"can_refund": True, "max_amount": 500},
            budget={"api_calls": 100, "llm_spend_usd": 5.0},
        )
        assert actor.permissions["can_refund"] is True
        assert actor.budget["llm_spend_usd"] == 5.0
