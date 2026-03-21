"""Schema validation for the Terrarium framework.

Validates response payloads and entity data against JSON schemas,
returning structured :class:`ValidationResult` objects.
"""

from __future__ import annotations

from pydantic import BaseModel


class ValidationResult(BaseModel):
    """Result of a validation check.

    Attributes:
        valid: Whether the validation passed.
        errors: List of error messages for failures.
        warnings: List of non-fatal warning messages.
    """

    valid: bool = True
    errors: list[str] = []
    warnings: list[str] = []


class SchemaValidator:
    """Validates dictionaries against JSON schemas."""

    def validate_response(self, response: dict, schema: dict) -> ValidationResult:
        """Validate a response payload against a JSON schema.

        Args:
            response: The response dictionary to validate.
            schema: The JSON schema to validate against.

        Returns:
            A :class:`ValidationResult` with any errors or warnings.
        """
        ...

    def validate_entity(self, entity: dict, entity_schema: dict) -> ValidationResult:
        """Validate an entity dictionary against an entity schema.

        Args:
            entity: The entity dictionary to validate.
            entity_schema: The JSON schema for this entity type.

        Returns:
            A :class:`ValidationResult` with any errors or warnings.
        """
        ...
