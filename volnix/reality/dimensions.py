"""World-condition dimension models.

Five universal dimensions describe the personality of a generated world.
All dimension models are frozen Pydantic ``BaseModel`` instances so they
can be safely shared across compilation stages.

Dimensions are PERSONALITY TRAITS, not engineering parameters.  The LLM
interprets them holistically -- "somewhat_neglected information" means the
LLM generates a world where data management has been neglected.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Base dimension
# ---------------------------------------------------------------------------


class BaseDimension(BaseModel, frozen=True):
    """Shared base for all dimension models."""

    def to_dict(self) -> dict[str, Any]:
        """Return all fields as a plain dictionary."""
        return self.model_dump()

    @classmethod
    def field_names(cls) -> list[str]:
        """Return the list of field names for this dimension."""
        return list(cls.model_fields.keys())


# ---------------------------------------------------------------------------
# Individual dimensions
# ---------------------------------------------------------------------------


class InformationQualityDimension(BaseDimension, frozen=True):
    """How clean / complete the data in this world is."""

    staleness: int = Field(default=0, ge=0, le=100)
    incompleteness: int = Field(default=0, ge=0, le=100)
    inconsistency: int = Field(default=0, ge=0, le=100)
    noise: int = Field(default=0, ge=0, le=100)


class ReliabilityDimension(BaseDimension, frozen=True):
    """How reliable external services are in this world."""

    failures: int = Field(default=0, ge=0, le=100)
    timeouts: int = Field(default=0, ge=0, le=100)
    degradation: int = Field(default=0, ge=0, le=100)


class SocialFrictionDimension(BaseDimension, frozen=True):
    """How hostile the external actors in this world are."""

    uncooperative: int = Field(default=0, ge=0, le=100)
    deceptive: int = Field(default=0, ge=0, le=100)
    hostile: int = Field(default=0, ge=0, le=100)
    sophistication: Literal["low", "medium", "high"] = "low"


class ComplexityDimension(BaseDimension, frozen=True):
    """How ambiguous / edge-case-heavy the situations are."""

    ambiguity: int = Field(default=0, ge=0, le=100)
    edge_cases: int = Field(default=0, ge=0, le=100)
    contradictions: int = Field(default=0, ge=0, le=100)
    urgency: int = Field(default=0, ge=0, le=100)
    volatility: int = Field(default=0, ge=0, le=100)


class BoundaryDimension(BaseDimension, frozen=True):
    """How many gaps exist in auth / data access boundaries."""

    access_limits: int = Field(default=0, ge=0, le=100)
    rule_clarity: int = Field(default=0, ge=0, le=100)
    boundary_gaps: int = Field(default=0, ge=0, le=100)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


class WorldConditions(BaseModel, frozen=True):
    """Combined world conditions across all five dimensions.

    This is the compilation-time "personality" of the world that gets passed
    to the world compiler and condition expander.  The LLM decides how
    personality traits manifest in concrete entities and situations.
    """

    information: InformationQualityDimension = Field(default_factory=InformationQualityDimension)
    reliability: ReliabilityDimension = Field(default_factory=ReliabilityDimension)
    friction: SocialFrictionDimension = Field(default_factory=SocialFrictionDimension)
    complexity: ComplexityDimension = Field(default_factory=ComplexityDimension)
    boundaries: BoundaryDimension = Field(default_factory=BoundaryDimension)
