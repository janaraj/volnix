"""Service surface models -- the universal API operation abstraction.

An APIOperation captures a single API endpoint/method with BOTH its HTTP
binding (method, path) and MCP tool representation (name, inputSchema).
A ServiceSurface aggregates all operations for a service plus entity schemas
and state machines.

The agent sees whichever protocol it connects with:
- MCP: operation.to_mcp_tool() -> {name, description, inputSchema}
- HTTP: operation.to_http_route() -> {method, path}
- OpenAI: operation.to_openai_function() -> {type:"function", function:{...}}
Same underlying operation, multiple external representations.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class APIOperation(BaseModel, frozen=True):
    """A single API operation (e.g., stripe.refunds.create).

    Protocol-agnostic: captures the abstract operation.
    Protocol-specific views derived via to_mcp_tool(), to_http_route(), etc.
    """
    # Identity
    name: str                                    # "stripe_refunds_create"
    service: str                                 # "stripe"
    description: str = ""                        # Human-readable

    # HTTP binding (how the real API exposes this)
    http_method: str = "POST"                    # GET, POST, PUT, PATCH, DELETE
    http_path: str = ""                          # "/v1/refunds"

    # Request schema
    parameters: dict[str, Any] = Field(default_factory=dict)
    required_params: list[str] = Field(default_factory=list)
    content_type: str = "application/json"

    # Response schema
    response_schema: dict[str, Any] = Field(default_factory=dict)
    response_status_codes: dict[int, str] = Field(
        default_factory=dict
    )  # e.g. {200: "OK", 404: "Not Found"}

    # Auth & pagination
    auth_type: str = ""                          # "bearer", "api_key", "oauth2"
    pagination_style: str | None = None          # "cursor", "offset", "none"

    # Semantic metadata
    is_read_only: bool = False
    creates_entity: str | None = None            # Entity type created
    mutates_entity: str | None = None            # Entity type modified
    side_effects: list[str] = Field(default_factory=list)

    def to_mcp_tool(self) -> dict[str, Any]:
        """Generate MCP tool definition."""
        tool: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required_params,
            },
        }
        # FIX-25: Add MCP annotations for read-only and destructive hints
        if self.is_read_only:
            tool.setdefault("annotations", {})["readOnlyHint"] = True
        if self.mutates_entity:
            tool.setdefault("annotations", {})["destructiveHint"] = True
        return tool

    def to_http_route(self) -> dict[str, str]:
        """Generate HTTP route definition."""
        return {
            "method": self.http_method,
            "path": self.http_path,
            "content_type": self.content_type,
            "tool_name": self.name,
        }

    def to_openai_function(self) -> dict[str, Any]:
        """Generate OpenAI function calling definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required_params,
                },
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Generate Anthropic tool use definition."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required_params,
            },
        }


class ServiceSurface(BaseModel, frozen=True):
    """Complete specification for simulating a service.

    Produced by any resolution source. Contains operations with BOTH
    HTTP bindings and MCP tool definitions.

    Agent sees MCP tools or HTTP routes -- same underlying operations.
    Pipeline sees ActionContext derived from either protocol.
    """
    service_name: str
    category: str
    source: str                                  # "tier1_pack", "context_hub", "openapi", etc.
    fidelity_tier: int

    operations: list[APIOperation] = Field(default_factory=list)
    entity_schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    state_machines: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Metadata
    confidence: float = 1.0
    auth_pattern: str = ""                       # "bearer", "api_key", "oauth2"
    base_url: str = ""                           # Real API base URL for reference
    raw_spec: str = ""                           # Original spec for audit

    @classmethod
    def from_pack(cls, pack: Any) -> ServiceSurface:
        """Convert a ServicePack to a ServiceSurface."""
        operations = []
        for tool in (pack.get_tools() or []):
            params = tool.get("parameters", {}).get("properties", {})
            required = tool.get("parameters", {}).get("required", [])
            operations.append(APIOperation(
                name=tool["name"],
                service=pack.pack_name,
                description=tool.get("description", ""),
                http_path=tool.get("http_path", ""),
                http_method=tool.get("http_method", "POST"),
                parameters=params,
                required_params=required,
                response_schema=tool.get("response_schema", {}),
            ))
        return cls(
            service_name=pack.pack_name,
            category=pack.category,
            source="tier1_pack",
            fidelity_tier=pack.fidelity_tier,
            operations=operations,
            entity_schemas=pack.get_entity_schemas(),
            state_machines=pack.get_state_machines(),
            confidence=1.0,
        )

    def get_mcp_tools(self) -> list[dict[str, Any]]:
        """All operations as MCP tools."""
        return [op.to_mcp_tool() for op in self.operations]

    def get_http_routes(self) -> list[dict[str, str]]:
        """All operations as HTTP routes."""
        return [op.to_http_route() for op in self.operations if op.http_path]

    def get_operation(self, name: str) -> APIOperation | None:
        """Look up operation by name."""
        for op in self.operations:
            if op.name == name:
                return op
        return None

    def get_operation_names(self) -> list[str]:
        """All operation names."""
        return [op.name for op in self.operations]

    def validate_surface(self) -> list[str]:
        """Validate the surface is complete and consistent.

        Returns list of validation errors (empty = valid).
        Used during promotion to verify quality before Tier upgrade.
        """
        errors = []
        if not self.operations:
            errors.append("ServiceSurface has no operations")
        for op in self.operations:
            if not op.name:
                errors.append("Operation missing name")
            if not op.parameters and not op.is_read_only:
                errors.append(f"Mutation operation '{op.name}' has no parameters")
            if not op.response_schema:
                errors.append(f"Operation '{op.name}' has no response_schema")
        if not self.entity_schemas:
            errors.append("ServiceSurface has no entity_schemas")
        # FIX-06: Check required_params are subset of parameters
        for op in self.operations:
            for rp in op.required_params:
                if rp not in op.parameters:
                    errors.append(f"Required param '{rp}' not in parameters for '{op.name}'")
        # FIX-06: Check no duplicate operation names
        names = [op.name for op in self.operations]
        if len(names) != len(set(names)):
            errors.append("Duplicate operation names detected")
        return errors

    def assert_promotable(self) -> None:
        """Raise if surface is not ready for tier promotion."""
        errors = self.validate_surface()
        if errors:
            raise ValueError(f"Surface not promotable: {errors}")
