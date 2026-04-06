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

from volnix.core.context import ResponseProposal
from volnix.core.errors import PackNotFoundError, ValidationError
from volnix.core.types import (
    FidelityMetadata,
    FidelitySource,
    FidelityTier,
    ToolName,
)
from volnix.packs.base import ServicePack
from volnix.packs.registry import PackRegistry
from volnix.validation.schema import SchemaValidator
from volnix.validation.state_machine import StateMachineValidator

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
        # Injected by app.py for dynamic mode query-driven generation
        self._behavior: str = "static"
        self._llm_router: Any = None
        self._state_engine: Any = None

    async def execute(
        self,
        action: str,
        input_data: dict[str, Any],
        state: dict[str, Any] | None = None,
        service_id: str | None = None,
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

        # 1. Resolve pack — prefer service_id (handles tool name collisions
        # like "search" in both notion and reddit), fall back to tool name.
        if service_id and self._registry.has_pack(service_id):
            pack = self._registry.get_pack(service_id)
        else:
            pack = self._registry.get_pack_for_tool(action)
        entity_schemas = pack.get_entity_schemas()
        state_machines = pack.get_state_machines()

        # 2. Sanitize input: strip null values from optional params.
        # External agents (CrewAI, LangGraph) serialize unset optional params
        # as null in JSON. Strip before validation so schema validator doesn't
        # reject null values for typed fields.
        input_data = {k: v for k, v in input_data.items() if v is not None}

        # 3. Validate input against tool parameter schema
        tool_def = self._find_tool_def(pack, action)
        if tool_def and "parameters" in tool_def:
            input_result = self._schema_validator.validate_entity(input_data, tool_def["parameters"])
            if not input_result.valid:
                raise ValidationError(
                    message=f"Input validation failed for '{action}': {input_result.errors}",
                    validation_type="schema",
                )

        # 4. Dispatch to pack (the ABC contract -- handle_action)
        proposal = await pack.handle_action(ToolName(action), input_data, state)

        # 4b. Dynamic enrichment: generate relevant entities when results are sparse.
        # Only in dynamic behavior mode for read (GET) actions.
        if self._behavior == "dynamic" and self._llm_router and self._state_engine:
            if tool_def and tool_def.get("http_method", "GET").upper() == "GET":
                proposal = await self._dynamic_enrich(
                    pack, action, input_data, state, proposal,
                )

        # 5. Validate output: entity deltas against schemas
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
                        field_type = field_schema["type"]
                        # Handle nullable types: ["string", "null"] etc.
                        if isinstance(field_type, list):
                            if "null" in field_type and value is None:
                                continue
                            non_null = [t for t in field_type if t != "null"]
                            expected = tuple(
                                _TYPE_MAP[t] for t in non_null
                                if t in _TYPE_MAP
                            ) or None
                        else:
                            expected = _TYPE_MAP.get(field_type)
                        if expected and not isinstance(value, expected):
                            raise ValidationError(
                                message=f"Update field '{field_name}' expected {field_type}, got {type(value).__name__} for {delta.entity_type}",
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

    async def _dynamic_enrich(
        self,
        pack: ServicePack,
        action: str,
        input_data: dict[str, Any],
        state: dict[str, Any],
        proposal: ResponseProposal,
    ) -> ResponseProposal:
        """Generate relevant entities when Tier 1 returns sparse results.

        Fires in dynamic behavior mode for read/GET actions. Generates
        entities matching the query context via the same LLM infrastructure
        used during world compilation, inserts into state, re-runs the
        pack handler with enriched state.
        """
        import json
        from volnix.engines.world_compiler.data_generator import WorldDataGenerator
        from volnix.engines.world_compiler.prompt_templates import ENTITY_GENERATION

        # Check if response has a sparse results list
        body = proposal.response_body
        results_key = None
        for key in ("results", "items", "tweets", "posts", "messages",
                     "entities", "data", "news", "bars", "orders", "tickets"):
            if key in body and isinstance(body[key], list):
                results_key = key
                break
        if results_key is None:
            return proposal

        if len(body[results_key]) >= 5:
            return proposal  # Already has enough results

        # Determine target entity type by field overlap with pack schemas
        entity_schemas = pack.get_entity_schemas()
        target_type = self._match_entity_type(body[results_key], entity_schemas)
        if not target_type:
            return proposal

        schema = entity_schemas[target_type]

        # Extract query context from input_data
        query = (
            input_data.get("query")
            or input_data.get("q")
            or input_data.get("search")
            or input_data.get("subreddit")
            or input_data.get("symbol")
            or input_data.get("keywords")
            or str(input_data)
        )

        # Build ref context from existing state (reuse data_generator logic)
        data_gen = WorldDataGenerator(llm_router=self._llm_router)
        # Map state keys back to entity type names for ref context
        entity_state: dict[str, list[dict]] = {}
        for etype in entity_schemas:
            for state_key, entities in state.items():
                if isinstance(entities, list) and (
                    state_key == etype
                    or state_key.startswith(etype)
                    or state_key.rstrip("s").rstrip("e") == etype.rstrip("s").rstrip("e")
                ):
                    entity_state[etype] = entities
                    break
        ref_context = data_gen._build_ref_context(schema, entity_state)

        # Generate entities via LLM (same template as world compilation)
        try:
            response = await ENTITY_GENERATION.execute(
                self._llm_router,
                entity_type=target_type,
                count="3",
                entity_schema=json.dumps(schema, indent=2),
                domain_description=f"Generate entities relevant to the search: {query}",
                mission="",
                reality_summary="",
                behavior_mode="dynamic",
                actor_summary="",
                policies_summary="",
                seed_scenarios=f"All entities MUST be relevant to: {query}",
                existing_refs=json.dumps(ref_context, indent=2) if ref_context else "none",
            )
            parsed = ENTITY_GENERATION.parse_json_response(response)
            entities = data_gen.parse_generated_entities(target_type, parsed, 3)
        except Exception as exc:
            logger.warning("Dynamic generation failed for %s: %s", action, exc)
            return proposal

        if not entities:
            return proposal

        # Insert into state DB
        try:
            await self._state_engine.populate_entities({target_type: entities})
            logger.info(
                "Dynamic enrichment: +%d %s for '%s'",
                len(entities), target_type, str(query)[:50],
            )
        except Exception as exc:
            logger.warning("Dynamic insert failed: %s", exc)
            return proposal

        # Re-run pack handler with enriched state
        try:
            for etype in entity_schemas:
                plural = etype + "s" if not etype.endswith("s") else etype + "es"
                try:
                    state[plural] = await self._state_engine.query_entities(etype)
                except Exception:
                    pass
            return await pack.handle_action(ToolName(action), input_data, state)
        except Exception:
            return proposal

    @staticmethod
    def _match_entity_type(
        results: list[dict],
        entity_schemas: dict[str, dict],
    ) -> str | None:
        """Match result items to an entity type by field overlap with schemas.

        Generic across all packs — no hardcoded mappings.
        """
        if not results:
            return max(
                entity_schemas,
                key=lambda t: len(entity_schemas[t].get("properties", {})),
                default=None,
            )

        result_fields: set[str] = set()
        for r in results[:3]:
            result_fields.update(r.keys())

        best_type = None
        best_overlap = 0
        for etype, schema in entity_schemas.items():
            schema_fields = set(schema.get("properties", {}).keys())
            overlap = len(result_fields & schema_fields)
            if overlap > best_overlap:
                best_overlap = overlap
                best_type = etype
        return best_type
