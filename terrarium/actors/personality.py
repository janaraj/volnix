"""Personality and friction-profile models for world actors.

Personalities govern how actors behave during simulation -- their response
style, speed, strengths, weaknesses, and extensible domain-specific traits.

:class:`FrictionProfile` replaces the legacy ``AdversarialProfile`` and covers
the full spectrum from uncooperative through deceptive to hostile.  The
:func:`AdversarialProfile` function is kept as a backward-compatible alias that
creates a ``FrictionProfile(category="hostile")``.
"""

from __future__ import annotations

import warnings
from typing import Any, Literal

from pydantic import BaseModel, Field


class Personality(BaseModel, frozen=True):
    """Personality traits for an actor in the world.

    Universal core traits are explicit fields.  Domain-specific traits go
    into the extensible ``traits`` dict so that no subclassing is needed.
    """

    style: str = "balanced"
    response_time: str = "5m"  # Duration string (e.g., "5m", "1h", "30s"). Parsed by Animator.
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    availability: str | None = None
    traits: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class FrictionProfile(BaseModel, frozen=True):
    """Profile describing an actor's friction behavior.

    Covers the full spectrum: ``uncooperative`` (vague, slow, changes mind),
    ``deceptive`` (fake evidence, social engineering), and ``hostile``
    (explicit threats, system exploitation).
    """

    category: Literal["uncooperative", "deceptive", "hostile"] = "uncooperative"
    intensity: int = Field(30, ge=0, le=100)
    behaviors: list[str] = Field(default_factory=list)
    sophistication: Literal["low", "medium", "high"] = "medium"
    goal: str = ""
    traits: dict[str, Any] = Field(default_factory=dict)


def AdversarialProfile(**kwargs: Any) -> FrictionProfile:
    """Deprecated.  Use ``FrictionProfile(category='hostile', ...)`` instead."""
    warnings.warn(
        "AdversarialProfile is deprecated. Use FrictionProfile(category='hostile').",
        DeprecationWarning,
        stacklevel=2,
    )
    kwargs.setdefault("category", "hostile")
    return FrictionProfile(**kwargs)
