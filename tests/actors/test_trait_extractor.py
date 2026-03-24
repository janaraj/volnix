"""Tests for deterministic trait extraction from ActorDefinition."""

from __future__ import annotations

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.personality import FrictionProfile, Personality
from terrarium.actors.state import ActorBehaviorTraits
from terrarium.actors.trait_extractor import extract_behavior_traits
from terrarium.core.types import ActorId, ActorType


def _make_actor(**kwargs) -> ActorDefinition:
    defaults = {
        "id": ActorId("test-actor"),
        "type": ActorType.HUMAN,
        "role": "support_agent",
    }
    defaults.update(kwargs)
    return ActorDefinition(**defaults)


def test_default_traits():
    """An actor with no friction/personality should get neutral defaults."""
    actor = _make_actor()
    traits = extract_behavior_traits(actor)
    assert isinstance(traits, ActorBehaviorTraits)
    assert traits.cooperation_level == 0.5
    assert traits.deception_risk == 0.0
    assert traits.authority_level == 0.0
    assert traits.stakes_level == 0.3
    assert traits.ambient_activity_rate == 0.1


def test_friction_uncooperative():
    """Uncooperative friction profile should lower cooperation."""
    actor = _make_actor(
        friction_profile=FrictionProfile(category="uncooperative", intensity=50),
    )
    traits = extract_behavior_traits(actor)
    assert traits.cooperation_level < 0.5
    assert traits.deception_risk > 0.0


def test_friction_deceptive():
    """Deceptive friction profile should raise deception risk."""
    actor = _make_actor(
        friction_profile=FrictionProfile(category="deceptive", intensity=80),
    )
    traits = extract_behavior_traits(actor)
    assert traits.deception_risk > 0.5


def test_friction_hostile():
    """Hostile friction profile should yield low cooperation."""
    actor = _make_actor(
        friction_profile=FrictionProfile(category="hostile", intensity=60),
    )
    traits = extract_behavior_traits(actor)
    assert traits.cooperation_level < 0.2


def test_permissions_authority():
    """Write-all + read-all permissions should yield high authority."""
    actor = _make_actor(permissions={"read": "all", "write": "all"})
    traits = extract_behavior_traits(actor)
    assert traits.authority_level == 0.9


def test_personality_hint_keywords():
    """Keywords in personality_hint should influence traits."""
    actor = _make_actor(personality_hint="proactive, high-stakes manager")
    traits = extract_behavior_traits(actor)
    assert traits.ambient_activity_rate >= 0.4
    assert traits.stakes_level >= 0.7
    assert traits.authority_level >= 0.6


def test_metadata_overrides():
    """Metadata stakes and authority_level should override defaults."""
    actor = _make_actor(metadata={"stakes": 0.9, "authority_level": 0.8})
    traits = extract_behavior_traits(actor)
    assert traits.stakes_level == 0.9
    assert traits.authority_level == 0.8


def test_traits_are_frozen():
    """ActorBehaviorTraits should be frozen (immutable)."""
    actor = _make_actor()
    traits = extract_behavior_traits(actor)
    try:
        traits.cooperation_level = 0.99
        assert False, "Should have raised"
    except (AttributeError, TypeError, ValueError):
        pass


def test_deterministic():
    """Same input should produce same output (no randomness)."""
    actor = _make_actor(
        friction_profile=FrictionProfile(category="deceptive", intensity=40),
        personality_hint="busy executive",
    )
    t1 = extract_behavior_traits(actor)
    t2 = extract_behavior_traits(actor)
    assert t1 == t2


def test_personality_style_aggressive():
    """Aggressive personality style should increase ambient activity."""
    actor = _make_actor(
        personality=Personality(style="aggressive"),
    )
    traits = extract_behavior_traits(actor)
    assert traits.ambient_activity_rate >= 0.4
    assert traits.cooperation_level < 0.5
