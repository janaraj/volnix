"""Personality and adversarial-profile models for world actors.

Personalities govern how human actors behave during simulation --
their response style, speed, strengths, and weaknesses.  Adversarial
profiles describe hostile actors and their strategies.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Personality(BaseModel, frozen=True):
    """Personality traits for a human actor in the world.

    These traits influence how the actor behaves during simulation,
    including response style, timing, and decision-making tendencies.
    """

    style: str = "balanced"            # cautious | aggressive | methodical | creative | balanced
    response_time: str = "5m"          # how quickly they respond
    strengths: list[str] = Field(default_factory=list)    # [thoroughness, policy_knowledge, ...]
    weaknesses: list[str] = Field(default_factory=list)   # [slow_to_decide, ...]
    availability: str | None = None    # "09:00-17:00"


class AdversarialProfile(BaseModel, frozen=True):
    """Profile for adversarial actors (hostile customers, social engineers, etc.).

    Adversarial profiles describe the intent, strategy, and sophistication
    of actors who are deliberately trying to manipulate or exploit the system.
    """

    intent: str = "manipulative"       # manipulative | chaotic | exploitative
    strategy: str = "direct"           # trust_building | social_engineering | brute_force | direct
    sophistication: str = "medium"     # low | medium | high
    goal: str = ""                     # "Get refund on non-refundable charge"
