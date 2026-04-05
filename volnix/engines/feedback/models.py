"""Pydantic models for the feedback pipeline.

All models are frozen (immutable) per project convention.
Domain identifiers use typed wrappers from ``core.types``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ObservedOperation(BaseModel, frozen=True):
    """An API operation observed during a simulation run."""

    name: str
    call_count: int
    parameter_keys: list[str] = Field(default_factory=list)
    response_keys: list[str] = Field(default_factory=list)
    error_count: int = 0


class ObservedMutation(BaseModel, frozen=True):
    """An entity state change observed during a simulation run."""

    entity_type: str
    operation: str  # create | update | delete
    count: int


class ObservedError(BaseModel, frozen=True):
    """An error pattern observed during a simulation run."""

    error_type: str
    count: int
    context: str = ""


class CapturedSurface(BaseModel, frozen=True):
    """Behavioral fingerprint of a service extracted from a completed run.

    Produced by :class:`ServiceCapture.capture()` — represents everything
    observed about a service during a single simulation run.
    """

    service_name: str
    run_id: str
    captured_at: str  # ISO timestamp
    operations_observed: list[ObservedOperation] = Field(
        default_factory=list
    )
    entity_mutations: list[ObservedMutation] = Field(default_factory=list)
    error_patterns: list[ObservedError] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    behavioral_rules: list[str] = Field(default_factory=list)
    source_profile: str | None = None
    fidelity_source: str = "bootstrapped"


class PromotionEvaluation(BaseModel, frozen=True):
    """Result of evaluating a service for tier promotion."""

    service_name: str
    eligible: bool
    current_fidelity: str
    proposed_fidelity: str
    criteria_met: list[str] = Field(default_factory=list)
    criteria_missing: list[str] = Field(default_factory=list)
    recommendation: str = ""
    annotation_count: int = 0


class PromotionResult(BaseModel, frozen=True):
    """Outcome of executing a tier promotion."""

    service_name: str
    previous_fidelity: str
    new_fidelity: str
    profile_path: str
    version: str


class PackCompileResult(BaseModel, frozen=True):
    """Outcome of generating a Tier 1 pack scaffold."""

    service_name: str
    output_dir: str
    files_generated: list[str] = Field(default_factory=list)
    handler_stubs: int = 0


class VerificationCheck(BaseModel, frozen=True):
    """A single verification check result."""

    name: str
    passed: bool
    message: str = ""


class VerificationResult(BaseModel, frozen=True):
    """Full pack verification outcome."""

    service_name: str
    passed: bool
    checks: list[VerificationCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
