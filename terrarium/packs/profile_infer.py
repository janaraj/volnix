"""Profile inference pipeline -- generates draft Tier 2 profiles for unknown services.

When the compiler encounters a service with no Tier 1 pack or curated Tier 2 profile,
the ProfileInferrer gathers available information (Context Hub docs, OpenAPI specs,
kernel classification) and asks an LLM to generate a draft ServiceProfileData.

The resulting profile is labeled ``fidelity_source: "bootstrapped"`` and runs at
Tier 2 with lower confidence than curated profiles.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

from terrarium.packs.profile_schema import (
    ProfileEntity,
    ProfileErrorMode,
    ProfileExample,
    ProfileOperation,
    ProfileStateMachine,
    ServiceProfileData,
)

logger = logging.getLogger(__name__)

# Confidence scores based on available sources
_CONFIDENCE_HUB = 0.7
_CONFIDENCE_OPENAPI = 0.6
_CONFIDENCE_KERNEL = 0.4
_CONFIDENCE_LLM_ONLY = 0.3


class ProfileInferrer:
    """Generates draft Tier 2 profiles for unknown services via LLM.

    Uses all available sources (Context Hub, OpenAPI specs, kernel classification)
    to gather information, then asks the LLM to generate a structured profile.
    """

    def __init__(
        self,
        llm_router: Any,
        context_hub: Any | None = None,
        openapi_provider: Any | None = None,
        kernel: Any | None = None,
    ) -> None:
        self._router = llm_router
        self._context_hub = context_hub
        self._openapi_provider = openapi_provider
        self._kernel = kernel

    async def infer(self, service_name: str) -> ServiceProfileData:
        """Infer a draft profile for the given service.

        Steps:
        1. Gather all available sources (Context Hub, OpenAPI, Kernel)
        2. Build LLM prompt with gathered information
        3. LLM generates YAML -> parse -> validate -> ServiceProfileData
        4. Set confidence based on sources
        5. Return ServiceProfileData with fidelity_source="bootstrapped"

        Args:
            service_name: The name of the service to infer a profile for.

        Returns:
            A ServiceProfileData with fidelity_source="bootstrapped".
        """
        # 1. Gather sources
        sources = await self._gather_sources(service_name)

        # 2-3. Generate profile via LLM
        profile = await self._generate_via_llm(service_name, sources)

        # 4. Minimum viability check
        if not profile.operations:
            logger.warning("Inferred profile for '%s' has zero operations — invalid", service_name)
            raise ValueError(f"Inferred profile for '{service_name}' has no operations")
        if not profile.entities:
            logger.warning("Inferred profile for '%s' has zero entities — invalid", service_name)
            raise ValueError(f"Inferred profile for '{service_name}' has no entities")
        if not profile.responder_prompt:
            logger.warning(
                "Inferred profile for '%s' has empty responder_prompt",
                service_name,
            )
            raise ValueError(
                f"Inferred profile for '{service_name}' has empty responder_prompt"
            )

        return profile

    async def _gather_sources(self, service_name: str) -> dict[str, Any]:
        """Collect all available information about the service.

        Tries Context Hub, OpenAPI provider, and kernel classification
        in order, collecting whatever is available.
        """
        sources: dict[str, Any] = {"service_name": service_name}

        # Context Hub
        if self._context_hub is not None:
            try:
                supports = await self._context_hub.supports(service_name)
                if supports:
                    hub_data = await self._context_hub.fetch(service_name)
                    if hub_data is not None:
                        sources["context_hub"] = hub_data.get("raw_content", "")
                        logger.info(
                            "ProfileInferrer: gathered Context Hub docs for '%s'",
                            service_name,
                        )
            except Exception as exc:
                logger.debug(
                    "ProfileInferrer: Context Hub failed for '%s': %s",
                    service_name,
                    exc,
                )

        # OpenAPI
        if self._openapi_provider is not None:
            try:
                supports = await self._openapi_provider.supports(service_name)
                if supports:
                    spec_data = await self._openapi_provider.fetch(service_name)
                    if spec_data is not None:
                        sources["openapi"] = spec_data
                        logger.info(
                            "ProfileInferrer: gathered OpenAPI spec for '%s'",
                            service_name,
                        )
            except Exception as exc:
                logger.debug(
                    "ProfileInferrer: OpenAPI failed for '%s': %s",
                    service_name,
                    exc,
                )

        # Kernel classification
        if self._kernel is not None:
            try:
                category = self._kernel.get_category(service_name)
                if category:
                    sources["category"] = str(category)
                    primitives = self._kernel.get_primitives(str(category))
                    sources["primitives"] = primitives
                    logger.info(
                        "ProfileInferrer: classified '%s' as category '%s'",
                        service_name,
                        category,
                    )
            except Exception as exc:
                logger.debug(
                    "ProfileInferrer: Kernel classification failed for '%s': %s",
                    service_name,
                    exc,
                )

        return sources

    async def _generate_via_llm(
        self, service_name: str, sources: dict[str, Any]
    ) -> ServiceProfileData:
        """Ask LLM to generate a structured service profile.

        Builds a prompt from the gathered sources and sends it to the
        LLM router. Parses the YAML response into ServiceProfileData.
        """
        from terrarium.llm.types import LLMRequest

        # Build available docs section
        available_docs = self._format_available_docs(sources)
        category = sources.get("category", "unknown")

        system_prompt = _INFER_SYSTEM_PROMPT
        user_prompt = _INFER_USER_TEMPLATE.format(
            service_name=service_name,
            category=category,
            available_docs=available_docs,
        )

        request = LLMRequest(
            system_prompt=system_prompt,
            user_content=user_prompt,
            temperature=0.7,
        )

        response = await self._router.route(
            request,
            engine_name="profile_infer",
            use_case="default",
        )

        # Parse YAML response
        profile_data = self._parse_yaml_response(response.content, service_name)

        # Reject profiles with no operations
        if not profile_data.get("operations"):
            raise ValueError(f"Could not generate valid profile for '{service_name}'")

        # Set confidence based on sources
        confidence = self._compute_confidence(sources)

        # Build the final ServiceProfileData
        return self._build_profile(service_name, profile_data, sources, confidence)

    def _format_available_docs(self, sources: dict[str, Any]) -> str:
        """Format available docs for the LLM prompt."""
        parts: list[str] = []

        if "context_hub" in sources:
            content = sources["context_hub"]
            # Truncate to avoid token overflow
            if len(content) > 4000:
                content = content[:4000] + "\n... (truncated)"
            parts.append(f"## Context Hub API Documentation\n{content}")

        if "openapi" in sources:
            spec = sources["openapi"]
            if isinstance(spec, dict):
                ops = spec.get("operations", [])
                if ops:
                    parts.append("## OpenAPI Operations")
                    for op in ops[:20]:  # Limit
                        parts.append(
                            f"- {op.get('name', '?')}: {op.get('http_method', '?')} "
                            f"{op.get('http_path', '?')} - {op.get('description', '')}"
                        )

        if "primitives" in sources:
            primitives = sources["primitives"]
            if primitives:
                parts.append("## Semantic Primitives (from kernel)")
                for p in primitives:
                    if isinstance(p, dict):
                        parts.append(f"- {p.get('name', '?')}: {p.get('description', '')}")

        if not parts:
            parts.append(
                "No external documentation available. "
                "Use your knowledge of this service's public API."
            )

        return "\n\n".join(parts)

    def _parse_yaml_response(self, content: str, service_name: str) -> dict[str, Any]:
        """Parse YAML from LLM response, stripping markdown wrappers."""
        content = content.strip()

        # Strip markdown code block wrappers
        content = re.sub(r"^```(?:ya?ml)?\s*\n?", "", content)
        content = re.sub(r"\n?\s*```\s*$", "", content)
        content = content.strip()

        try:
            parsed = yaml.safe_load(content)
            if isinstance(parsed, dict):
                return parsed
        except yaml.YAMLError:
            pass

        # Try to find YAML block in content
        # Look for the first line that starts with a key
        lines = content.split("\n")
        yaml_lines: list[str] = []
        collecting = False
        for line in lines:
            if not collecting and re.match(r"^[a-z_]+:", line):
                collecting = True
            if collecting:
                yaml_lines.append(line)

        if yaml_lines:
            try:
                parsed = yaml.safe_load("\n".join(yaml_lines))
                if isinstance(parsed, dict):
                    return parsed
            except yaml.YAMLError:
                pass

        # Fallback: raise error instead of returning empty profile
        raise ValueError(
            f"Could not parse valid YAML profile from LLM response for '{service_name}'"
        )

    def _compute_confidence(self, sources: dict[str, Any]) -> float:
        """Compute confidence score based on available sources."""
        if "context_hub" in sources:
            return _CONFIDENCE_HUB
        if "openapi" in sources:
            return _CONFIDENCE_OPENAPI
        if "category" in sources:
            return _CONFIDENCE_KERNEL
        return _CONFIDENCE_LLM_ONLY

    def _build_profile(
        self,
        service_name: str,
        profile_data: dict[str, Any],
        sources: dict[str, Any],
        confidence: float,
    ) -> ServiceProfileData:
        """Build a ServiceProfileData from parsed profile data.

        Handles both well-structured LLM output and partial/malformed data
        by falling back to defaults for missing fields.
        """
        # Parse operations
        operations: list[ProfileOperation] = []
        for op_data in profile_data.get("operations", []):
            if isinstance(op_data, dict):
                try:
                    operations.append(
                        ProfileOperation(
                            name=op_data.get("name", f"{service_name}_unknown"),
                            service=op_data.get("service", service_name),
                            description=op_data.get("description", ""),
                            http_method=op_data.get("http_method", "POST"),
                            http_path=op_data.get("http_path", ""),
                            parameters=op_data.get("parameters", {}),
                            required_params=op_data.get("required_params", []),
                            response_schema=op_data.get("response_schema", {}),
                            is_read_only=op_data.get("is_read_only", False),
                            creates_entity=op_data.get("creates_entity"),
                            mutates_entity=op_data.get("mutates_entity"),
                        )
                    )
                except Exception as exc:
                    logger.debug("ProfileInferrer: skipping malformed operation: %s", exc)

        # Parse entities
        entities: list[ProfileEntity] = []
        for ent_data in profile_data.get("entities", []):
            if isinstance(ent_data, dict):
                try:
                    entities.append(
                        ProfileEntity(
                            name=ent_data.get("name", "unknown"),
                            identity_field=ent_data.get("identity_field", "id"),
                            fields=ent_data.get("fields", {}),
                            required=ent_data.get("required", []),
                        )
                    )
                except Exception as exc:
                    logger.debug("ProfileInferrer: skipping malformed entity: %s", exc)

        # Parse state machines
        state_machines: list[ProfileStateMachine] = []
        for sm_data in profile_data.get("state_machines", []):
            if isinstance(sm_data, dict):
                try:
                    state_machines.append(
                        ProfileStateMachine(
                            entity_type=sm_data.get("entity_type", "unknown"),
                            field=sm_data.get("field", "status"),
                            transitions=sm_data.get("transitions", {}),
                        )
                    )
                except Exception as exc:
                    logger.debug("ProfileInferrer: skipping malformed state machine: %s", exc)

        # Parse error modes
        error_modes: list[ProfileErrorMode] = []
        for em_data in profile_data.get("error_modes", []):
            if isinstance(em_data, dict):
                try:
                    error_modes.append(
                        ProfileErrorMode(
                            code=em_data.get("code", "UNKNOWN"),
                            when=em_data.get("when", ""),
                            http_status=em_data.get("http_status", 400),
                            response_body=em_data.get("response_body", {}),
                        )
                    )
                except Exception as exc:
                    logger.debug("ProfileInferrer: skipping malformed error mode: %s", exc)

        # Parse behavioral notes
        behavioral_notes = profile_data.get("behavioral_notes", [])
        if not isinstance(behavioral_notes, list):
            behavioral_notes = []

        # Parse examples
        examples: list[ProfileExample] = []
        for ex_data in profile_data.get("examples", []):
            if isinstance(ex_data, dict):
                try:
                    examples.append(
                        ProfileExample(
                            operation=ex_data.get("operation", ""),
                            request=ex_data.get("request", {}),
                            response=ex_data.get("response", {}),
                        )
                    )
                except Exception as exc:
                    logger.debug("ProfileInferrer: skipping malformed example: %s", exc)

        # Build source chain
        source_chain: list[str] = ["llm_inference"]
        if "context_hub" in sources:
            source_chain.insert(0, "context_hub")
        if "openapi" in sources:
            source_chain.insert(0, "openapi")
        if "category" in sources:
            source_chain.insert(0, f"kernel:{sources['category']}")

        category = profile_data.get("category", sources.get("category", "unknown"))

        return ServiceProfileData(
            profile_name=profile_data.get("profile_name", service_name),
            service_name=profile_data.get("service_name", service_name),
            category=category,
            version=profile_data.get("version", "0.1.0"),
            fidelity_source="bootstrapped",
            operations=operations,
            entities=entities,
            state_machines=state_machines,
            error_modes=error_modes,
            behavioral_notes=behavioral_notes,
            examples=examples,
            responder_prompt=profile_data.get(
                "responder_prompt",
                f"You are simulating the {service_name} API.",
            ),
            confidence=confidence,
            source_chain=source_chain,
            auth_pattern=profile_data.get("auth_pattern", ""),
            base_url=profile_data.get("base_url", ""),
        )


# ---------------------------------------------------------------------------
# Prompt templates (inline, used only by ProfileInferrer)
# ---------------------------------------------------------------------------

_INFER_SYSTEM_PROMPT = """\
You are Terrarium's service profiler. Generate a structured service profile
for the given service. This profile will be used to simulate the service's API.

Output ONLY valid YAML matching this structure:
profile_name: <service>
service_name: <service>
category: <category>
operations:
  - name: <service>_<action>
    service: <service>
    http_method: <GET|POST|PUT|DELETE>
    http_path: <real API path>
    description: <what it does>
    parameters:
      param_name: {type: string}
    required_params: [param1, param2]
    response_schema:
      type: object
      properties:
        field_name: {type: string}
    is_read_only: false
    creates_entity: <entity_type or null>
    mutates_entity: <entity_type or null>
entities:
  - name: <entity>
    identity_field: id
    fields:
      field_name: {type: string}
    required: [field1, field2]
state_machines:
  - entity_type: <entity>
    field: status
    transitions:
      state1: [state2, state3]
error_modes:
  - code: <ERROR_CODE>
    when: <condition>
    http_status: <400|403|404|409>
behavioral_notes:
  - <note1>
  - <note2>
responder_prompt: |
  You are simulating the <service> API. <instructions>

Output ONLY valid YAML. No markdown, no explanation."""

_INFER_USER_TEMPLATE = """\
Generate a service profile for: {service_name}

Category: {category}

{available_docs}

Include realistic operations, entities, state machines, error modes, and a responder prompt.
Base the operations on the real API if you know it."""
