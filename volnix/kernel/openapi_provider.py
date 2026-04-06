"""OpenAPI spec provider.

Parses OpenAPI 3.x specs (YAML or JSON) into structured service information.
Accepts file paths or URLs. OpenAPI 3.x only. Swagger 2.x is not currently
supported.
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
        import asyncio

        return await asyncio.to_thread(self._supports_sync, service_name)

    def _supports_sync(self, service_name: str) -> bool:
        """Sync helper for supports()."""
        if not self._spec_dir:
            return False
        for ext in (".yaml", ".yml", ".json"):
            if (self._spec_dir / f"{service_name}{ext}").exists():
                return True
        return False

    async def fetch(self, service_name: str) -> dict[str, Any] | None:
        """Parse an OpenAPI spec for a service."""
        import asyncio

        if self._spec_dir is None:
            return None

        return await asyncio.to_thread(self._fetch_sync, service_name)

    def _fetch_sync(self, service_name: str) -> dict[str, Any] | None:
        """Sync helper for fetch()."""
        for ext in (".yaml", ".yml", ".json"):
            path = self._spec_dir / f"{service_name}{ext}"
            if path.exists():
                return self._parse_spec(path)
        return None

    def _resolve_ref(self, spec: dict, ref: str) -> dict:
        """Resolve a $ref JSON Pointer within the spec."""
        if not ref.startswith("#/"):
            return {"type": "object"}  # External refs not supported
        parts = ref[2:].split("/")
        node = spec
        for part in parts:
            node = node.get(part, {})
        return node if isinstance(node, dict) else {"type": "object"}

    def _parse_spec(self, path: Path) -> dict[str, Any]:
        """Parse an OpenAPI spec file into structured dict."""
        with path.open("r") as f:
            if path.suffix == ".json":
                spec = json.load(f)
            else:
                spec = yaml.safe_load(f)

        operations = []
        paths = spec.get("paths", {})
        for path_str, path_obj in paths.items():
            # FIX-12: Extract path-level parameters and merge with method-level
            path_params = path_obj.get("parameters", [])
            for method, details in path_obj.items():
                if method in ("get", "post", "put", "patch", "delete"):
                    op_id = details.get("operationId", f"{method}_{path_str}")
                    merged_params = path_params + details.get("parameters", [])
                    params, required = self._extract_parameters(
                        spec,
                        details,
                        merged_params,
                    )
                    operations.append(
                        {
                            "name": op_id,
                            "description": details.get("summary", ""),
                            "http_method": method.upper(),
                            "http_path": path_str,
                            "parameters": params,
                            "required_params": required,
                            "response_schema": self._extract_response(spec, details),
                        }
                    )

        return {
            "source": "openapi",
            "service": path.stem,
            "title": spec.get("info", {}).get("title", ""),
            "version": spec.get("info", {}).get("version", ""),
            "operations": operations,
            "raw_content": str(path),
        }

    def _extract_parameters(
        self,
        spec: dict,
        operation: dict,
        merged_params: list[dict] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        """Extract parameter schemas and required list from an OpenAPI operation."""
        params = {}
        required: list[str] = []

        all_params = merged_params if merged_params is not None else operation.get("parameters", [])
        for p in all_params:
            # FIX-04: resolve $ref in parameters
            if "$ref" in p:
                p = self._resolve_ref(spec, p["$ref"])
            schema = p.get("schema", {"type": "string"})
            if "$ref" in schema:
                schema = self._resolve_ref(spec, schema["$ref"])
            params[p["name"]] = schema
            # FIX-05: track required parameters
            if p.get("required", False):
                required.append(p["name"])

        # Also check requestBody
        request_body = operation.get("requestBody", {})
        if "$ref" in request_body:
            request_body = self._resolve_ref(spec, request_body["$ref"])
        content = request_body.get("content", {})
        # FIX-19 (for request): try application/json first, fall back to first available
        body_schema = {}
        if "application/json" in content:
            body_schema = content["application/json"].get("schema", {})
        elif content:
            first_type = next(iter(content))
            body_schema = content[first_type].get("schema", {})

        if "$ref" in body_schema:
            body_schema = self._resolve_ref(spec, body_schema["$ref"])
        if body_schema.get("properties"):
            params.update(body_schema["properties"])
            # FIX-05: extract required from requestBody schema
            body_required = body_schema.get("required", [])
            required.extend(body_required)

        return params, required

    def _extract_response(self, spec: dict, operation: dict) -> dict[str, Any]:
        """Extract response schema from an OpenAPI operation."""
        responses = operation.get("responses", {})
        for code in ("200", "201", "204"):
            if code in responses:
                response = responses[code]
                if "$ref" in response:
                    response = self._resolve_ref(spec, response["$ref"])
                content = response.get("content", {})
                # FIX-19: try application/json first, fall back to first available content type
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                elif content:
                    first_type = next(iter(content))
                    schema = content[first_type].get("schema", {})
                else:
                    continue
                if "$ref" in schema:
                    schema = self._resolve_ref(spec, schema["$ref"])
                return schema
        return {}
