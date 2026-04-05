"""Compiler-time validation for generated world sections and final world state."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from volnix.actors.definition import ActorDefinition
from volnix.core.errors import EntityNotFoundError
from volnix.core.protocols import StateEngineProtocol
from volnix.core.types import EntityId
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.seeds import EntitySelector, SeedInvariant
from volnix.validation.consistency import ConsistencyValidator
from volnix.validation.schema import SchemaValidator
from volnix.validation.schema_contracts import (
    NormalizedEntitySchema,
    normalize_entity_schemas,
)
from volnix.validation.state_machine import StateMachineValidator
from volnix.validation.temporal import TemporalValidator


class SectionValidationResult(BaseModel, frozen=True):
    """Validation result for one logical compiler section."""

    section: str
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorldValidationResult(BaseModel, frozen=True):
    """Aggregated validation result for the generated world."""

    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sections: dict[str, SectionValidationResult] = Field(default_factory=dict)


class _GeneratedEntityState(StateEngineProtocol):
    """Minimal in-memory StateEngineProtocol over generated entities."""

    def __init__(
        self,
        all_entities: dict[str, list[dict[str, Any]]],
        schemas: dict[str, NormalizedEntitySchema],
    ) -> None:
        self._all_entities = all_entities
        self._schemas = schemas
        self._index: dict[str, dict[str, dict[str, Any]]] = {}

        for entity_type, entities in all_entities.items():
            schema = schemas.get(entity_type)
            identity_field = schema.identity_field if schema else None
            if not identity_field:
                continue
            self._index[entity_type] = {
                str(entity[identity_field]): entity
                for entity in entities
                if identity_field in entity and entity[identity_field] not in (None, "")
            }

    async def get_entity(
        self,
        entity_type: str,
        entity_id: EntityId,
    ) -> dict[str, Any]:
        entity = self._index.get(entity_type, {}).get(str(entity_id))
        if entity is None:
            raise EntityNotFoundError(f"{entity_type}/{entity_id}")
        return entity

    async def query_entities(self, entity_type, filters=None):
        return list(self._all_entities.get(entity_type, []))

    async def propose_mutation(self, delta):
        return delta

    async def commit_event(self, event):
        return event

    async def snapshot(self):
        return None

    async def fork(self, snapshot_id):
        return self

    async def diff(self, a, b):
        return []

    async def get_causal_chain(self, event_id):
        return []

    async def get_timeline(self, entity_id, start=None, end=None):
        return []


class CompilerWorldValidator:
    """Strict, metadata-driven compiler validator."""

    def __init__(
        self,
        *,
        collect_all_validation_errors: bool = True,
    ) -> None:
        self._collect_all = collect_all_validation_errors
        self._schema_validator = SchemaValidator()
        self._state_machine_validator = StateMachineValidator()
        self._consistency_validator = ConsistencyValidator()
        self._temporal_validator = TemporalValidator()

    def normalize_plan_schemas(
        self,
        plan: WorldPlan,
    ) -> dict[str, NormalizedEntitySchema]:
        """Normalize all entity schemas declared on the resolved service surfaces."""
        normalized: dict[str, NormalizedEntitySchema] = {}
        for resolution in plan.services.values():
            normalized.update(normalize_entity_schemas(resolution.surface.entity_schemas))
        return normalized

    def collect_state_machines(
        self,
        plan: WorldPlan,
    ) -> dict[str, dict[str, Any]]:
        """Collect state machines by entity type across all services."""
        state_machines: dict[str, dict[str, Any]] = {}
        for resolution in plan.services.values():
            state_machines.update(resolution.surface.state_machines)
        return state_machines

    def validate_entity_section(
        self,
        section: str,
        entities: list[dict[str, Any]],
        schema: NormalizedEntitySchema,
        *,
        state_machine: dict[str, Any] | None = None,
        expected_count: int | None = None,
    ) -> SectionValidationResult:
        """Validate one generated entity section locally."""
        errors: list[str] = []
        warnings: list[str] = []

        if expected_count is not None and len(entities) != expected_count:
            errors.append(
                f"Expected {expected_count} entities, got {len(entities)}"
            )
            if not self._collect_all:
                return SectionValidationResult(
                    section=section,
                    valid=False,
                    errors=errors,
                    warnings=warnings,
                )

        for index, entity in enumerate(entities):
            prefix = f"[{index}]"
            schema_result = self._schema_validator.validate_entity(
                entity,
                schema.json_schema,
            )
            errors.extend(f"{prefix} {error}" for error in schema_result.errors)
            warnings.extend(f"{prefix} {warning}" for warning in schema_result.warnings)

            temporal_result = self._temporal_validator.validate_entity_orderings(
                section,
                entity,
                schema.temporal_orderings,
            )
            errors.extend(f"{prefix} {error}" for error in temporal_result.errors)

            if state_machine is not None:
                errors.extend(
                    self._validate_state_machine_membership(
                        entity,
                        state_machine,
                        prefix,
                    )
                )

            if errors and not self._collect_all:
                break

        return SectionValidationResult(
            section=section,
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_actor_role(
        self,
        role: str,
        actors: list[ActorDefinition],
        *,
        expected_count: int,
    ) -> SectionValidationResult:
        """Validate one role batch produced by the actor generator."""
        errors: list[str] = []
        if len(actors) != expected_count:
            errors.append(f"Expected {expected_count} actors, got {len(actors)}")

        for index, actor in enumerate(actors):
            if actor.personality is None:
                errors.append(f"[{index}] missing personality")
                if not self._collect_all:
                    break
                continue
            if not actor.personality.style:
                errors.append(f"[{index}] missing personality.style")
            if not actor.personality.response_time:
                errors.append(f"[{index}] missing personality.response_time")
            if errors and not self._collect_all:
                break

        return SectionValidationResult(
            section=f"actor_role:{role}",
            valid=len(errors) == 0,
            errors=errors,
        )

    async def validate_world(
        self,
        plan: WorldPlan,
        all_entities: dict[str, list[dict[str, Any]]],
        *,
        actors: list[ActorDefinition] | None = None,
        seed_invariants: dict[str, list[SeedInvariant]] | None = None,
    ) -> WorldValidationResult:
        """Validate full-world contracts after generation or seed application."""
        schemas = self.normalize_plan_schemas(plan)
        state_machines = self.collect_state_machines(plan)
        state = _GeneratedEntityState(all_entities, schemas)
        sections: dict[str, SectionValidationResult] = {}

        for entity_type, entities in all_entities.items():
            schema = schemas.get(entity_type)
            if schema is None:
                continue

            errors: list[str] = []
            warnings: list[str] = []
            for index, entity in enumerate(entities):
                prefix = f"[{index}]"

                consistency = await self._consistency_validator.validate_entity_references(
                    entity_type,
                    entity,
                    schema,
                    state,
                )
                errors.extend(f"{prefix} {error}" for error in consistency.errors)

                temporal = self._temporal_validator.validate_entity_orderings(
                    entity_type,
                    entity,
                    schema.temporal_orderings,
                )
                errors.extend(f"{prefix} {error}" for error in temporal.errors)

                state_machine = state_machines.get(entity_type)
                if state_machine is not None:
                    errors.extend(
                        self._validate_state_machine_membership(
                            entity,
                            state_machine,
                            prefix,
                        )
                    )

                if errors and not self._collect_all:
                    break

            if errors or warnings:
                sections[entity_type] = SectionValidationResult(
                    section=entity_type,
                    valid=len(errors) == 0,
                    errors=errors,
                    warnings=warnings,
                )
                if errors and not self._collect_all:
                    return self._aggregate(sections)

        if actors is not None:
            expected_counts = defaultdict(int)
            for spec in plan.actor_specs:
                expected_counts[str(spec.get("role", ""))] += int(spec.get("count", 1))
            for role, expected_count in expected_counts.items():
                role_actors = [actor for actor in actors if actor.role == role]
                result = self.validate_actor_role(
                    role,
                    role_actors,
                    expected_count=expected_count,
                )
                if not result.valid or result.warnings:
                    sections[result.section] = result
                    if not result.valid and not self._collect_all:
                        return self._aggregate(sections)

        for section, invariants in (seed_invariants or {}).items():
            result = self.validate_seed_invariants(
                section,
                invariants,
                all_entities,
                schemas,
            )
            if not result.valid or result.warnings:
                sections[section] = result
                if not result.valid and not self._collect_all:
                    return self._aggregate(sections)

        return self._aggregate(sections)

    def validate_seed_invariants(
        self,
        section: str,
        invariants: list[SeedInvariant],
        all_entities: dict[str, list[dict[str, Any]]],
        schemas: dict[str, NormalizedEntitySchema],
    ) -> SectionValidationResult:
        """Validate deterministic seed invariants against concrete world data."""
        errors: list[str] = []

        if not invariants:
            errors.append("Seed expansion did not declare invariants")
            return SectionValidationResult(
                section=section,
                valid=False,
                errors=errors,
            )

        # Normalize LLM-generated invariant kinds to canonical names
        _KIND_ALIASES = {
            "equals": "exists",
            "exist": "exists",
            "has": "exists",
            "field_equal": "field_equals",
            "field_eq": "field_equals",
            "ref": "references",
            "reference": "references",
        }

        for index, invariant in enumerate(invariants):
            prefix = f"[{index}]"
            # Normalize kind aliases from LLM output
            kind = _KIND_ALIASES.get(invariant.kind, invariant.kind)
            matches = self._select_entities(invariant.selector, all_entities)

            if kind == "exists":
                if not matches:
                    errors.append(f"{prefix} selector did not match any entities")
            elif kind == "count":
                errors.extend(
                    self._validate_count_invariant(prefix, invariant, matches)
                )
            elif kind == "field_equals":
                errors.extend(
                    self._validate_field_equals_invariant(prefix, invariant, matches)
                )
            elif kind == "temporal":
                errors.extend(
                    self._validate_temporal_invariant(prefix, invariant, matches)
                )
            elif kind == "references":
                errors.extend(
                    self._validate_reference_invariant(
                        prefix,
                        invariant,
                        matches,
                        all_entities,
                        schemas,
                    )
                )
            else:
                errors.append(f"{prefix} unsupported invariant kind '{kind}'")

            if errors and not self._collect_all:
                break

        # Check for vacuous invariant set — warn if all invariants are trivially satisfiable
        warnings: list[str] = []
        if not errors:
            vacuous_count = 0
            for invariant in invariants:
                is_vacuous_count = (
                    invariant.kind == "count"
                    and invariant.operator == "gte"
                    and invariant.value == 0
                )
                if is_vacuous_count:
                    vacuous_count += 1
                elif invariant.kind == "exists" and not invariant.selector.match:
                    vacuous_count += 1
            if vacuous_count == len(invariants):
                warnings.append(
                    "All seed invariants are trivially satisfiable — "
                    "seed scenario may not be meaningfully validated"
                )

        return SectionValidationResult(
            section=section,
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _aggregate(
        self,
        sections: dict[str, SectionValidationResult],
    ) -> WorldValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        for section_name, result in sections.items():
            errors.extend(f"{section_name}: {error}" for error in result.errors)
            warnings.extend(
                f"{section_name}: {warning}" for warning in result.warnings
            )
        return WorldValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sections=sections,
        )

    def _validate_state_machine_membership(
        self,
        entity: dict[str, Any],
        state_machine: dict[str, Any],
        prefix: str,
    ) -> list[str]:
        status = entity.get("status")
        if status is None:
            return []

        transitions = state_machine.get("transitions", {})
        all_states: set[str] = set(transitions.keys())
        for targets in transitions.values():
            if isinstance(targets, list):
                all_states.update(targets)

        if all_states and status not in all_states:
            return [f"{prefix} invalid status '{status}'"]
        return []

    def _select_entities(
        self,
        selector: EntitySelector,
        all_entities: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        entities = all_entities.get(selector.entity_type, [])
        matched: list[dict[str, Any]] = []
        for entity in entities:
            if all(entity.get(field) == value for field, value in selector.match.items()):
                matched.append(entity)
        return matched

    def _validate_count_invariant(
        self,
        prefix: str,
        invariant: SeedInvariant,
        matches: list[dict[str, Any]],
    ) -> list[str]:
        if invariant.operator not in {"eq", "gte", "lte"}:
            return [f"{prefix} invalid count operator '{invariant.operator}'"]
        if not isinstance(invariant.value, int):
            return [f"{prefix} count invariant requires integer value"]

        actual = len(matches)
        expected = invariant.value
        if invariant.operator == "eq" and actual != expected:
            return [f"{prefix} expected count == {expected}, got {actual}"]
        if invariant.operator == "gte" and actual < expected:
            return [f"{prefix} expected count >= {expected}, got {actual}"]
        if invariant.operator == "lte" and actual > expected:
            return [f"{prefix} expected count <= {expected}, got {actual}"]
        return []

    def _validate_temporal_invariant(
        self,
        prefix: str,
        invariant: SeedInvariant,
        matches: list[dict[str, Any]],
    ) -> list[str]:
        """Validate that before_field < after_field for matched entities."""
        if not invariant.before_field or not invariant.after_field:
            return [f"{prefix} temporal invariant requires before_field and after_field"]
        errors: list[str] = []
        for entity in matches:
            before = entity.get(invariant.before_field)
            after = entity.get(invariant.after_field)
            if before is None or after is None:
                continue  # Field not present — skip
            if str(before) >= str(after):
                errors.append(
                    f"{prefix} temporal violation: {invariant.before_field}={before} "
                    f"is not before {invariant.after_field}={after}"
                )
        return errors

    def _validate_field_equals_invariant(
        self,
        prefix: str,
        invariant: SeedInvariant,
        matches: list[dict[str, Any]],
    ) -> list[str]:
        if invariant.field is None:
            return [f"{prefix} field_equals invariant requires field"]
        if not any(entity.get(invariant.field) == invariant.value for entity in matches):
            return [
                f"{prefix} no selected entity has {invariant.field} == {invariant.value!r}"
            ]
        return []

    def _validate_reference_invariant(
        self,
        prefix: str,
        invariant: SeedInvariant,
        matches: list[dict[str, Any]],
        all_entities: dict[str, list[dict[str, Any]]],
        schemas: dict[str, NormalizedEntitySchema],
    ) -> list[str]:
        if invariant.field is None or invariant.target_selector is None:
            return [f"{prefix} references invariant requires field and target_selector"]

        target_matches = self._select_entities(invariant.target_selector, all_entities)
        target_schema = schemas.get(invariant.target_selector.entity_type)
        identity_field = target_schema.identity_field if target_schema else None
        if not identity_field:
            return [
                f"{prefix} target entity type '{invariant.target_selector.entity_type}' "
                "has no identity contract"
            ]

        target_ids = {
            target.get(identity_field)
            for target in target_matches
            if target.get(identity_field) not in (None, "")
        }
        if not target_ids:
            return [f"{prefix} target selector did not match any identifiable entities"]
        def _field_matches_target(value: Any, targets: set) -> bool:
            """Check if a field value references any target ID. Handles lists."""
            if isinstance(value, list):
                return any(v in targets for v in value if not isinstance(v, (list, dict)))
            if isinstance(value, (dict, set)):
                return False  # unhashable types can't be in a set
            return value in targets

        if not any(_field_matches_target(entity.get(invariant.field), target_ids) for entity in matches):
            return [
                f"{prefix} no selected entity references a target via {invariant.field}"
            ]
        return []
