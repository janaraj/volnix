"""Referential consistency validation for the Terrarium framework.

Verifies that state deltas reference existing entities and that
cross-entity references remain consistent after proposed mutations.
"""

from __future__ import annotations

from terrarium.core.errors import EntityNotFoundError
from terrarium.core.protocols import StateEngineProtocol
from terrarium.core.types import EntityId, StateDelta, ValidationType
from terrarium.validation.schema import ValidationResult


class ConsistencyValidator:
    """Validates referential consistency of state mutations."""

    async def validate_references(
        self,
        delta: StateDelta,
        entity_schema: dict,
        state: StateEngineProtocol,
    ) -> ValidationResult:
        """Validate that all entity references in a state delta are resolvable.

        Reference fields are identified from the *entity_schema* — any field
        whose type string starts with ``"ref:"`` is treated as a foreign-key
        reference to another entity type.

        Args:
            delta: The proposed state mutation.
            entity_schema: Schema dict with a ``"fields"`` mapping from field
                name to type string.  E.g. ``{"fields": {"charge": "ref:charge"}}``.
            state: The state engine for entity lookups.

        Returns:
            A :class:`ValidationResult` with any referential integrity errors.
        """
        errors: list[str] = []
        fields_spec = entity_schema.get("fields", {})

        for field_name, field_type in fields_spec.items():
            if not isinstance(field_type, str) or not field_type.startswith("ref:"):
                continue

            # The field is a reference — check if the delta provides a value
            if field_name not in delta.fields:
                continue

            ref_id = delta.fields[field_name]
            ref_entity_type = field_type.split(":", 1)[1]

            try:
                await state.get_entity(ref_entity_type, EntityId(str(ref_id)))
            except (EntityNotFoundError, KeyError):
                errors.append(
                    f"Referenced {ref_entity_type} entity '{ref_id}' "
                    f"not found (field '{field_name}')"
                )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            validation_type=ValidationType.CONSISTENCY,
        )

    async def validate_entity_exists(
        self,
        entity_type: str,
        entity_id: EntityId,
        state: StateEngineProtocol,
    ) -> ValidationResult:
        """Verify that a specific entity exists in the state store.

        Args:
            entity_type: The expected type of the entity.
            entity_id: The identifier of the entity to check.
            state: The state engine for entity lookups.

        Returns:
            A :class:`ValidationResult` indicating existence.
        """
        try:
            await state.get_entity(entity_type, entity_id)
            return ValidationResult(
                valid=True,
                validation_type=ValidationType.CONSISTENCY,
            )
        except (EntityNotFoundError, KeyError):
            return ValidationResult(
                valid=False,
                errors=[
                    f"Entity '{entity_id}' of type '{entity_type}' not found"
                ],
                validation_type=ValidationType.CONSISTENCY,
            )
