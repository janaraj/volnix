"""World-condition dimension models.

Five universal dimensions describe the state of a generated world.  All
dimension models are frozen Pydantic ``BaseModel`` instances so they can
be safely shared across compilation stages.
"""

from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Individual dimensions
# ---------------------------------------------------------------------------


class DataQualityDimension(BaseModel, frozen=True):
    """How clean / complete the data in this world is."""

    staleness: int = 0          # % of records with outdated info
    incompleteness: int = 0     # % of entities missing fields
    inconsistency: int = 0      # % of cross-service lookups with conflicting data


class ServiceReliabilityDimension(BaseModel, frozen=True):
    """How reliable external services are in this world."""

    failure_rate: int = 0       # % of API calls that fail
    timeouts: int = 0           # % of API calls that timeout


class SituationalComplexityDimension(BaseModel, frozen=True):
    """How ambiguous / edge-case-heavy the situations are."""

    ambiguity: int = 0          # % of requests that are vague/contradictory
    edge_cases: int = 0         # % of situations that don't fit any policy


class AdversarialDimension(BaseModel, frozen=True):
    """How hostile the external actors in this world are."""

    hostile_actors: int = 0     # % of external actors with manipulative intent
    injection_content: int = 0  # % of inbound content containing manipulation
    sophistication: str = "low" # low | medium | high


class BoundarySecurityDimension(BaseModel, frozen=True):
    """How many gaps exist in auth / data access boundaries."""

    auth_gaps: int = 0          # % of access points with misconfigured auth
    exposed_secrets: int = 0    # % of sensitive data accessible without proper scoping


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


class WorldConditions(BaseModel, frozen=True):
    """Combined world conditions across all five dimensions.

    This is the compilation-time "shape" of the world that gets passed
    to the world compiler and seed processor.
    """

    data_quality: DataQualityDimension = DataQualityDimension()
    service_reliability: ServiceReliabilityDimension = ServiceReliabilityDimension()
    situational_complexity: SituationalComplexityDimension = SituationalComplexityDimension()
    adversarial: AdversarialDimension = AdversarialDimension()
    boundary_security: BoundarySecurityDimension = BoundarySecurityDimension()
