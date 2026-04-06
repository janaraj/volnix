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
import re
from typing import Any

from volnix.core.context import ActionContext, ResponseProposal
from volnix.core.types import (
    EntityId,
    FidelityMetadata,
    FidelitySource,
    FidelityTier,
    StateDelta,
)
from volnix.llm.types import LLMRequest, LLMResponse
from volnix.packs.profile_schema import (
    ProfileOperation,
    ServiceProfileData,
)
from volnix.validation.schema import SchemaValidator

logger = logging.getLogger(__name__)


class Tier2Generator:
    """Generates responses using LLM guided by curated service profiles.

    Uses a loaded ServiceProfileData to constrain LLM responses through:
    - Profile responder_prompt as system prompt
    - Behavioral notes for service-specific rules
    - Error modes for realistic failure simulation
    - Response schema for structural validation
    - Few-shot examples for grounding
    """

    def __init__(
        self,
        llm_router: Any,  # LLMRouter (avoid import cycle with typing.Protocol)
        seed: int = 42,
    ) -> None:
        self._router = llm_router
        self._seed = seed
        self._schema_validator = SchemaValidator()

    async def generate(
        self,
        ctx: ActionContext,
        profile: ServiceProfileData,
        current_state: dict[str, Any] | None = None,
    ) -> ResponseProposal:
        """Generate a profiled LLM response.

        Steps:
        1. Find the operation spec from profile matching ctx.action
        2. Build system prompt from profile.responder_prompt + behavioral_notes + error_modes
        3. Build user prompt from action details + current state + examples
        4. LLM call via router (engine_name="responder", use_case="tier2")
        5. Parse JSON response
        6. Validate against operation's response_schema
        7. Build StateDelta from response (if operation creates/mutates entity)
        8. Return ResponseProposal with FidelityMetadata(tier=2)

        Args:
            ctx: The action context with action name and input data.
            profile: The curated service profile constraining the response.
            current_state: Current world state (entity data keyed by type).

        Returns:
            A ResponseProposal with fidelity tier 2 metadata.
        """
        if current_state is None:
            current_state = {}

        # 1. Find the operation definition
        operation = self._find_operation(profile, ctx.action)
        if operation is None:
            return self._error_proposal(
                f"Operation '{ctx.action}' not found in profile '{profile.profile_name}'"
            )

        # 2. Build system prompt
        system_prompt = self._build_system_prompt(profile, operation)

        # 3. Build user prompt
        user_prompt = self._build_user_prompt(ctx, profile, operation, current_state)

        # 4. LLM call via router
        request = LLMRequest(
            system_prompt=system_prompt,
            user_content=user_prompt,
            output_schema=operation.response_schema if operation.response_schema else None,
            seed=self._seed,
            temperature=0.7,
        )
        response = await self._router.route(
            request,
            engine_name="responder",
            use_case="tier2",
        )

        # 5. Parse JSON response
        response_body = self._parse_response(response)

        # 6. Validate against operation's response_schema
        validation_warnings: list[str] = []
        if operation.response_schema:
            errors = self._validate_response(response_body, operation)
            if errors and (operation.creates_entity or operation.mutates_entity):
                # Retry once with error context for create/mutate operations
                logger.warning(
                    "Tier2 response validation failed for %s (create/mutate), retrying: %s",
                    ctx.action,
                    errors,
                )
                retry_response = await self._retry_with_errors(
                    ctx, profile, operation, current_state, errors,
                )
                if retry_response is not None:
                    response_body = retry_response
                    errors = self._validate_response(response_body, operation)

                if errors:
                    # Still failing — return error proposal, no state delta
                    logger.warning(
                        "Tier2 retry also failed validation for %s: %s",
                        ctx.action,
                        errors,
                    )
                    return ResponseProposal(
                        response_body={
                            "error": f"Validation failed: {errors[0]}",
                            "action": ctx.action,
                        },
                        fidelity=FidelityMetadata(
                            tier=FidelityTier.PROFILED,
                            source=profile.profile_name,
                            fidelity_source=self._resolve_fidelity_source(
                                profile.fidelity_source,
                            ),
                            deterministic=False,
                        ),
                    )
            elif errors:
                # Read-only: log but don't block
                logger.warning(
                    "Tier2 response validation warnings for %s (read-only): %s",
                    ctx.action,
                    errors,
                )
                validation_warnings.extend(errors)

        # 7. Build StateDelta from response
        state_deltas = self._extract_state_deltas(operation, response_body, profile)

        # 8. Return ResponseProposal with FidelityMetadata(tier=2)
        fidelity_source = self._resolve_fidelity_source(profile.fidelity_source)
        warning_parts = [f"Tier 2 profile: {profile.profile_name} (LLM-generated response)"]
        if validation_warnings:
            warning_parts.append(f"Validation warnings: {'; '.join(validation_warnings)}")

        return ResponseProposal(
            response_body=response_body,
            proposed_state_deltas=state_deltas,
            fidelity=FidelityMetadata(
                tier=FidelityTier.PROFILED,
                source=profile.profile_name,
                fidelity_source=fidelity_source,
                deterministic=False,
                replay_stable=False,
                benchmark_grade=False,
            ),
            fidelity_warning="; ".join(warning_parts),
        )

    def _find_operation(
        self, profile: ServiceProfileData, action_name: str
    ) -> ProfileOperation | None:
        """Find the operation spec from profile matching the action name."""
        for op in profile.operations:
            if op.name == action_name:
                return op
        return None

    def _build_system_prompt(self, profile: ServiceProfileData, operation: ProfileOperation) -> str:
        """Assemble system prompt from profile data.

        Includes responder_prompt, behavioral notes, error modes,
        and response format instructions.
        """
        parts: list[str] = []

        # Primary responder prompt
        if profile.responder_prompt:
            parts.append(profile.responder_prompt.strip())

        # Behavioral notes
        if profile.behavioral_notes:
            parts.append("\n## Behavioral Rules")
            for note in profile.behavioral_notes:
                parts.append(f"- {note}")

        # Error modes
        if profile.error_modes:
            parts.append("\n## Error Modes")
            for em in profile.error_modes:
                parts.append(f"- {em.code}: {em.when} (HTTP {em.http_status})")

        # Response format instructions
        parts.append("\n## Response Format")
        parts.append("Output ONLY valid JSON matching the EXACT response schema below.")
        parts.append("Do NOT include markdown formatting, explanation, or extra fields.")
        parts.append("The response MUST contain ALL required fields from the schema.")

        # Response schema reference
        if operation.response_schema:
            required = operation.response_schema.get("required", [])
            parts.append(
                f"\n## Response Schema (MUST follow exactly)\n```json\n"
                f"{json.dumps(operation.response_schema, indent=2)}\n```"
            )
            if required:
                parts.append(f"\nRequired fields that MUST appear in your response: {required}")

        return "\n".join(parts)

    def _build_user_prompt(
        self,
        ctx: ActionContext,
        profile: ServiceProfileData,
        operation: ProfileOperation,
        current_state: dict[str, Any],
    ) -> str:
        """Build user prompt with action details, state, and examples.

        Includes operation name, description, input parameters,
        current entity state, and matching few-shot examples.
        """
        parts: list[str] = []

        # Operation header
        parts.append(f"Execute operation: {operation.name}")
        parts.append(f"Description: {operation.description}")

        # Input parameters
        input_data = ctx.input_data or {}
        parts.append(f"\n## Input\n```json\n{json.dumps(input_data, indent=2)}\n```")

        # Current world state (relevant entities)
        if current_state:
            state_str = self._format_state_context(current_state)
            if state_str:
                parts.append(f"\n## Current World State\n{state_str}")

        # Few-shot examples matching this operation
        matching_examples = [ex for ex in profile.examples if ex.operation == operation.name]
        if matching_examples:
            parts.append("\n## Examples")
            for ex in matching_examples:
                parts.append(f"Request: {json.dumps(ex.request, indent=2)}")
                parts.append(f"Response: {json.dumps(ex.response, indent=2)}")

        return "\n".join(parts)

    def _format_state_context(self, current_state: dict[str, Any]) -> str:
        """Format entity state for inclusion in prompt."""
        parts: list[str] = []
        for entity_type, entities in current_state.items():
            if not entities:
                continue
            if isinstance(entities, list):
                parts.append(f"### {entity_type} ({len(entities)} total)")
                # Limit to 20 entities to avoid token overflow
                for e in entities[:20]:
                    parts.append(json.dumps(e, default=str))
                if len(entities) > 20:
                    parts.append(f"... and {len(entities) - 20} more")
            else:
                parts.append(f"### {entity_type}")
                parts.append(json.dumps(entities, default=str))
        return "\n".join(parts)

    def _validate_response(
        self, response: dict[str, Any], operation: ProfileOperation
    ) -> list[str]:
        """Validate response against the operation's response_schema.

        Returns a list of validation error messages (empty if valid).
        """
        if not operation.response_schema:
            return []

        # Check for parse errors
        if response.get("_parse_error"):
            return ["Response could not be parsed as valid JSON"]

        result = self._schema_validator.validate_response(response, operation.response_schema)
        return list(result.errors)

    async def _retry_with_errors(
        self,
        ctx: ActionContext,
        profile: ServiceProfileData,
        operation: ProfileOperation,
        current_state: dict[str, Any],
        errors: list[str],
    ) -> dict[str, Any] | None:
        """Retry LLM call with validation error context.

        Adds the validation errors to the prompt so the LLM can fix them.
        Returns the parsed response body, or None if the retry fails.
        """
        system_prompt = self._build_system_prompt(profile, operation)
        user_prompt = self._build_user_prompt(ctx, profile, operation, current_state)
        error_context = "\n".join(f"- {e}" for e in errors)
        user_prompt += (
            f"\n\n## VALIDATION ERRORS FROM PREVIOUS ATTEMPT\n"
            f"Your previous response had these errors:\n{error_context}\n\n"
            f"Please fix these errors and return a valid JSON response."
        )

        request = LLMRequest(
            system_prompt=system_prompt,
            user_content=user_prompt,
            output_schema=operation.response_schema if operation.response_schema else None,
            seed=self._seed,
            temperature=0.3,  # Lower temperature for correction
        )

        try:
            response = await self._router.route(
                request,
                engine_name="responder",
                use_case="tier2",
            )
            return self._parse_response(response)
        except Exception as exc:
            logger.warning("Tier2 retry LLM call failed: %s", exc)
            return None

    def _extract_state_deltas(
        self,
        operation: ProfileOperation,
        response_body: dict[str, Any],
        profile: ServiceProfileData,
    ) -> list[StateDelta]:
        """Extract state deltas from the LLM response.

        Inspects the operation's creates_entity / mutates_entity fields
        to determine what state changes should be proposed.
        """
        deltas: list[StateDelta] = []

        if operation.creates_entity:
            entity_type = operation.creates_entity
            identity_field = self._get_identity_field(entity_type, profile)
            entity_id_value = response_body.get(identity_field)
            if entity_id_value is None:
                logger.warning(
                    "Response missing identity field '%s' for entity '%s'",
                    identity_field,
                    entity_type,
                )
                return []  # Don't create invalid StateDelta
            deltas.append(
                StateDelta(
                    entity_type=entity_type,
                    entity_id=EntityId(str(entity_id_value)),
                    operation="create",
                    fields=response_body,
                )
            )
        elif operation.mutates_entity:
            entity_type = operation.mutates_entity
            identity_field = self._get_identity_field(entity_type, profile)
            entity_id_value = response_body.get(identity_field)
            if entity_id_value is None:
                logger.warning(
                    "Response missing identity field '%s' for entity '%s'",
                    identity_field,
                    entity_type,
                )
                return []  # Don't create invalid StateDelta
            deltas.append(
                StateDelta(
                    entity_type=entity_type,
                    entity_id=EntityId(str(entity_id_value)),
                    operation="update",
                    fields=response_body,
                )
            )

        return deltas

    def _get_identity_field(self, entity_type: str, profile: ServiceProfileData) -> str:
        """Look up the identity field for an entity type from the profile."""
        for entity_def in profile.entities:
            if entity_def.name == entity_type:
                return entity_def.identity_field
        return "id"

    def _build_proposal(
        self,
        response_body: dict[str, Any],
        operation: ProfileOperation,
        profile: ServiceProfileData,
    ) -> ResponseProposal:
        """Build a ResponseProposal from the parsed response."""
        state_deltas = self._extract_state_deltas(operation, response_body, profile)
        fidelity_source = self._resolve_fidelity_source(profile.fidelity_source)
        return ResponseProposal(
            response_body=response_body,
            proposed_state_deltas=state_deltas,
            fidelity=FidelityMetadata(
                tier=FidelityTier.PROFILED,
                source=profile.profile_name,
                fidelity_source=fidelity_source,
                deterministic=False,
                replay_stable=False,
                benchmark_grade=False,
            ),
            fidelity_warning=f"Tier 2 profile: {profile.profile_name} (LLM-generated response)",
        )

    def _parse_response(self, response: LLMResponse) -> dict[str, Any]:
        """Parse LLM response into dict.

        Tries structured_output first, then parses content as JSON,
        stripping markdown code blocks if present.
        """
        if response.structured_output:
            return response.structured_output

        content = response.content.strip()
        # Strip markdown code block wrappers
        content = re.sub(r"^```(?:json)?\s*\n?", "", content)
        content = re.sub(r"\n?\s*```\s*$", "", content)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the response
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass

        return {"raw_response": content, "_parse_error": True}

    @staticmethod
    def _resolve_fidelity_source(source_str: str) -> FidelitySource:
        """Convert a profile's fidelity_source string to the enum."""
        try:
            return FidelitySource(source_str)
        except ValueError:
            return FidelitySource.CURATED_PROFILE

    @staticmethod
    def _error_proposal(message: str) -> ResponseProposal:
        """Create an error ResponseProposal."""
        return ResponseProposal(
            response_body={"error": message},
            fidelity=FidelityMetadata(
                tier=FidelityTier.PROFILED,
                source="tier2_error",
                deterministic=False,
            ),
        )
