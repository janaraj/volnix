"""Pack runtime -- generic execution engine for service pack actions.

Contains ZERO pack-specific logic. Dispatches to ANY ServicePack through
the ABC contract, validates input/output against the pack's own schemas
and state machines using existing validators.

Enforcement: This is the ONLY sanctioned execution path. Calling
pack.handle_action() directly bypasses validation and fidelity tagging.
"""
from __future__ import annotations

import logging
from typing import Any

from terrarium.core.context import ResponseProposal
from terrarium.core.errors import PackNotFoundError, ValidationError
from terrarium.core.types import (
    FidelityMetadata,
    FidelitySource,
    FidelityTier,
    ToolName,
)
from terrarium.packs.base import ServicePack
from terrarium.packs.registry import PackRegistry
from terrarium.validation.schema import SchemaValidator
from terrarium.validation.state_machine import StateMachineValidator

logger = logging.getLogger(__name__)


class PackRuntime:
    """Generic runtime for executing pack actions with validation.

    Execute pipeline (pack-agnostic):
    1. Resolve pack from tool name via registry
    2. Validate input against pack.get_entity_schemas()
    3. Call pack.handle_action(action, input_data, state)
    4. Validate output: entity deltas against schemas
    5. Validate output: state transitions against state machines
    6. Tag response with FidelityMetadata
    7. Return validated ResponseProposal
    """

    def __init__(
        self,
        pack_registry: PackRegistry,
        schema_validator: SchemaValidator | None = None,
        state_machine_validator: StateMachineValidator | None = None,
    ) -> None:
        self._registry = pack_registry
        self._schema_validator = schema_validator or SchemaValidator()
        self._sm_validator = state_machine_validator or StateMachineValidator()

    async def execute(
        self,
        action: str,
        input_data: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> ResponseProposal:
        """Execute an action through its pack with full validation.

        Args:
            action: Tool name (e.g., "email_send").
            input_data: Input payload for the tool.
            state: Current entity state (dict of entity lists keyed by type).

        Returns:
            Validated ResponseProposal with FidelityMetadata.

        Raises:
            PackNotFoundError: No pack provides this tool.
            ValidationError: Input or output fails validation.
        """
        state = state or {}

        # 1. Resolve pack (generic lookup -- no pack-specific logic)
        pack = self._registry.get_pack_for_tool(action)
        entity_schemas = pack.get_entity_schemas()
        state_machines = pack.get_state_machines()

        # 2. Validate input against tool parameter schema
        tool_def = self._find_tool_def(pack, action)
        if tool_def and "parameters" in tool_def:
            input_result = self._schema_validator.validate_entity(input_data, tool_def["parameters"])
            if not input_result.valid:
                raise ValidationError(
                    message=f"Input validation failed for '{action}': {input_result.errors}",
                    validation_type="schema",
                )

        # 3. Dispatch to pack (the ABC contract -- handle_action)
        proposal = await pack.handle_action(ToolName(action), input_data, state)

        # 4. Validate output: entity deltas against schemas
        for delta in (proposal.proposed_state_deltas or []):
            schema = entity_schemas.get(delta.entity_type)
            if schema and delta.operation == "create":
                # Full validation for creates (all required fields must be present)
                entity_result = self._schema_validator.validate_entity(delta.fields, schema)
                if not entity_result.valid:
                    raise ValidationError(
                        message=f"Entity schema validation failed for {delta.entity_type}: {entity_result.errors}",
                        validation_type="schema",
                    )
            elif schema and delta.operation == "update":
                # Partial validation for updates: type-check provided fields only
                # (updates are partial — don't enforce required fields)
                props = schema.get("properties", {})
                _TYPE_MAP = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
                for field_name, value in delta.fields.items():
                    field_schema = props.get(field_name)
                    if not field_schema:
                        continue
                    if "type" in field_schema:
                        expected = _TYPE_MAP.get(field_schema["type"])
                        if expected and not isinstance(value, expected):
                            raise ValidationError(
                                message=f"Update field '{field_name}' expected {field_schema['type']}, got {type(value).__name__} for {delta.entity_type}",
                                validation_type="schema",
                            )
                    # Enum constraint validation
                    if "enum" in field_schema and value not in field_schema["enum"]:
                        raise ValidationError(
                            message=f"Update field '{field_name}' value '{value}' not in allowed values {field_schema['enum']} for {delta.entity_type}",
                            validation_type="schema",
                        )
                    # Minimum constraint validation
                    if "minimum" in field_schema and isinstance(value, (int, float)) and value < field_schema["minimum"]:
                        raise ValidationError(
                            message=f"Update field '{field_name}' value {value} below minimum {field_schema['minimum']} for {delta.entity_type}",
                            validation_type="schema",
                        )
                    # Maximum constraint validation
                    if "maximum" in field_schema and isinstance(value, (int, float)) and value > field_schema["maximum"]:
                        raise ValidationError(
                            message=f"Update field '{field_name}' value {value} above maximum {field_schema['maximum']} for {delta.entity_type}",
                            validation_type="schema",
                        )

        # 5. Validate output: state transitions
        for delta in (proposal.proposed_state_deltas or []):
            sm = state_machines.get(delta.entity_type)
            if sm and "status" in delta.fields:
                new_status = delta.fields["status"]
                old_status = (delta.previous_fields or {}).get("status")
                if old_status is not None:
                    # Update: validate transition
                    sm_result = self._sm_validator.validate_transition(old_status, new_status, sm)
                    if not sm_result.valid:
                        raise ValidationError(
                            message=f"State transition invalid for {delta.entity_type}: {sm_result.errors}",
                            validation_type="state_machine",
                        )
                else:
                    # Create: validate initial state is a known state
                    all_states = set(sm.get("transitions", {}).keys())
                    for targets in sm.get("transitions", {}).values():
                        all_states.update(targets)
                    if all_states and new_status not in all_states:
                        raise ValidationError(
                            message=f"Invalid initial state '{new_status}' for {delta.entity_type}",
                            validation_type="state_machine",
                        )

        # 6. Tag with FidelityMetadata (if not already tagged by pack)
        if proposal.fidelity is None:
            proposal = ResponseProposal(
                response_body=proposal.response_body,
                proposed_events=proposal.proposed_events,
                proposed_state_deltas=proposal.proposed_state_deltas,
                proposed_side_effects=proposal.proposed_side_effects,
                fidelity=FidelityMetadata(
                    tier=FidelityTier(pack.fidelity_tier),
                    source=pack.pack_name,
                    fidelity_source=FidelitySource.VERIFIED_PACK,
                    deterministic=True,
                    replay_stable=True,
                    benchmark_grade=True,
                ),
                fidelity_warning=proposal.fidelity_warning,
            )

        return proposal

    def has_tool(self, tool_name: str) -> bool:
        """Check if any registered pack handles this tool."""
        return self._registry.has_tool(tool_name)

    def _find_tool_def(self, pack: ServicePack, action: str) -> dict | None:
        """Find the tool definition for an action from the pack's tool list."""
        for tool in pack.get_tools():
            if tool.get("name") == action:
                return tool
        return None
