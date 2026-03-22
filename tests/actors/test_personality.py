"""Tests for terrarium.actors.personality -- Personality, FrictionProfile, AdversarialProfile."""

import pytest
from pydantic import ValidationError

from terrarium.actors.personality import (
    AdversarialProfile,
    FrictionProfile,
    Personality,
)


class TestPersonality:
    """Verify Personality model defaults and constraints."""

    def test_personality_defaults(self) -> None:
        """Default Personality has balanced style, 5m response time, empty traits."""
        p = Personality()
        assert p.style == "balanced"
        assert p.response_time == "5m"
        assert p.traits == {}
        assert p.description == ""

    def test_personality_with_domain_traits(self) -> None:
        """Personality accepts arbitrary domain-specific traits via traits dict."""
        p = Personality(traits={"patience": 0.3, "escalation_threshold": "low"})
        assert p.traits["patience"] == 0.3
        assert p.traits["escalation_threshold"] == "low"

    def test_personality_frozen(self) -> None:
        """Personality instances are immutable (frozen model)."""
        p = Personality()
        with pytest.raises(Exception):
            p.style = "aggressive"

    def test_personality_description(self) -> None:
        """Personality carries an NL description field."""
        p = Personality(description="Cautious and methodical support agent")
        assert "Cautious" in p.description


class TestFrictionProfile:
    """Verify FrictionProfile model defaults and validation."""

    def test_friction_profile_defaults(self) -> None:
        """Default FrictionProfile is uncooperative, intensity 30, medium sophistication."""
        fp = FrictionProfile()
        assert fp.category == "uncooperative"
        assert fp.intensity == 30
        assert fp.behaviors == []
        assert fp.sophistication == "medium"

    def test_friction_profile_hostile(self) -> None:
        """FrictionProfile accepts hostile category with behaviors and goal."""
        fp = FrictionProfile(
            category="hostile",
            intensity=80,
            behaviors=["explicit_threats", "system_exploitation"],
            sophistication="high",
            goal="Steal credentials",
        )
        assert fp.category == "hostile"
        assert len(fp.behaviors) == 2
        assert fp.goal == "Steal credentials"

    def test_friction_profile_frozen(self) -> None:
        """FrictionProfile instances are immutable (frozen model)."""
        fp = FrictionProfile()
        with pytest.raises(Exception):
            fp.category = "hostile"

    def test_friction_profile_intensity_bounds(self) -> None:
        """FrictionProfile intensity must be in [0, 100]."""
        with pytest.raises(ValidationError):
            FrictionProfile(intensity=101)
        with pytest.raises(ValidationError):
            FrictionProfile(intensity=-1)

    def test_friction_profile_extensible(self) -> None:
        """FrictionProfile accepts arbitrary domain-specific traits."""
        fp = FrictionProfile(traits={"trigger": "refund_denied"})
        assert fp.traits["trigger"] == "refund_denied"


class TestAdversarialCompat:
    """Verify backward-compatible AdversarialProfile alias."""

    def test_adversarial_creates_friction_profile(self) -> None:
        """AdversarialProfile() returns a FrictionProfile with category='hostile'."""
        ap = AdversarialProfile(intensity=70, sophistication="high")
        assert isinstance(ap, FrictionProfile)
        assert ap.category == "hostile"

    def test_adversarial_default_no_args(self) -> None:
        """AdversarialProfile() with no args defaults to hostile, intensity 30."""
        ap = AdversarialProfile()
        assert ap.category == "hostile"
        assert ap.intensity == 30  # FrictionProfile default
