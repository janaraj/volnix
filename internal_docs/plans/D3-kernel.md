# Phase D3: Service Resolution Framework

## Context

**Phase:** D3 (third Phase D — feeds D4 compiler)
**Module:** `terrarium/kernel/`
**Goal:** Build the service resolution framework: classify services, fetch real API specs, produce universal ServiceSurface models that support BOTH MCP tool exposure AND HTTP REST routes.

**The core mechanic:** Get the spec → Generate the data → Simulate the behavior.

**How agents connect (Phase E1 implements, D3 provides the data model):**
```
Mode 1: MCP (for AI agents — Claude Code, Codex, etc.)
  Agent ←MCP→ Terrarium MCP Server → sees tools: stripe_refunds_create, gmail_messages_list
  Tool names and schemas come from ServiceSurface.operations[].to_mcp_tool()

Mode 2: HTTP/REST (simulating real APIs)
  Agent ←HTTP→ Terrarium HTTP Server → calls: POST /v1/refunds, GET /gmail/v1/users/me/messages
  Routes and schemas come from ServiceSurface.operations[].to_http_route()

Both modes go through the same pipeline:
  External request → Gateway translates → ActionContext → 7-step pipeline → Response
```

**Resolution chain (order of confidence):**
```
1. Tier 1 Pack (compiled code, deterministic)
2. Tier 2 Profile (curated, community-contributed)
3. Context Hub (real API docs for 70+ services via chub CLI)
4. OpenAPI spec (structured spec parsing)
5. LLM inference (D4 adds this — uses kernel primitives)
6. Kernel classification (pure fallback — category + primitives)
```

---

## Dependencies

**Add to `pyproject.toml`:**
```toml
# Context Hub CLI wrapper (npm package, called via subprocess)
# No Python dependency — we shell out to `chub` CLI
# User installs: npm install -g @anthropic/context-hub
```

No new Python deps. Context Hub is accessed via `chub` CLI subprocess (same pattern as ACP/CLI providers in B3). `tomllib` is Python 3.11+ built-in.

---

## Implementation — Detailed Code

### File 1: `terrarium/kernel/surface.py` — APIOperation + ServiceSurface (NEW)

```python
"""Service surface models — the universal API operation abstraction.

An APIOperation captures a single API endpoint/method with BOTH its HTTP
binding (method, path) and MCP tool representation (name, inputSchema).
A ServiceSurface aggregates all operations for a service plus entity schemas
and state machines.

The agent sees whichever protocol it connects with:
- MCP: operation.to_mcp_tool() → {name, description, inputSchema}
- HTTP: operation.to_http_route() → {method, path}
- OpenAI: operation.to_openai_function() → {name, parameters}
Same underlying operation, multiple external representations.
"""
from __future__ import annotations
from typing import Any, ClassVar
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

    # Semantic metadata
    is_read_only: bool = False
    creates_entity: str | None = None            # Entity type created
    mutates_entity: str | None = None            # Entity type modified
    side_effects: list[str] = Field(default_factory=list)

    def to_mcp_tool(self) -> dict[str, Any]:
        """Generate MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required_params,
            },
        }

    def to_http_route(self) -> dict[str, str]:
        """Generate HTTP route definition."""
        return {
            "method": self.http_method,
            "path": self.http_path,
            "content_type": self.content_type,
        }

    def to_openai_function(self) -> dict[str, Any]:
        """Generate OpenAI function calling definition."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required_params,
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

    Agent sees MCP tools or HTTP routes — same underlying operations.
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
        return errors
```

### File 2: `terrarium/kernel/registry.py` — SemanticRegistry (implement stubs)

```python
"""Semantic Kernel — static service classification registry.

Maps service names to categories and provides canonical primitives.
39 pre-mapped services across 9 categories. Dynamic registration supported.
"""
import logging
import tomllib
from pathlib import Path
from typing import Any

from terrarium.kernel.categories import CATEGORIES, SemanticCategory
from terrarium.kernel.primitives import get_primitives_for_category, SemanticPrimitive

logger = logging.getLogger(__name__)


class SemanticRegistry:

    def __init__(self) -> None:
        self._categories: dict[str, SemanticCategory] = {}
        self._service_map: dict[str, str] = {}
        self._initialized = False

    async def initialize(self) -> None:
        self._categories = dict(CATEGORIES)
        toml_path = Path(__file__).parent / "data" / "services.toml"
        if toml_path.exists():
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
            for svc, cat in data.get("services", {}).items():
                if cat in self._categories:
                    self._service_map[svc.lower()] = cat
                else:
                    logger.warning("Service '%s' maps to unknown category '%s'", svc, cat)
        self._initialized = True
        logger.info("Kernel: %d categories, %d services", len(self._categories), len(self._service_map))

    def get_category(self, service_name: str) -> str | None:
        return self._service_map.get(service_name.lower())

    def get_primitives(self, category: str) -> list[dict[str, Any]]:
        return [p.model_dump() for p in get_primitives_for_category(category)]

    def get_service_mapping(self, service_name: str) -> dict[str, Any] | None:
        cat = self.get_category(service_name)
        if cat is None:
            return None
        cat_obj = self._categories.get(cat)
        return {
            "service": service_name,
            "category": cat,
            "category_description": cat_obj.description if cat_obj else "",
            "primitives": [p.name for p in get_primitives_for_category(cat)],
        }

    def list_categories(self) -> list[str]:
        return sorted(self._categories.keys())

    def list_services(self, category: str | None = None) -> list[str]:
        if category is None:
            return sorted(self._service_map.keys())
        return sorted(s for s, c in self._service_map.items() if c == category)

    def register_service(self, service_name: str, category: str) -> None:
        if category not in self._categories:
            raise ValueError(f"Unknown category: '{category}'. Valid: {self.list_categories()}")
        self._service_map[service_name.lower()] = category

    def has_service(self, service_name: str) -> bool:
        return service_name.lower() in self._service_map

    def has_category(self, category: str) -> bool:
        return category in self._categories
```

### File 3: `terrarium/kernel/external_spec.py` — Protocol (NEW)

```python
"""External spec provider protocol.

Any source of API specifications implements this protocol:
- ContextHubProvider (chub CLI)
- OpenAPIProvider (parse spec files/URLs)
- Future: MCP manifest provider, etc.
"""
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExternalSpecProvider(Protocol):
    """Protocol for external API spec sources."""
    provider_name: str

    async def is_available(self) -> bool:
        """Check if this provider is accessible.""" ...

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Fetch raw spec for a service. Returns None if not available.""" ...

    async def supports(self, service_name: str) -> bool:
        """Quick check if this provider likely has the service.""" ...
```

### File 4: `terrarium/kernel/context_hub.py` — Context Hub integration (NEW)

```python
"""Context Hub integration — fetch real API docs for 70+ services.

Uses the `chub` CLI from @anthropic/context-hub npm package.
Install: npm install -g @anthropic/context-hub

The chub CLI returns structured API documentation:
  chub get stripe/api → endpoint descriptions, parameter schemas,
  auth patterns, common gotchas, response formats.

This is the BEST source for unknown services because it has
real, curated API documentation — not LLM inference.
"""
import asyncio
import json
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)


class ContextHubProvider:
    """Fetches API docs from Context Hub via chub CLI."""

    provider_name = "context_hub"

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._command = "chub"

    async def is_available(self) -> bool:
        """Check if chub CLI is installed."""
        return shutil.which(self._command) is not None

    async def supports(self, service_name: str) -> bool:
        """Check if Context Hub likely has this service.

        Quick heuristic: check if the service name is in the known catalog.
        For a more accurate check, we'd need to query chub list.
        """
        # Known Context Hub services (subset — full list from npm package)
        _KNOWN = {
            "stripe", "github", "slack", "gmail", "twilio", "sendgrid",
            "openai", "anthropic", "firebase", "supabase", "vercel",
            "aws", "gcp", "azure", "shopify", "salesforce", "hubspot",
            "notion", "airtable", "linear", "jira", "asana",
            "datadog", "pagerduty", "sentry", "grafana",
            # ... 70+ more
        }
        return service_name.lower() in _KNOWN

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Fetch API documentation via chub get {service}/api.

        Returns structured dict with raw_content, endpoints (if parseable),
        and metadata. Returns None if chub not installed or service not found.
        """
        if not await self.is_available():
            logger.debug("chub CLI not installed — skipping Context Hub")
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                self._command, "get", f"{service_name}/api",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )

            if proc.returncode != 0:
                logger.debug("chub get %s/api failed (rc=%d): %s",
                             service_name, proc.returncode, stderr.decode()[:200])
                return None

            content = stdout.decode()
            if not content.strip():
                return None

            return {
                "source": "context_hub",
                "service": service_name,
                "raw_content": content,
                "content_type": "markdown",
                # Future: parse endpoints, schemas from the markdown
            }

        except asyncio.TimeoutError:
            logger.warning("chub get %s/api timed out after %.0fs", service_name, self._timeout)
            return None
        except FileNotFoundError:
            logger.debug("chub command not found")
            return None
        except Exception as exc:
            logger.warning("chub get %s/api error: %s", service_name, exc)
            return None

    async def list_available(self) -> list[str]:
        """List services available in Context Hub (if chub supports it)."""
        if not await self.is_available():
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                self._command, "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            if proc.returncode == 0:
                return [line.strip() for line in stdout.decode().splitlines() if line.strip()]
        except Exception:
            pass
        return []
```

### File 5: `terrarium/kernel/openapi_provider.py` — OpenAPI spec parsing (NEW)

```python
"""OpenAPI/Swagger spec provider.

Parses OpenAPI 3.x or Swagger 2.x specs (YAML or JSON) into
structured service information. Accepts file paths or URLs.
"""
import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class OpenAPIProvider:
    """Parses OpenAPI specs into structured API information."""

    provider_name = "openapi"

    def __init__(self, spec_dir: str | None = None) -> None:
        self._spec_dir = Path(spec_dir) if spec_dir else None

    async def is_available(self) -> bool:
        """OpenAPI provider is always available (it's a parser)."""
        return True

    async def supports(self, service_name: str) -> bool:
        """Check if we have a local spec file for this service."""
        if self._spec_dir and (self._spec_dir / f"{service_name}.yaml").exists():
            return True
        if self._spec_dir and (self._spec_dir / f"{service_name}.json").exists():
            return True
        return False

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Parse an OpenAPI spec for a service."""
        if self._spec_dir is None:
            return None

        # Try YAML then JSON
        for ext in (".yaml", ".yml", ".json"):
            path = self._spec_dir / f"{service_name}{ext}"
            if path.exists():
                return self._parse_spec(path)
        return None

    def _parse_spec(self, path: Path) -> dict[str, Any]:
        """Parse an OpenAPI spec file into structured dict."""
        with path.open("r") as f:
            if path.suffix == ".json":
                spec = json.load(f)
            else:
                spec = yaml.safe_load(f)

        operations = []
        paths = spec.get("paths", {})
        for path_str, methods in paths.items():
            for method, details in methods.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    op_id = details.get("operationId", f"{method}_{path_str}")
                    operations.append({
                        "name": op_id,
                        "description": details.get("summary", ""),
                        "http_method": method.upper(),
                        "http_path": path_str,
                        "parameters": self._extract_parameters(details),
                        "response_schema": self._extract_response(details),
                    })

        return {
            "source": "openapi",
            "service": path.stem,
            "title": spec.get("info", {}).get("title", ""),
            "version": spec.get("info", {}).get("version", ""),
            "operations": operations,
            "raw_content": str(path),
        }

    def _extract_parameters(self, operation: dict) -> dict[str, Any]:
        """Extract parameter schemas from an OpenAPI operation."""
        params = {}
        for p in operation.get("parameters", []):
            params[p["name"]] = p.get("schema", {"type": "string"})
        # Also check requestBody
        body = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
        if body.get("properties"):
            params.update(body["properties"])
        return params

    def _extract_response(self, operation: dict) -> dict[str, Any]:
        """Extract response schema from an OpenAPI operation."""
        responses = operation.get("responses", {})
        for code in ("200", "201", "204"):
            if code in responses:
                content = responses[code].get("content", {}).get("application/json", {})
                return content.get("schema", {})
        return {}
```

### File 6: `terrarium/kernel/resolver.py` — Service Resolution Chain (NEW)

```python
"""Service resolver — orchestrates the resolution chain.

Tries sources in confidence order:
1. Tier 1 Pack
2. Tier 2 Profile
3. Context Hub
4. OpenAPI spec
5. LLM inference (D4 callback)
6. Kernel classification (primitives only)
"""
import logging
from typing import Any, Callable, Awaitable

from terrarium.kernel.external_spec import ExternalSpecProvider
from terrarium.kernel.registry import SemanticRegistry
from terrarium.kernel.surface import APIOperation, ServiceSurface

logger = logging.getLogger(__name__)

# Type for the LLM inference callback (injected by D4)
LLMInferCallback = Callable[[str, str, list[dict]], Awaitable[ServiceSurface | None]]


class ServiceResolver:
    """Resolves a service name to a ServiceSurface.

    The resolution chain:
    1. Pack (Tier 1) — from pack_registry
    2. Profile (Tier 2) — from pack_registry profiles
    3. External specs (Context Hub, OpenAPI) — from providers list
    4. LLM inference — from injected callback (D4 adds this)
    5. Kernel classification — primitives as weak signal
    """

    def __init__(
        self,
        kernel: SemanticRegistry,
        providers: list[ExternalSpecProvider] | None = None,
        llm_infer: LLMInferCallback | None = None,
    ) -> None:
        self._kernel = kernel
        self._providers = providers or []
        self._llm_infer = llm_infer  # D4 injects this

    async def resolve(self, service_name: str) -> ServiceSurface | None:
        """Try each source in order. Return first successful resolution."""
        name = service_name.lower()

        # Steps 1-2 (pack/profile) are handled by the caller (D4 compiler)
        # because they require PackRegistry which isn't a kernel dependency.
        # This resolver handles steps 3-6.

        # Step 3-4: External spec providers
        for provider in self._providers:
            try:
                if await provider.is_available() and await provider.supports(name):
                    spec = await provider.fetch(name)
                    if spec:
                        surface = self._surface_from_spec(spec, name, provider.provider_name)
                        if surface:
                            logger.info("Resolved '%s' via %s", name, provider.provider_name)
                            return surface
            except Exception as exc:
                logger.warning("Provider %s failed for '%s': %s", provider.provider_name, name, exc)

        # Step 5: LLM inference (if D4 injected the callback)
        if self._llm_infer:
            category = self._kernel.get_category(name)
            primitives = self._kernel.get_primitives(category) if category else []
            try:
                surface = await self._llm_infer(name, category or "", primitives)
                if surface:
                    logger.info("Resolved '%s' via LLM inference", name)
                    return surface
            except Exception as exc:
                logger.warning("LLM inference failed for '%s': %s", name, exc)

        # Step 6: Kernel classification (weakest signal)
        category = self._kernel.get_category(name)
        if category:
            primitives = self._kernel.get_primitives(category)
            logger.info("Resolved '%s' via kernel classification → %s", name, category)
            return ServiceSurface(
                service_name=name,
                category=category,
                source="kernel_inference",
                fidelity_tier=2,
                operations=[],
                entity_schemas={
                    p["name"]: {"type": "object", "fields": p.get("fields", {})}
                    for p in primitives
                },
                state_machines={},
                confidence=0.2,
            )

        return None

    def _surface_from_spec(self, spec: dict, service_name: str, source: str) -> ServiceSurface | None:
        """Convert an external spec dict to a ServiceSurface."""
        category = self._kernel.get_category(service_name) or "unknown"
        operations = []

        # If spec has parsed operations (from OpenAPI)
        for op_data in spec.get("operations", []):
            operations.append(APIOperation(
                name=op_data.get("name", ""),
                service=service_name,
                description=op_data.get("description", ""),
                http_method=op_data.get("http_method", "POST"),
                http_path=op_data.get("http_path", ""),
                parameters=op_data.get("parameters", {}),
                response_schema=op_data.get("response_schema", {}),
            ))

        return ServiceSurface(
            service_name=service_name,
            category=category,
            source=source,
            fidelity_tier=2,
            operations=operations,
            confidence=0.7 if source == "context_hub" else 0.5,
            raw_spec=spec.get("raw_content", ""),
        )
```

### File 7: `terrarium/kernel/__init__.py` — Updated exports

```python
from terrarium.kernel.categories import CATEGORIES, SemanticCategory
from terrarium.kernel.primitives import SemanticPrimitive, get_primitives_for_category
from terrarium.kernel.registry import SemanticRegistry
from terrarium.kernel.surface import APIOperation, ServiceSurface
from terrarium.kernel.external_spec import ExternalSpecProvider
from terrarium.kernel.context_hub import ContextHubProvider
from terrarium.kernel.openapi_provider import OpenAPIProvider
from terrarium.kernel.resolver import ServiceResolver

__all__ = [
    "CATEGORIES", "SemanticCategory", "SemanticPrimitive", "SemanticRegistry",
    "APIOperation", "ServiceSurface", "ExternalSpecProvider",
    "ContextHubProvider", "OpenAPIProvider", "ServiceResolver",
    "get_primitives_for_category",
]
```

---

## Test Harness (~55 tests)

### test_categories.py (5) + test_primitives.py (6) + test_registry.py (14) — as before

### test_surface.py (~12 tests — NEW)
| Test | Validates |
|------|-----------|
| `test_api_operation_creation` | All fields set correctly |
| `test_to_mcp_tool` | Generates {name, description, inputSchema} |
| `test_to_http_route` | Generates {method, path, content_type} |
| `test_to_openai_function` | Generates OpenAI function format |
| `test_to_anthropic_tool` | Generates Anthropic tool format |
| `test_service_surface_get_mcp_tools` | All operations as MCP list |
| `test_service_surface_get_http_routes` | All operations as HTTP list |
| `test_get_operation_by_name` | Lookup works |
| `test_validate_surface_complete` | Valid surface → no errors |
| `test_validate_surface_missing_ops` | Missing operations → error |
| `test_validate_surface_missing_response` | Missing response_schema → error |
| `test_stripe_refund_operation_e2e` | Full Stripe refund → MCP tool + HTTP route |

### test_context_hub.py (~5 tests)
| Test | Validates |
|------|-----------|
| `test_is_available_missing` | False when chub not installed |
| `test_fetch_unavailable` | Returns None gracefully |
| `test_supports_known_service` | "stripe" → True |
| `test_protocol_compliance` | Satisfies ExternalSpecProvider |
| `test_timeout_handling` | Timeout → None |

### test_openapi_provider.py (~5 tests — NEW)
| Test | Validates |
|------|-----------|
| `test_parse_simple_spec` | YAML spec → operations extracted |
| `test_parse_parameters` | Path + query + body params extracted |
| `test_parse_response_schema` | 200 response schema extracted |
| `test_supports_local_file` | Finds spec file in spec_dir |
| `test_missing_spec_returns_none` | Unknown service → None |

### test_resolver.py (~8 tests — NEW)
| Test | Validates |
|------|-----------|
| `test_resolve_via_context_hub` | Mock provider → ServiceSurface |
| `test_resolve_falls_to_kernel` | No provider → kernel classification |
| `test_resolve_unknown_service` | Returns None |
| `test_resolution_order` | First provider checked first |
| `test_confidence_levels` | context_hub=0.7, openapi=0.5, kernel=0.2 |
| `test_surface_from_openapi_spec` | Parsed spec → operations with HTTP bindings |
| `test_resolver_with_no_providers` | Falls through to kernel |
| `test_llm_callback_invoked` | D4 callback called when providers fail |

### test_architectural_validation.py (~5 tests — NEW, for promotion)
| Test | Validates |
|------|-----------|
| `test_surface_validate_for_promotion` | validate_surface() catches incomplete surfaces |
| `test_email_pack_produces_valid_surface` | EmailPack → ServiceSurface → validate_surface() passes |
| `test_surface_has_mcp_and_http` | Every operation has both MCP and HTTP representations |
| `test_operations_have_response_schemas` | All operations have non-empty response_schema |
| `test_entity_schemas_present` | ServiceSurface has at least one entity schema |

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `terrarium/kernel/surface.py` | **CREATE** — APIOperation + ServiceSurface |
| `terrarium/kernel/registry.py` | **IMPLEMENT** — SemanticRegistry (10 methods) |
| `terrarium/kernel/external_spec.py` | **CREATE** — ExternalSpecProvider Protocol |
| `terrarium/kernel/context_hub.py` | **CREATE** — ContextHubProvider |
| `terrarium/kernel/openapi_provider.py` | **CREATE** — OpenAPIProvider |
| `terrarium/kernel/resolver.py` | **CREATE** — ServiceResolver |
| `terrarium/kernel/__init__.py` | **UPDATE** — exports |
| `tests/kernel/test_categories.py` | **IMPLEMENT** — 5 tests |
| `tests/kernel/test_primitives.py` | **IMPLEMENT** — 6 tests |
| `tests/kernel/test_registry.py` | **IMPLEMENT** — 14 tests |
| `tests/kernel/test_surface.py` | **CREATE** — 12 tests |
| `tests/kernel/test_context_hub.py` | **CREATE** — 5 tests |
| `tests/kernel/test_openapi_provider.py` | **CREATE** — 5 tests |
| `tests/kernel/test_resolver.py` | **CREATE** — 8 tests |
| `tests/kernel/test_architectural_validation.py` | **CREATE** — 5 tests |

---

## Verification

1. `pytest tests/kernel/ -v` — ALL ~55 pass
2. `pytest tests/ -q` — 880 + ~55 = ~935 passed
3. Manual:
```python
import asyncio
from terrarium.kernel import SemanticRegistry, ServiceResolver, ContextHubProvider, APIOperation, ServiceSurface

async def main():
    kernel = SemanticRegistry()
    await kernel.initialize()
    print(f"Categories: {len(kernel.list_categories())}")
    print(f"Services: {len(kernel.list_services())}")
    print(f"stripe → {kernel.get_category('stripe')}")

    # Create a Stripe refund operation
    op = APIOperation(
        name="stripe_refunds_create", service="stripe",
        description="Create a refund",
        http_method="POST", http_path="/v1/refunds",
        parameters={"charge": {"type": "string"}, "amount": {"type": "integer"}},
        required_params=["charge"],
        creates_entity="refund", mutates_entity="charge",
    )
    print(f"MCP: {op.to_mcp_tool()['name']}")
    print(f"HTTP: {op.to_http_route()}")

asyncio.run(main())
```

---

## Post-Implementation

1. Save plan to `plans/D3-kernel.md`
2. Update IMPLEMENTATION_STATUS.md
3. Next: D4 (world compiler — uses kernel + resolver + D1 + D2)
