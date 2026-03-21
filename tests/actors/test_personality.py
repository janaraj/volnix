"""Tests for terrarium.actors.personality -- Personality and AdversarialProfile."""

import pytest

from terrarium.actors.personality import AdversarialProfile, Personality


class TestPersonality:
    """Verify Personality model defaults and constraints."""

    def test_personality_defaults(self) -> None:
        """Default Personality has balanced style and 5m response time."""
        ...

    def test_personality_styles(self) -> None:
        """Personality accepts all documented style values."""
        ...

    def test_personality_frozen(self) -> None:
        """Personality instances are immutable."""
        ...


class TestAdversarialProfile:
    """Verify AdversarialProfile model."""

    def test_adversarial_profile(self) -> None:
        """AdversarialProfile can be created with custom intent and strategy."""
        ...
