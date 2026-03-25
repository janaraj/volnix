"""Pydantic models for YAML-based service profiles (Tier 2).

A ServiceProfile YAML file describes a service without Python code:
operations, entities, state machines, error modes, behavioral notes,
examples, and an LLM responder prompt.

These are NOT Python ServiceProfile subclasses. They are data files
loaded by ProfileLoader and converted to ServiceSurface objects.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProfileOperation(BaseModel, frozen=True):
    """A single API operation in a profile."""

    name: str  # "jira_create_issue"
    service: str  # "jira"
    description: str = ""
    http_method: str = "POST"
    http_path: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    required_params: list[str] = Field(default_factory=list)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    is_read_only: bool = False
    creates_entity: str | None = None
    mutates_entity: str | None = None


class ProfileEntity(BaseModel, frozen=True):
    """An entity type managed by the profiled service."""

    name: str  # "issue"
    identity_field: str = "id"
    fields: dict[str, Any] = Field(default_factory=dict)  # JSON-schema-style properties
    required: list[str] = Field(default_factory=list)


class ProfileStateMachine(BaseModel, frozen=True):
    """State machine for an entity type."""

    entity_type: str  # "issue"
    field: str = "status"  # Which field tracks state
    transitions: dict[str, list[str]] = Field(default_factory=dict)


class ProfileErrorMode(BaseModel, frozen=True):
    """An error condition the service can produce."""

    code: str  # "ISSUE_NOT_FOUND"
    when: str  # "Issue ID does not exist"
    http_status: int = 400
    response_body: dict[str, Any] = Field(default_factory=dict)


class ProfileExample(BaseModel, frozen=True):
    """Request/response example for few-shot prompting."""

    operation: str  # "jira_create_issue"
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)


class ServiceProfileData(BaseModel, frozen=True):
    """Complete service profile loaded from YAML.

    This is the Pydantic representation of a .profile.yaml file.
    NOT the same as packs.base.ServiceProfile ABC.
    """

    # Identity
    profile_name: str  # "jira"
    service_name: str  # "jira"
    category: str  # "work_management"
    version: str = "1.0.0"
    fidelity_source: str = "curated_profile"  # "curated_profile" | "bootstrapped"

    # Operations
    operations: list[ProfileOperation] = Field(default_factory=list)

    # Entities
    entities: list[ProfileEntity] = Field(default_factory=list)

    # State machines
    state_machines: list[ProfileStateMachine] = Field(default_factory=list)

    # Error modes
    error_modes: list[ProfileErrorMode] = Field(default_factory=list)

    # Behavioral notes (injected into LLM prompt)
    behavioral_notes: list[str] = Field(default_factory=list)

    # Few-shot examples
    examples: list[ProfileExample] = Field(default_factory=list)

    # LLM responder prompt
    responder_prompt: str = ""

    # Pack extension (for profiles that overlay a Tier 1 pack)
    extends_pack: str | None = None

    # Confidence score (0.0 to 1.0)
    confidence: float = 0.9

    # Source chain for provenance tracking
    source_chain: list[str] = Field(default_factory=list)

    # Auth pattern
    auth_pattern: str = ""
    base_url: str = ""
