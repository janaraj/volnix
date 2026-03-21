"""Referential consistency validation for the Terrarium framework.

Verifies that state deltas reference existing entities and that
cross-entity references remain consistent after proposed mutations.
"""

from __future__ import annotations

from terrarium.core.protocols import StateEngineProtocol
from terrarium.core.types import EntityId, StateDelta
from terrarium.validation.schema import ValidationResult


class ConsistencyValidator:
    """Validates referential consistency of state mutations."""

    async def validate_references(
        self,
        delta: StateDelta,
        state: StateEngineProtocol,
    ) -> ValidationResult:
        """Validate that all entity references in a state delta are resolvable.

        Args:
            delta: The proposed state mutation.
            state: The state engine for entity lookups.

        Returns:
            A :class:`ValidationResult` with any referential integrity errors.
        """
        ...

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
        ...
