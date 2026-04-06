"""Schema validation for the Volnix framework.

Validates response payloads and entity data against JSON schemas,
returning structured :class:`ValidationResult` objects.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from volnix.core.types import ValidationType

# Mapping from JSON Schema type strings to Python types.
_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class ValidationResult(BaseModel, frozen=True):
    """Result of a validation check.

    Attributes:
        valid: Whether the validation passed.
        errors: List of error messages for failures.
        warnings: List of non-fatal warning messages.
        validation_type: The category of validation that produced this result.
    """

    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_type: ValidationType | None = None

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge this result with *other*, returning a NEW instance.

        The merged result is invalid if either input is invalid.
        Errors and warnings are concatenated.  The ``validation_type`` is
        preserved from *self* when both are the same type; otherwise it is
        set to ``None`` (mixed).
        """
        merged_errors = list(self.errors) + list(other.errors)
        merged_warnings = list(self.warnings) + list(other.warnings)
        merged_valid = self.valid and other.valid
        if self.validation_type == other.validation_type:
            merged_type = self.validation_type
        else:
            merged_type = None
        return ValidationResult(
            valid=merged_valid,
            errors=merged_errors,
            warnings=merged_warnings,
            validation_type=merged_type,
        )


def _check_type(value: Any, expected_type_str: str | list[str]) -> bool:
    """Return True if *value* matches the JSON Schema type string.

    Handles union types: ``"type": ["string", "null"]`` means the value
    can be either a string or null.
    """
    # Union type — accept if value matches ANY of the listed types
    if isinstance(expected_type_str, list):
        return any(_check_type(value, t) for t in expected_type_str)
    # Null type — only None matches
    if expected_type_str == "null":
        return value is None
    expected = _TYPE_MAP.get(expected_type_str)
    if expected is None:
        return True  # unknown type — accept
    # bool is subclass of int in Python; reject bools for integer/number checks
    if expected_type_str in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, expected)


class SchemaValidator:
    """Validates dictionaries against JSON schemas."""

    def _validate(self, data: dict[str, Any], schema: dict[str, Any]) -> ValidationResult:
        """Core validation logic shared by validate_response and validate_entity."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check required fields
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        # Check property constraints
        properties = schema.get("properties", {})
        for field_name, field_schema in properties.items():
            if field_name not in data:
                continue

            value = data[field_name]

            # Type check
            expected_type = field_schema.get("type")
            if expected_type is not None and not _check_type(value, expected_type):
                errors.append(
                    f"Field '{field_name}' expected type {expected_type}, "
                    f"got {type(value).__name__}"
                )
                continue  # skip further checks on a type-mismatched value

            # Enum check
            enum_values = field_schema.get("enum")
            if enum_values is not None and value not in enum_values:
                errors.append(
                    f"Field '{field_name}' value {value!r} not in allowed values {enum_values}"
                )

            # Minimum check
            minimum = field_schema.get("minimum")
            if minimum is not None and isinstance(value, (int, float)):
                if value < minimum:
                    errors.append(f"Field '{field_name}' value {value} is below minimum {minimum}")

            # Maximum check
            maximum = field_schema.get("maximum")
            if maximum is not None and isinstance(value, (int, float)):
                if value > maximum:
                    errors.append(f"Field '{field_name}' value {value} is above maximum {maximum}")

            # Nested object validation
            if expected_type == "object" and isinstance(value, dict):
                nested_result = self._validate(value, field_schema)
                for err in nested_result.errors:
                    errors.append(f"{field_name}.{err}")

            # Array items validation
            if expected_type == "array" and isinstance(value, list):
                items_schema = field_schema.get("items")
                if items_schema:
                    for i, item in enumerate(value):
                        if isinstance(item, dict) and items_schema.get("type") == "object":
                            nested_result = self._validate(item, items_schema)
                            for err in nested_result.errors:
                                errors.append(f"{field_name}[{i}].{err}")
                        elif items_schema.get("type") and not _check_type(
                            item, items_schema["type"]
                        ):
                            errors.append(
                                f"{field_name}[{i}] expected type {items_schema['type']}, "
                                f"got {type(item).__name__}"
                            )

        # Check additionalProperties
        if not schema.get("additionalProperties", True) and properties:
            extra = set(data.keys()) - set(properties.keys())
            for field_name in sorted(extra):
                errors.append(f"Additional property '{field_name}' not allowed")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            validation_type=ValidationType.SCHEMA,
        )

    def validate_response(
        self, response: dict[str, Any], schema: dict[str, Any]
    ) -> ValidationResult:
        """Validate a response payload against a JSON schema.

        Args:
            response: The response dictionary to validate.
            schema: The JSON schema to validate against.

        Returns:
            A :class:`ValidationResult` with any errors or warnings.
        """
        return self._validate(response, schema)

    def validate_entity(
        self, entity: dict[str, Any], entity_schema: dict[str, Any]
    ) -> ValidationResult:
        """Validate an entity dictionary against an entity schema.

        Args:
            entity: The entity dictionary to validate.
            entity_schema: The JSON schema for this entity type.

        Returns:
            A :class:`ValidationResult` with any errors or warnings.
        """
        return self._validate(entity, entity_schema)
