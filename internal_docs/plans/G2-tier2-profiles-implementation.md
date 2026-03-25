Now I have a thorough understanding of the entire codebase. Let me deliver the comprehensive implementation plan.

---

## Terrarium G2: Tier 2 Service Profiles + Runtime + Infer Pipeline -- Complete Implementation Plan

This plan covers the complete end-to-end flow: YAML profile files, profile loader, Tier 2 runtime, infer pipeline, and integration into MCP/HTTP/Gateway/Responder/Compiler.

---

### COMPONENT 1: ServiceProfile YAML Schema + Pydantic Model

**Purpose**: Define the structured YAML file format for service profiles and the Pydantic model that loads them.

**File**: `/Users/jana/workspace/terrarium/terrarium/packs/profile_schema.py` (NEW)

```python
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
    name: str                                  # "jira_create_issue"
    service: str                               # "jira"
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
    name: str                                  # "issue"
    identity_field: str = "id"
    fields: dict[str, Any] = Field(default_factory=dict)  # JSON-schema-style properties
    required: list[str] = Field(default_factory=list)


class ProfileStateMachine(BaseModel, frozen=True):
    """State machine for an entity type."""
    entity_type: str                           # "issue"
    field: str = "status"                      # Which field tracks state
    transitions: dict[str, list[str]] = Field(default_factory=dict)


class ProfileErrorMode(BaseModel, frozen=True):
    """An error condition the service can produce."""
    code: str                                  # "ISSUE_NOT_FOUND"
    when: str                                  # "Issue ID does not exist"
    http_status: int = 400
    response_body: dict[str, Any] = Field(default_factory=dict)


class ProfileExample(BaseModel, frozen=True):
    """Request/response example for few-shot prompting."""
    operation: str                             # "jira_create_issue"
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)


class ServiceProfileData(BaseModel, frozen=True):
    """Complete service profile loaded from YAML.
    
    This is the Pydantic representation of a .profile.yaml file.
    NOT the same as packs.base.ServiceProfile ABC.
    """
    # Identity
    profile_name: str                          # "jira"
    service_name: str                          # "jira"
    category: str                              # "work_management"
    version: str = "1.0.0"
    fidelity_source: str = "curated_profile"   # "curated_profile" | "bootstrapped"
    
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
    
    # Auth pattern
    auth_pattern: str = ""
    base_url: str = ""
```

**Key design decisions**:
- Separate from `packs.base.ServiceProfile` ABC. That ABC was designed for Python-code profiles that extend Tier 1 packs. This is for standalone YAML data profiles that do NOT require a base pack.
- All models are frozen Pydantic (project convention).
- `fidelity_source` distinguishes hand-curated from LLM-inferred profiles.

---

### COMPONENT 2: ProfileLoader

**Purpose**: Load `.profile.yaml` files from disk, parse them into `ServiceProfileData`, convert to `ServiceSurface`.

**File**: `/Users/jana/workspace/terrarium/terrarium/packs/profile_loader.py` (NEW)

```python
"""Profile loader -- reads .profile.yaml files and produces ServiceSurface objects.

Scans a directory for *.profile.yaml files, parses each into ServiceProfileData,
and converts to ServiceSurface for use by the responder, gateway, and MCP/HTTP adapters.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

import yaml

from terrarium.kernel.surface import APIOperation, ServiceSurface
from terrarium.packs.profile_schema import (
    ServiceProfileData,
    ProfileOperation,
    ProfileEntity,
)

logger = logging.getLogger(__name__)


class ProfileLoader:
    """Loads YAML service profiles and converts them to ServiceSurfaces."""

    def __init__(self, profile_dir: str | Path | None = None) -> None:
        self._profile_dir = Path(profile_dir) if profile_dir else None
        self._profiles: dict[str, ServiceProfileData] = {}
        self._surfaces: dict[str, ServiceSurface] = {}

    def discover(self, profile_dir: str | Path | None = None) -> int:
        """Scan directory for .profile.yaml files. Returns count loaded."""
        scan_dir = Path(profile_dir) if profile_dir else self._profile_dir
        if scan_dir is None or not scan_dir.is_dir():
            return 0
        
        count = 0
        # Pattern 1: profiles/jira.profile.yaml (flat)
        for yaml_file in sorted(scan_dir.glob("*.profile.yaml")):
            profile = self._load_file(yaml_file)
            if profile:
                self._profiles[profile.service_name] = profile
                self._surfaces[profile.service_name] = self._to_surface(profile)
                count += 1
        
        # Pattern 2: profiles/jira/profile.yaml (subdirectory)
        for subdir in sorted(scan_dir.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("_"):
                yaml_file = subdir / "profile.yaml"
                if yaml_file.exists():
                    profile = self._load_file(yaml_file)
                    if profile:
                        self._profiles[profile.service_name] = profile
                        self._surfaces[profile.service_name] = self._to_surface(profile)
                        count += 1
        
        logger.info("ProfileLoader: discovered %d profiles", count)
        return count

    def register_profile(self, profile: ServiceProfileData) -> None:
        """Register a profile directly (e.g., from infer pipeline)."""
        self._profiles[profile.service_name] = profile
        self._surfaces[profile.service_name] = self._to_surface(profile)

    def get_profile(self, service_name: str) -> ServiceProfileData | None:
        """Get the raw profile data for a service."""
        return self._profiles.get(service_name.lower())

    def get_surface(self, service_name: str) -> ServiceSurface | None:
        """Get the ServiceSurface for a profiled service."""
        return self._surfaces.get(service_name.lower())

    def has_profile(self, service_name: str) -> bool:
        return service_name.lower() in self._profiles

    def list_profiles(self) -> list[str]:
        return sorted(self._profiles.keys())

    def get_all_surfaces(self) -> dict[str, ServiceSurface]:
        """Return all loaded surfaces (for gateway tool discovery)."""
        return dict(self._surfaces)

    def _load_file(self, path: Path) -> ServiceProfileData | None:
        """Parse a single .profile.yaml file."""
        try:
            with path.open("r") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                logger.warning("Profile %s is not a dict", path)
                return None
            return ServiceProfileData(**raw)
        except Exception as exc:
            logger.warning("Failed to load profile %s: %s", path, exc)
            return None

    @staticmethod
    def _to_surface(profile: ServiceProfileData) -> ServiceSurface:
        """Convert ServiceProfileData to ServiceSurface."""
        operations = []
        for op in profile.operations:
            operations.append(APIOperation(
                name=op.name,
                service=profile.service_name,
                description=op.description,
                http_method=op.http_method,
                http_path=op.http_path,
                parameters=op.parameters,
                required_params=op.required_params,
                response_schema=op.response_schema,
                is_read_only=op.is_read_only,
                creates_entity=op.creates_entity,
                mutates_entity=op.mutates_entity,
            ))
        
        entity_schemas = {}
        for entity in profile.entities:
            entity_schemas[entity.name] = {
                "type": "object",
                "properties": entity.fields,
                "required": entity.required,
                "identity_field": entity.identity_field,
            }
        
        state_machines = {}
        for sm in profile.state_machines:
            state_machines[sm.entity_type] = {
                "field": sm.field,
                "transitions": sm.transitions,
            }
        
        from terrarium.core.types import FidelitySource
        confidence = 0.9 if profile.fidelity_source == "curated_profile" else 0.6
        
        return ServiceSurface(
            service_name=profile.service_name,
            category=profile.category,
            source=f"tier2_{profile.fidelity_source}",
            fidelity_tier=2,
            operations=operations,
            entity_schemas=entity_schemas,
            state_machines=state_machines,
            confidence=confidence,
            auth_pattern=profile.auth_pattern,
            base_url=profile.base_url,
        )
```

**Integration points**:
- Called by `WorldResponderEngine._on_initialize()` to discover profiles at startup.
- Called by the infer pipeline to register dynamically generated profiles.
- Surfaces are consumed by Gateway.initialize() for tool discovery.

---

### COMPONENT 3: Jira Service Profile (Hand-Crafted YAML)

**File**: `/Users/jana/workspace/terrarium/terrarium/packs/profiles/jira.profile.yaml` (NEW)

Note: A NEW `profiles/` directory at `terrarium/packs/profiles/` -- distinct from the existing `profiled/` directory which contains Python-code profiles.

```yaml
profile_name: jira
service_name: jira
category: work_management
version: "1.0.0"
fidelity_source: curated_profile

operations:
  - name: jira_create_issue
    service: jira
    description: "Create a new Jira issue in a project"
    http_method: POST
    http_path: /rest/api/3/issue
    parameters:
      project_key:
        type: string
        description: "Project key (e.g., PROJ)"
      summary:
        type: string
        description: "Issue summary/title"
      description:
        type: string
        description: "Issue description (Atlassian Document Format or plain text)"
      issue_type:
        type: string
        enum: ["Bug", "Task", "Story", "Epic", "Sub-task"]
        description: "Type of issue"
      priority:
        type: string
        enum: ["Highest", "High", "Medium", "Low", "Lowest"]
      assignee_id:
        type: string
        description: "Account ID of the assignee"
      labels:
        type: array
        items: {type: string}
      sprint_id:
        type: integer
        description: "Sprint to add the issue to"
    required_params: [project_key, summary, issue_type]
    response_schema:
      type: object
      properties:
        id: {type: string}
        key: {type: string}
        self: {type: string}
      required: [id, key]
    creates_entity: issue

  - name: jira_get_issue
    service: jira
    description: "Get a single Jira issue by key"
    http_method: GET
    http_path: /rest/api/3/issue/{issue_key}
    parameters:
      issue_key:
        type: string
        description: "Issue key (e.g., PROJ-123)"
    required_params: [issue_key]
    response_schema:
      type: object
      properties:
        id: {type: string}
        key: {type: string}
        fields:
          type: object
          properties:
            summary: {type: string}
            description: {type: string}
            status: {type: object, properties: {name: {type: string}}}
            priority: {type: object, properties: {name: {type: string}}}
            assignee: {type: object, properties: {accountId: {type: string}, displayName: {type: string}}}
            project: {type: object, properties: {key: {type: string}, name: {type: string}}}
            issuetype: {type: object, properties: {name: {type: string}}}
            created: {type: string}
            updated: {type: string}
            labels: {type: array, items: {type: string}}
      required: [id, key, fields]
    is_read_only: true

  - name: jira_update_issue
    service: jira
    description: "Update fields on an existing Jira issue"
    http_method: PUT
    http_path: /rest/api/3/issue/{issue_key}
    parameters:
      issue_key: {type: string}
      summary: {type: string}
      description: {type: string}
      priority: {type: string, enum: ["Highest", "High", "Medium", "Low", "Lowest"]}
      assignee_id: {type: string}
      labels: {type: array, items: {type: string}}
    required_params: [issue_key]
    response_schema:
      type: object
      properties:
        ok: {type: boolean}
    mutates_entity: issue

  - name: jira_transition_issue
    service: jira
    description: "Transition an issue to a new status"
    http_method: POST
    http_path: /rest/api/3/issue/{issue_key}/transitions
    parameters:
      issue_key: {type: string}
      transition_id: {type: string}
      transition_name: {type: string, enum: ["To Do", "In Progress", "In Review", "Done"]}
    required_params: [issue_key]
    response_schema:
      type: object
      properties:
        ok: {type: boolean}
    mutates_entity: issue

  - name: jira_search_issues
    service: jira
    description: "Search for issues using JQL"
    http_method: POST
    http_path: /rest/api/3/search
    parameters:
      jql: {type: string, description: "JQL query string"}
      max_results: {type: integer, description: "Maximum results to return"}
      start_at: {type: integer}
    required_params: [jql]
    response_schema:
      type: object
      properties:
        total: {type: integer}
        issues:
          type: array
          items:
            type: object
            properties:
              id: {type: string}
              key: {type: string}
              fields: {type: object}
    is_read_only: true

  - name: jira_list_sprints
    service: jira
    description: "List sprints for a board"
    http_method: GET
    http_path: /rest/agile/1.0/board/{board_id}/sprint
    parameters:
      board_id: {type: integer}
      state: {type: string, enum: ["active", "closed", "future"]}
    required_params: [board_id]
    response_schema:
      type: object
      properties:
        values:
          type: array
          items:
            type: object
            properties:
              id: {type: integer}
              name: {type: string}
              state: {type: string}
              startDate: {type: string}
              endDate: {type: string}
    is_read_only: true

  - name: jira_add_comment
    service: jira
    description: "Add a comment to an issue"
    http_method: POST
    http_path: /rest/api/3/issue/{issue_key}/comment
    parameters:
      issue_key: {type: string}
      body: {type: string, description: "Comment body text"}
    required_params: [issue_key, body]
    response_schema:
      type: object
      properties:
        id: {type: string}
        body: {type: string}
        author: {type: object, properties: {accountId: {type: string}, displayName: {type: string}}}
        created: {type: string}
    creates_entity: comment

entities:
  - name: issue
    identity_field: key
    fields:
      id: {type: string}
      key: {type: string}
      summary: {type: string}
      description: {type: string}
      status: {type: string, enum: ["To Do", "In Progress", "In Review", "Done"]}
      priority: {type: string, enum: ["Highest", "High", "Medium", "Low", "Lowest"]}
      issue_type: {type: string, enum: ["Bug", "Task", "Story", "Epic", "Sub-task"]}
      project_key: {type: string}
      assignee_id: {type: string}
      reporter_id: {type: string}
      labels: {type: array, items: {type: string}}
      sprint_id: {type: integer}
      created: {type: string}
      updated: {type: string}
    required: [key, summary, status, issue_type, project_key]

  - name: sprint
    identity_field: id
    fields:
      id: {type: integer}
      name: {type: string}
      state: {type: string, enum: ["active", "closed", "future"]}
      board_id: {type: integer}
      start_date: {type: string}
      end_date: {type: string}
      goal: {type: string}
    required: [id, name, state]

  - name: comment
    identity_field: id
    fields:
      id: {type: string}
      issue_key: {type: string}
      body: {type: string}
      author_id: {type: string}
      created: {type: string}
    required: [id, issue_key, body]

state_machines:
  - entity_type: issue
    field: status
    transitions:
      "To Do": ["In Progress"]
      "In Progress": ["In Review", "To Do"]
      "In Review": ["Done", "In Progress"]
      "Done": ["To Do"]

  - entity_type: sprint
    field: state
    transitions:
      "future": ["active"]
      "active": ["closed"]

error_modes:
  - code: ISSUE_NOT_FOUND
    when: "Issue key does not match any existing issue"
    http_status: 404
    response_body: {"errorMessages": ["Issue Does Not Exist"], "errors": {}}
  - code: PERMISSION_DENIED
    when: "User does not have permission on the project"
    http_status: 403
  - code: INVALID_TRANSITION
    when: "The requested status transition is not allowed"
    http_status: 400
    response_body: {"errorMessages": ["Invalid transition"], "errors": {}}

behavioral_notes:
  - "Jira issue keys follow the pattern PROJECT_KEY-NUMBER (e.g., PROJ-123)"
  - "All dates are in ISO 8601 format with timezone"
  - "User references use accountId (not username) in Jira Cloud"
  - "JQL queries support standard operators: =, !=, IN, NOT IN, IS, IS NOT, ~, ORDER BY"
  - "Status transitions must follow the configured workflow"
  - "Sprint IDs are board-scoped integers"
  - "Issue descriptions in Jira Cloud use Atlassian Document Format (ADF), but plain text is accepted"

examples:
  - operation: jira_create_issue
    request:
      project_key: "PROJ"
      summary: "Fix login page timeout"
      issue_type: "Bug"
      priority: "High"
      assignee_id: "5b10a2844c20165700ede21g"
    response:
      id: "10042"
      key: "PROJ-42"
      self: "https://your-domain.atlassian.net/rest/api/3/issue/10042"

  - operation: jira_search_issues
    request:
      jql: "project = PROJ AND status = 'In Progress' ORDER BY priority DESC"
      max_results: 10
    response:
      total: 3
      issues:
        - id: "10040"
          key: "PROJ-40"
          fields: {summary: "Update API docs", status: {name: "In Progress"}, priority: {name: "Medium"}}

responder_prompt: |
  You are simulating the Jira Cloud REST API (v3).
  
  You manage project issues, sprints, and comments. Your responses must:
  1. Follow the exact response schema for each operation
  2. Generate realistic Jira issue keys (PROJECT_KEY-NUMBER, incrementing)
  3. Use accountId format for user references (e.g., "5b10a2844c20165700ede21g")
  4. Return ISO 8601 dates with timezone for all date fields
  5. Respect status transitions: To Do -> In Progress -> In Review -> Done (with allowed reversals)
  6. JQL search results should filter the existing issues based on the query
  7. For errors, return Jira-style error responses with "errorMessages" array
  
  When creating entities, generate a new unique key by incrementing the highest existing 
  issue number for that project. When searching, apply JQL filters against existing state.

auth_pattern: bearer
base_url: "https://your-domain.atlassian.net"
```

**Additional profiles** (Shopify and Twilio):
- `/Users/jana/workspace/terrarium/terrarium/packs/profiles/shopify.profile.yaml` -- hand-crafted with operations for products/orders/customers
- `/Users/jana/workspace/terrarium/terrarium/packs/profiles/twilio.profile.yaml` -- either hand-crafted or auto-inferred to prove the pipeline

---

### COMPONENT 4: Tier 2 Generator (LLM-Constrained Responses)

**Purpose**: When no Tier 1 pack handles a tool, use the profile to constrain an LLM response.

**File**: `/Users/jana/workspace/terrarium/terrarium/engines/responder/tier2.py` (MODIFY -- replace stub)

```python
"""Tier 2 generator -- profiled LLM responses.

Generates service responses using LLM constrained by:
1. The profile's responder_prompt (system personality)
2. The operation's response_schema (structural constraint)
3. Current world state (entity context)
4. Behavioral notes (service-specific rules)
5. Few-shot examples (grounding)
6. Error modes (realistic failure simulation)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from terrarium.core.context import ActionContext, ResponseProposal
from terrarium.core.types import (
    EntityId,
    FidelityMetadata,
    FidelitySource,
    FidelityTier,
    StateDelta,
)
from terrarium.llm.router import LLMRouter
from terrarium.llm.types import LLMRequest
from terrarium.packs.profile_schema import ServiceProfileData
from terrarium.validation.schema import SchemaValidator

logger = logging.getLogger(__name__)


class Tier2Generator:
    """Generates responses using LLM guided by curated service profiles."""

    def __init__(
        self,
        llm_router: LLMRouter,
        state: Any,  # StateEngineProtocol
    ) -> None:
        self._llm_router = llm_router
        self._state = state
        self._schema_validator = SchemaValidator()

    async def generate(
        self,
        ctx: ActionContext,
        profile: ServiceProfileData,
    ) -> ResponseProposal:
        """Generate a profiled LLM response.

        Steps:
        1. Build system prompt from profile.responder_prompt + behavioral_notes
        2. Build user prompt from operation + input_data + current state
        3. Call LLM via router (engine_name="responder", use_case="tier2")
        4. Parse JSON response
        5. Validate against operation.response_schema
        6. Extract state deltas from response
        7. Return ResponseProposal with fidelity metadata
        """
        # Find the operation definition
        operation = None
        for op in profile.operations:
            if op.name == ctx.action:
                operation = op
                break
        if operation is None:
            return self._error_proposal(f"Operation '{ctx.action}' not found in profile '{profile.profile_name}'")

        # Build current state context
        state_context = await self._build_state_context(profile)

        # Build system prompt
        system_prompt = self._build_system_prompt(profile, operation)

        # Build user prompt
        user_prompt = self._build_user_prompt(
            operation, ctx.input_data, state_context
        )

        # Call LLM
        request = LLMRequest(
            system_prompt=system_prompt,
            user_content=user_prompt,
            output_schema=self._build_output_schema(operation),
            temperature=0.7,
        )
        response = await self._llm_router.route(
            request,
            engine_name="responder",
            use_case="tier2",
        )

        # Parse response
        response_body = self._parse_response(response)

        # Validate against schema
        if operation.response_schema:
            result = self._schema_validator.validate_response(
                response_body, operation.response_schema
            )
            if not result.valid:
                logger.warning(
                    "Tier2 response validation failed for %s: %s",
                    ctx.action, result.errors
                )
                # Don't hard-fail; attach warning

        # Extract state deltas
        state_deltas = self._extract_state_deltas(
            operation, response_body, profile
        )

        return ResponseProposal(
            response_body=response_body,
            proposed_state_deltas=state_deltas,
            fidelity=FidelityMetadata(
                tier=FidelityTier.PROFILED,
                source=profile.profile_name,
                fidelity_source=FidelitySource(profile.fidelity_source),
                deterministic=False,
                replay_stable=False,
                benchmark_grade=False,
            ),
            fidelity_warning=f"Tier 2 profile: {profile.profile_name} (LLM-generated response)",
        )

    def _build_system_prompt(
        self, profile: ServiceProfileData, operation: Any
    ) -> str:
        """Assemble system prompt from profile data."""
        parts = [profile.responder_prompt]

        if profile.behavioral_notes:
            parts.append("\n## Behavioral Rules")
            for note in profile.behavioral_notes:
                parts.append(f"- {note}")

        if profile.error_modes:
            parts.append("\n## Error Modes")
            for em in profile.error_modes:
                parts.append(f"- {em.code}: {em.when} (HTTP {em.http_status})")

        parts.append("\n## Response Format")
        parts.append("Output ONLY valid JSON matching the response schema.")
        parts.append("Do NOT include markdown formatting or explanation.")

        if operation.response_schema:
            parts.append(f"\n## Response Schema\n```json\n{json.dumps(operation.response_schema, indent=2)}\n```")

        return "\n".join(parts)

    def _build_user_prompt(
        self,
        operation: Any,
        input_data: dict[str, Any],
        state_context: str,
    ) -> str:
        """Build user prompt with operation, input, and state."""
        parts = [f"Execute operation: {operation.name}"]
        parts.append(f"Description: {operation.description}")
        parts.append(f"\n## Input\n```json\n{json.dumps(input_data, indent=2)}\n```")

        if state_context:
            parts.append(f"\n## Current World State\n{state_context}")

        # Add relevant few-shot examples
        # (matched by operation name from profile.examples)
        examples = [
            ex for ex in getattr(self, '_current_profile_examples', [])
            if ex.operation == operation.name
        ]
        # Stored as instance var during generate(); alternatively pass profile
        # Better: receive from caller
        return "\n".join(parts)

    def _build_output_schema(self, operation: Any) -> dict[str, Any] | None:
        """Build structured output schema for the LLM request."""
        if operation.response_schema:
            return operation.response_schema
        return None

    async def _build_state_context(self, profile: ServiceProfileData) -> str:
        """Fetch relevant entity state for the profiled service."""
        if self._state is None:
            return ""
        parts = []
        for entity in profile.entities:
            try:
                entities = await self._state.query_entities(entity.name)
                if entities:
                    parts.append(f"### {entity.name} ({len(entities)} total)")
                    # Limit to 20 entities to avoid token overflow
                    for e in entities[:20]:
                        parts.append(json.dumps(e, default=str))
            except Exception:
                pass
        return "\n".join(parts)

    def _extract_state_deltas(
        self,
        operation: Any,
        response_body: dict[str, Any],
        profile: ServiceProfileData,
    ) -> list[StateDelta]:
        """Extract state deltas from the LLM response."""
        deltas = []

        if operation.creates_entity:
            entity_type = operation.creates_entity
            # Find the identity field for this entity type
            identity_field = "id"
            for entity_def in profile.entities:
                if entity_def.name == entity_type:
                    identity_field = entity_def.identity_field
                    break

            entity_id = response_body.get(identity_field, response_body.get("id", f"gen-{entity_type}"))
            deltas.append(StateDelta(
                entity_type=entity_type,
                entity_id=EntityId(str(entity_id)),
                operation="create",
                fields=response_body,
            ))
        elif operation.mutates_entity:
            entity_type = operation.mutates_entity
            identity_field = "id"
            for entity_def in profile.entities:
                if entity_def.name == entity_type:
                    identity_field = entity_def.identity_field
                    break
            # Try to find the entity ID from the input data or response
            entity_id = response_body.get(identity_field, "unknown")
            deltas.append(StateDelta(
                entity_type=entity_type,
                entity_id=EntityId(str(entity_id)),
                operation="update",
                fields=response_body,
            ))

        return deltas

    def _parse_response(self, response: Any) -> dict[str, Any]:
        """Parse LLM response into dict."""
        if response.structured_output:
            return response.structured_output
        
        content = response.content.strip()
        # Strip markdown code block wrappers
        import re
        content = re.sub(r'^```(?:json)?\s*\n?', '', content)
        content = re.sub(r'\n?\s*```\s*$', '', content)
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON object
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    pass
        
        return {"raw_response": content, "_parse_error": True}

    @staticmethod
    def _error_proposal(message: str) -> ResponseProposal:
        return ResponseProposal(
            response_body={"error": message},
            fidelity=FidelityMetadata(
                tier=FidelityTier.PROFILED,
                source="tier2_error",
                deterministic=False,
            ),
        )
```

---

### COMPONENT 5: Responder Engine Integration (Tier 1 + Tier 2 Dispatch)

**File**: `/Users/jana/workspace/terrarium/terrarium/engines/responder/engine.py` (MODIFY)

Changes to `WorldResponderEngine`:

1. **`_on_initialize()`** -- add ProfileLoader discovery and Tier2Generator creation.
2. **`execute()`** -- add Tier 2 fallback when Tier 1 has no handler.
3. **`_build_state_for_profile()`** -- new helper to fetch state for profiled services.

**Exact changes in `_on_initialize()`**:
After the existing Tier 1 setup code, add:
```python
# Tier 2: Profile-based services
from terrarium.packs.profile_loader import ProfileLoader
profile_base = Path(__file__).resolve().parents[2] / "packs" / "profiles"
self._profile_loader = ProfileLoader(profile_base)
self._profile_loader.discover()

# Tier 2 generator (needs LLM router -- injected later in _inject_cross_engine_deps)
self._tier2: Tier2Generator | None = None
```

**Exact changes in `execute()`** (replace the current method):
```python
async def execute(self, ctx: ActionContext) -> StepResult:
    """Execute the responder pipeline step.
    
    Dispatch order:
    1. Tier 1 pack (verified, deterministic)
    2. Tier 2 profile (LLM-constrained by profile)
    3. Error: no handler
    """
    # Try Tier 1 first
    if self._tier1.has_pack_for_tool(ctx.action):
        state = await self._build_state_for_pack(ctx)
        proposal = await self._tier1.dispatch(ctx, state=state)
        ctx.response_proposal = proposal
        return StepResult(
            step_name="responder",
            verdict=StepVerdict.ALLOW,
            metadata={"fidelity_tier": 1},
        )

    # Try Tier 2 profile
    profile = self._find_profile_for_action(ctx.action)
    if profile is not None and self._tier2 is not None:
        proposal = await self._tier2.generate(ctx, profile)
        ctx.response_proposal = proposal
        return StepResult(
            step_name="responder",
            verdict=StepVerdict.ALLOW,
            metadata={"fidelity_tier": 2, "profile": profile.profile_name},
        )

    # No handler
    return StepResult(
        step_name="responder",
        verdict=StepVerdict.ERROR,
        message=f"No pack or profile found for action '{ctx.action}'",
    )
```

**New helper method `_find_profile_for_action()`**:
```python
def _find_profile_for_action(self, action: str) -> ServiceProfileData | None:
    """Find a profile that provides the given action."""
    for service_name in self._profile_loader.list_profiles():
        profile = self._profile_loader.get_profile(service_name)
        if profile:
            for op in profile.operations:
                if op.name == action:
                    return profile
    return None
```

**New property for profile_loader** (used by Gateway):
```python
@property
def profile_loader(self) -> Any:
    """Public accessor for the profile loader."""
    return self._profile_loader
```

---

### COMPONENT 6: Gateway Integration (Tier 2 Tool Discovery)

**File**: `/Users/jana/workspace/terrarium/terrarium/gateway/gateway.py` (MODIFY)

Changes to `Gateway`:

**`initialize()`** -- After the existing pack tool discovery loop, add:
```python
# Discover Tier 2 profile tools
if hasattr(responder, '_profile_loader'):
    profile_loader = responder._profile_loader
    for service_name, surface in profile_loader.get_all_surfaces().items():
        for op in surface.operations:
            if op.name and op.name not in self._tool_map:
                self._tool_map[op.name] = (service_name, op.name)
    logger.info(
        "Gateway: discovered %d profile tools from %d profiles",
        sum(len(s.operations) for s in profile_loader.get_all_surfaces().values()),
        len(profile_loader.list_profiles()),
    )
```

**`get_tool_manifest()`** -- After the existing pack loop, add:
```python
# Add Tier 2 profile tools
if hasattr(responder, '_profile_loader'):
    for service_name, surface in responder._profile_loader.get_all_surfaces().items():
        if protocol == "mcp":
            tools.extend(surface.get_mcp_tools())
        elif protocol == "http":
            tools.extend(surface.get_http_routes())
        elif protocol == "openai":
            tools.extend(op.to_openai_function() for op in surface.operations)
        elif protocol == "anthropic":
            tools.extend(op.to_anthropic_tool() for op in surface.operations)
```

This ensures:
- `MCP list_tools()` returns Tier 2 operations alongside Tier 1.
- HTTP `_mount_pack_routes()` auto-mounts Tier 2 HTTP paths (it already reads from `get_tool_manifest(protocol="http")`).
- The `_tool_map` lookup resolves Tier 2 actions for `handle_request()`.

---

### COMPONENT 7: App Wiring (`_inject_cross_engine_deps`)

**File**: `/Users/jana/workspace/terrarium/terrarium/app.py` (MODIFY)

Add after the existing responder/compiler wiring block in `_inject_cross_engine_deps()`:
```python
# Wire Tier 2 generator with LLM router
if self._llm_router and hasattr(responder, '_profile_loader'):
    from terrarium.engines.responder.tier2 import Tier2Generator
    responder._tier2 = Tier2Generator(
        llm_router=self._llm_router,
        state=state_engine,
    )
```

---

### COMPONENT 8: Infer Pipeline (Unknown Service -> Profile Generation)

**Purpose**: When the compiler encounters a service with no pack AND no profile, gather sources, ask LLM to generate a profile YAML, save to disk.

**File**: `/Users/jana/workspace/terrarium/terrarium/engines/world_compiler/infer_pipeline.py` (NEW)

```python
"""Service profile inference pipeline.

When an unknown service is encountered during compilation:
1. Gather sources: Context Hub docs, OpenAPI spec, Kernel primitives
2. Ask LLM to generate a ServiceProfileData as structured JSON
3. Validate the generated profile
4. Save as .profile.yaml to the profiles directory
5. Register with the ProfileLoader

Uses the LLM routing key "service_bootstrapper" (already configured in terrarium.toml).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from terrarium.kernel.context_hub import ContextHubProvider
from terrarium.kernel.openapi_provider import OpenAPIProvider
from terrarium.kernel.registry import SemanticRegistry
from terrarium.llm.router import LLMRouter
from terrarium.llm.types import LLMRequest
from terrarium.packs.profile_loader import ProfileLoader
from terrarium.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class InferPipeline:
    """Generates service profiles for unknown services."""

    def __init__(
        self,
        llm_router: LLMRouter,
        profile_loader: ProfileLoader,
        kernel: SemanticRegistry | None = None,
        context_hub: ContextHubProvider | None = None,
        openapi_provider: OpenAPIProvider | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self._llm_router = llm_router
        self._profile_loader = profile_loader
        self._kernel = kernel
        self._context_hub = context_hub or ContextHubProvider()
        self._openapi_provider = openapi_provider
        self._output_dir = Path(output_dir) if output_dir else (
            Path(__file__).resolve().parents[2] / "packs" / "profiles"
        )

    async def infer(self, service_name: str) -> ServiceProfileData | None:
        """Run the full inference pipeline for a service.
        
        Returns ServiceProfileData if successful, None if inference fails.
        """
        name = service_name.lower()
        logger.info("InferPipeline: starting inference for '%s'", name)

        # Step 1: Gather sources
        sources = await self._gather_sources(name)
        if not sources:
            logger.warning("InferPipeline: no sources found for '%s'", name)

        # Step 2: Get kernel classification
        category = ""
        primitives = []
        if self._kernel:
            category = self._kernel.get_category(name) or ""
            if category:
                primitives = self._kernel.get_primitives(category)

        # Step 3: Ask LLM to generate profile
        profile_data = await self._generate_profile(
            name, category, primitives, sources
        )
        if profile_data is None:
            return None

        # Step 4: Validate
        errors = self._validate_profile(profile_data)
        if errors:
            logger.warning(
                "InferPipeline: generated profile has validation issues: %s", errors
            )
            # Try once more with error feedback
            profile_data = await self._repair_profile(
                name, profile_data, errors, sources
            )
            if profile_data is None:
                return None

        # Step 5: Save to disk
        self._save_profile(profile_data)

        # Step 6: Register with loader
        self._profile_loader.register_profile(profile_data)

        logger.info(
            "InferPipeline: generated profile for '%s' with %d operations",
            name, len(profile_data.operations),
        )
        return profile_data

    async def _gather_sources(self, service_name: str) -> dict[str, Any]:
        """Gather all available documentation for the service."""
        sources: dict[str, Any] = {}

        # Context Hub
        try:
            if await self._context_hub.supports(service_name):
                docs = await self._context_hub.fetch(service_name)
                if docs:
                    sources["context_hub"] = docs
        except Exception as exc:
            logger.debug("Context Hub failed for %s: %s", service_name, exc)

        # OpenAPI
        if self._openapi_provider:
            try:
                if await self._openapi_provider.supports(service_name):
                    spec = await self._openapi_provider.fetch(service_name)
                    if spec:
                        sources["openapi"] = spec
            except Exception as exc:
                logger.debug("OpenAPI failed for %s: %s", service_name, exc)

        return sources

    async def _generate_profile(
        self,
        service_name: str,
        category: str,
        primitives: list[dict],
        sources: dict[str, Any],
    ) -> ServiceProfileData | None:
        """Ask LLM to generate a complete service profile."""
        system_prompt = self._build_infer_system_prompt()
        user_prompt = self._build_infer_user_prompt(
            service_name, category, primitives, sources
        )

        request = LLMRequest(
            system_prompt=system_prompt,
            user_content=user_prompt,
            max_tokens=8192,
            temperature=0.5,
        )
        response = await self._llm_router.route(
            request,
            engine_name="service_bootstrapper",
            use_case="default",
        )

        # Parse response
        try:
            from terrarium.engines.world_compiler.prompt_templates import PromptTemplate
            template = PromptTemplate(system="", user="")
            data = template.parse_json_response(response)
            return ServiceProfileData(**data)
        except Exception as exc:
            logger.warning("InferPipeline: failed to parse LLM response: %s", exc)
            return None

    def _build_infer_system_prompt(self) -> str:
        return """You are Terrarium's service profile generator.

Given information about a service (documentation, API specs, category),
generate a complete service profile as JSON.

The profile must contain:
- profile_name: lowercase service name
- service_name: lowercase service name  
- category: semantic category
- version: "1.0.0"
- fidelity_source: "bootstrapped"
- operations: list of API operations with parameters, response schemas
- entities: list of entity types with fields
- state_machines: list of state machines for entities with status fields
- error_modes: list of common error conditions
- behavioral_notes: list of service-specific behavioral rules
- examples: at least 2 request/response examples
- responder_prompt: system prompt for simulating this service's API

## Operation Format
Each operation:
{
  "name": "service_operation_name",
  "service": "service_name",
  "description": "what it does",
  "http_method": "GET|POST|PUT|DELETE",
  "http_path": "/api/path/{param}",
  "parameters": {"param_name": {"type": "string", "description": "..."}},
  "required_params": ["param_name"],
  "response_schema": {"type": "object", "properties": {...}, "required": [...]},
  "is_read_only": false,
  "creates_entity": "entity_type_or_null",
  "mutates_entity": "entity_type_or_null"
}

Generate 5-10 core operations that cover CRUD + search for the service's main entities.
Operation names MUST be prefixed with the service name (e.g., "jira_create_issue").

Output ONLY valid JSON. No markdown."""

    def _build_infer_user_prompt(
        self,
        service_name: str,
        category: str,
        primitives: list[dict],
        sources: dict[str, Any],
    ) -> str:
        parts = [f"Generate a service profile for: {service_name}"]
        if category:
            parts.append(f"Category: {category}")
        if primitives:
            parts.append(f"Category primitives: {json.dumps(primitives)}")

        if "context_hub" in sources:
            raw = sources["context_hub"].get("raw_content", "")
            # Truncate to avoid token overflow
            parts.append(f"## API Documentation\n{raw[:6000]}")

        if "openapi" in sources:
            ops = sources["openapi"].get("operations", [])
            parts.append(f"## OpenAPI Operations ({len(ops)} found)")
            for op in ops[:15]:  # Limit
                parts.append(f"- {op.get('name')}: {op.get('description', '')}")

        return "\n\n".join(parts)

    async def _repair_profile(
        self,
        service_name: str,
        profile: ServiceProfileData,
        errors: list[str],
        sources: dict[str, Any],
    ) -> ServiceProfileData | None:
        """Attempt to repair a generated profile."""
        request = LLMRequest(
            system_prompt="Repair the following service profile. Fix the listed errors. Output ONLY valid JSON.",
            user_content=f"Service: {service_name}\n\nErrors:\n{json.dumps(errors)}\n\nCurrent profile:\n{json.dumps(profile.model_dump(), indent=2)}",
            max_tokens=8192,
            temperature=0.3,
        )
        response = await self._llm_router.route(
            request, engine_name="service_bootstrapper"
        )
        try:
            from terrarium.engines.world_compiler.prompt_templates import PromptTemplate
            template = PromptTemplate(system="", user="")
            data = template.parse_json_response(response)
            return ServiceProfileData(**data)
        except Exception:
            return None

    def _validate_profile(self, profile: ServiceProfileData) -> list[str]:
        """Validate a generated profile."""
        errors = []
        if not profile.operations:
            errors.append("Profile has no operations")
        if not profile.entities:
            errors.append("Profile has no entities")
        for op in profile.operations:
            if not op.name:
                errors.append("Operation missing name")
            if not op.response_schema:
                errors.append(f"Operation '{op.name}' missing response_schema")
        # Check operation names are prefixed
        for op in profile.operations:
            if not op.name.startswith(profile.service_name):
                errors.append(f"Operation '{op.name}' not prefixed with service name '{profile.service_name}'")
        return errors

    def _save_profile(self, profile: ServiceProfileData) -> None:
        """Save profile to disk as YAML."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{profile.service_name}.profile.yaml"
        data = profile.model_dump(mode="json")
        with path.open("w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logger.info("InferPipeline: saved profile to %s", path)
```

---

### COMPONENT 9: Compiler Integration (Infer Pipeline Trigger)

**File**: `/Users/jana/workspace/terrarium/terrarium/engines/world_compiler/service_resolution.py` (MODIFY)

Add the infer pipeline to `CompilerServiceResolver`:

**Constructor change** -- add `infer_pipeline` parameter:
```python
def __init__(
    self,
    pack_registry: PackRegistry | None = None,
    kernel: SemanticRegistry | None = None,
    resolver: ServiceResolver | None = None,
    profile_loader: Any | None = None,  # ProfileLoader
    infer_pipeline: Any | None = None,  # InferPipeline
) -> None:
    self._packs = pack_registry
    self._kernel = kernel
    self._resolver = resolver
    self._profile_loader = profile_loader
    self._infer_pipeline = infer_pipeline
```

**New step in `resolve_one()` -- after Step 2 (profiled), before Steps 3-6 (external)**:
```python
# Step 2b: YAML profile (standalone, not extending a pack)
if self._profile_loader and self._profile_loader.has_profile(name):
    surface = self._profile_loader.get_surface(name)
    if surface:
        return ServiceResolution(
            service_name=service_name,
            spec_reference=str(spec_reference),
            surface=surface,
            resolution_source="tier2_yaml_profile",
        )
```

**New step at the end of `resolve_one()` -- after Steps 3-6 (external) fail**:
```python
# Step 7: Infer pipeline (generate profile from sources)
if self._infer_pipeline:
    try:
        profile = await self._infer_pipeline.infer(name)
        if profile:
            surface = self._profile_loader.get_surface(name)
            if surface:
                return ServiceResolution(
                    service_name=service_name,
                    spec_reference=str(spec_reference),
                    surface=surface,
                    resolution_source="tier2_inferred",
                )
    except Exception as exc:
        logger.warning("Infer pipeline failed for '%s': %s", name, exc)
```

---

### COMPONENT 10: App Wiring for Infer Pipeline

**File**: `/Users/jana/workspace/terrarium/terrarium/app.py` (MODIFY)

In `_inject_cross_engine_deps()`, after the CompilerServiceResolver creation:
```python
# Wire infer pipeline into compiler service resolver
if self._llm_router and hasattr(responder, '_profile_loader'):
    from terrarium.engines.world_compiler.infer_pipeline import InferPipeline
    from terrarium.kernel.context_hub import ContextHubProvider

    infer = InferPipeline(
        llm_router=self._llm_router,
        profile_loader=responder._profile_loader,
        kernel=existing_kernel,
        context_hub=ContextHubProvider(),
    )
    compiler._compiler_resolver = CompilerServiceResolver(
        pack_registry=pack_reg,
        kernel=existing_kernel,
        resolver=(
            getattr(existing, "_resolver", None) if existing else None
        ),
        profile_loader=responder._profile_loader,
        infer_pipeline=infer,
    )
```

---

### COMPONENT 11: TOML Configuration

**File**: `/Users/jana/workspace/terrarium/terrarium.toml` (MODIFY)

Add under `[responder]`:
```toml
profiles_dir = "terrarium/packs/profiles"
```

The existing routing key `[llm.routing.responder_tier2]` is already configured -- no change needed. The existing `[llm.routing.service_bootstrapper]` is already configured for the infer pipeline.

---

### COMPONENT 12: Tests

**File**: `/Users/jana/workspace/terrarium/tests/packs/test_profile_loader.py` (NEW)

Tests for ProfileLoader:
1. `test_load_yaml_profile()` -- Load the jira.profile.yaml, verify all fields parse correctly
2. `test_to_surface()` -- Convert ServiceProfileData to ServiceSurface, verify operations, entity_schemas, state_machines
3. `test_discover_flat()` -- Place a profile in a temp dir, call discover(), verify it's found
4. `test_discover_subdir()` -- Place a profile in a subdirectory, verify it's found
5. `test_register_profile()` -- Register a profile directly, verify has_profile() returns True
6. `test_get_mcp_tools()` -- Verify the surface produces valid MCP tool definitions
7. `test_get_http_routes()` -- Verify the surface produces valid HTTP routes
8. `test_invalid_yaml()` -- Verify bad YAML is logged and skipped
9. `test_surface_validate()` -- Call validate_surface() on a profile-derived surface

**File**: `/Users/jana/workspace/terrarium/tests/engines/test_tier2_generator.py` (NEW)

Tests for Tier2Generator:
1. `test_generate_basic()` -- Mock LLM returns valid JSON matching schema, verify ResponseProposal
2. `test_generate_with_state()` -- Verify state context is fetched and included in prompt
3. `test_generate_creates_entity()` -- Operation with `creates_entity`, verify StateDelta with operation="create"
4. `test_generate_mutates_entity()` -- Operation with `mutates_entity`, verify StateDelta with operation="update"
5. `test_fidelity_metadata()` -- Verify FidelityMetadata has tier=PROFILED, source=profile_name
6. `test_schema_validation_warning()` -- LLM response violates schema, verify response still returned with warning
7. `test_unknown_action()` -- Action not in profile, verify error proposal

**File**: `/Users/jana/workspace/terrarium/tests/engines/test_infer_pipeline.py` (NEW)

Tests for InferPipeline:
1. `test_infer_with_context_hub()` -- Mock Context Hub returns docs, verify profile generated
2. `test_infer_with_kernel_only()` -- No external sources, kernel provides category/primitives
3. `test_infer_saves_yaml()` -- Verify profile YAML file written to disk
4. `test_infer_registers_with_loader()` -- Verify profile_loader.has_profile() after infer
5. `test_infer_repair()` -- First LLM response has errors, verify repair attempt
6. `test_infer_no_sources()` -- No Context Hub, no OpenAPI, verify still attempts with kernel

**File**: `/Users/jana/workspace/terrarium/tests/engines/test_responder.py` (MODIFY -- fill existing stubs)

Fill in the existing test stubs:
1. `test_responder_tier1_dispatch()` -- Verify Tier 1 path works (existing stub)
2. `test_responder_tier2_generate()` -- Create profile, mock LLM, call execute(), verify Tier 2 path
3. `test_responder_bootstrapped_service()` -- Register an inferred profile, verify it routes through Tier 2
4. `test_responder_fallback()` -- No pack, no profile, verify ERROR verdict

**File**: `/Users/jana/workspace/terrarium/tests/integration/test_tier2_e2e.py` (NEW)

End-to-end integration test:
1. `test_jira_profile_to_mcp_tools()` -- Load jira profile, verify MCP tools include jira_create_issue
2. `test_jira_profile_to_http_routes()` -- Load jira profile, verify HTTP routes include POST /rest/api/3/issue
3. `test_gateway_discovers_tier2_tools()` -- Full app startup with profiles, verify gateway._tool_map includes jira tools
4. `test_full_flow_tier2_action()` -- Handle a jira_create_issue action through the full pipeline with mocked LLM

---

### COMPLETE FLOW WALKTHROUGH

```
1. User says "jira" in world YAML
   → YAML parser extracts service_specs = {"jira": "jira"}
   
2. CompilerServiceResolver.resolve_one("jira", "jira", "auto")
   → Step 1: _packs.get_pack("jira") → PackNotFoundError (no Tier 1)
   → Step 2: _packs.get_profiles_for_pack("jira") → [] (no Python profile)
   → Step 2b: _profile_loader.has_profile("jira") → True (jira.profile.yaml exists!)
     → _profile_loader.get_surface("jira") → ServiceSurface
     → Return ServiceResolution(source="tier2_yaml_profile")
   
   If no profile exists:
   → Step 3-6: ServiceResolver tries Context Hub, OpenAPI, kernel
   → Step 7: _infer_pipeline.infer("jira")
     → _gather_sources("jira") → Context Hub docs
     → _generate_profile() → LLM produces ServiceProfileData
     → _save_profile() → writes jira.profile.yaml
     → _profile_loader.register_profile() → registered
     → Return ServiceResolution(source="tier2_inferred")

3. Compile: profile → ServiceSurface → entity generation
   → WorldPlan.services["jira"].surface has operations + entity_schemas
   → WorldDataGenerator generates "issue", "sprint", "comment" entities
   → Entities populated into StateEngine

4. Runtime: agent calls jira_create_issue
   → Gateway.handle_request("mcp", "mcp-agent", "jira_create_issue", {...})
   → _tool_map["jira_create_issue"] = ("jira", "jira_create_issue")
   → app.handle_action() → 7-step pipeline
   
   → Step 5 (responder): WorldResponderEngine.execute(ctx)
     → _tier1.has_pack_for_tool("jira_create_issue") → False
     → _find_profile_for_action("jira_create_issue") → ServiceProfileData
     → _tier2.generate(ctx, profile) 
       → Builds system prompt from responder_prompt + behavioral_notes
       → Builds user prompt with input_data + current entity state
       → LLM generates JSON response matching response_schema
       → SchemaValidator validates response
       → Extracts StateDelta(entity_type="issue", operation="create")
       → Returns ResponseProposal with FidelityMetadata(tier=PROFILED)
   
   → Step 6 (validation): validates StateDelta structure
   → Step 7 (commit): StateEngine persists new issue entity

5. MCP: list_tools() includes jira_create_issue
   → Gateway.get_tool_manifest(protocol="mcp")
   → Loops through pack_registry.list_packs() → Tier 1 tools
   → Loops through profile_loader.get_all_surfaces() → Tier 2 tools
   → Returns combined list including jira_create_issue

6. HTTP: POST /rest/api/3/issue works
   → HTTPRestAdapter._mount_pack_routes(app, gateway)
   → get_tool_manifest(protocol="http") returns http_path="/rest/api/3/issue"
   → app.post("/rest/api/3/issue")(handler) mounted
   → Handler calls gateway.handle_request() → same pipeline as MCP
```

---

### DEPENDENCY GRAPH (Implementation Order)

```
Phase 1 (no dependencies):
  1. profile_schema.py — Pure Pydantic models
  2. jira.profile.yaml — Pure data file

Phase 2 (depends on Phase 1):
  3. profile_loader.py — Depends on profile_schema, surface
  
Phase 3 (depends on Phase 2):
  4. tier2.py — Depends on profile_schema, LLM router, SchemaValidator
  5. infer_pipeline.py — Depends on profile_loader, profile_schema, LLM router

Phase 4 (integration, depends on Phase 3):
  6. engine.py (responder) — Wire profile_loader + tier2 into execute()
  7. service_resolution.py — Add profile_loader + infer steps
  8. gateway.py — Add Tier 2 tool discovery
  9. app.py — Wire everything in _inject_cross_engine_deps()

Phase 5 (tests, depends on Phase 4):
  10. test_profile_loader.py
  11. test_tier2_generator.py
  12. test_infer_pipeline.py
  13. test_responder.py (fill stubs)
  14. test_tier2_e2e.py
```

---

### Critical Files for Implementation

- `/Users/jana/workspace/terrarium/terrarium/packs/profile_schema.py` - New file: core Pydantic models for YAML profiles (ServiceProfileData, ProfileOperation, etc.). Every other component depends on this.
- `/Users/jana/workspace/terrarium/terrarium/packs/profile_loader.py` - New file: loads .profile.yaml files and converts to ServiceSurface. Bridge between YAML data and the runtime.
- `/Users/jana/workspace/terrarium/terrarium/engines/responder/tier2.py` - Existing stub to replace: LLM-constrained response generation using profile as constraint template.
- `/Users/jana/workspace/terrarium/terrarium/engines/responder/engine.py` - Existing file to modify: add Tier 2 fallback dispatch path in execute(), wire profile_loader and tier2 in _on_initialize().
- `/Users/jana/workspace/terrarium/terrarium/gateway/gateway.py` - Existing file to modify: add Tier 2 tool discovery in initialize() and get_tool_manifest() so MCP/HTTP adapters expose profiled service operations.