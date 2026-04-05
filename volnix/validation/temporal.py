"""Temporal validation for the Volnix framework.

Validates timestamp plausibility and ordering constraints to ensure
events are not created with impossible temporal relationships.
"""

from __future__ import annotations

from datetime import datetime

from volnix.core.types import ValidationType
from volnix.validation.schema import ValidationResult
from volnix.validation.schema_contracts import TemporalOrderingRule


class TemporalValidator:
    """Validates temporal constraints on events and timestamps."""

    def validate_timestamp(
        self,
        event_time: datetime,
        world_time: datetime,
    ) -> ValidationResult:
        """Validate that an event timestamp is plausible relative to world time.

        An event must not occur *after* the current world time.

        Args:
            event_time: The timestamp of the event.
            world_time: The current simulated world time.

        Returns:
            A :class:`ValidationResult` flagging any temporal anomalies.
        """
        try:
            is_future = event_time > world_time
        except TypeError:
            return ValidationResult(
                valid=False,
                errors=["Cannot compare timezone-aware and timezone-naive timestamps"],
                validation_type=ValidationType.TEMPORAL,
            )
        if is_future:
            return ValidationResult(
                valid=False,
                errors=[
                    f"Event time {event_time.isoformat()} is after "
                    f"world time {world_time.isoformat()}"
                ],
                validation_type=ValidationType.TEMPORAL,
            )
        return ValidationResult(
            valid=True,
            validation_type=ValidationType.TEMPORAL,
        )

    def validate_entity_orderings(
        self,
        entity_type: str,
        entity: dict[str, object],
        orderings: list[TemporalOrderingRule],
    ) -> ValidationResult:
        """Validate explicit intra-entity temporal ordering metadata."""
        result = ValidationResult(
            valid=True,
            validation_type=ValidationType.TEMPORAL,
        )

        for ordering in orderings:
            if (
                ordering.before_field not in entity
                or ordering.after_field not in entity
            ):
                continue

            before = entity.get(ordering.before_field)
            after = entity.get(ordering.after_field)
            if before in (None, "") or after in (None, ""):
                continue

            parsed_before, before_error = self._coerce_datetime(before)
            if before_error is not None:
                result = result.merge(
                    ValidationResult(
                        valid=False,
                        errors=[
                            f"{entity_type}.{ordering.before_field}: {before_error}"
                        ],
                        validation_type=ValidationType.TEMPORAL,
                    )
                )
                continue

            parsed_after, after_error = self._coerce_datetime(after)
            if after_error is not None:
                result = result.merge(
                    ValidationResult(
                        valid=False,
                        errors=[
                            f"{entity_type}.{ordering.after_field}: {after_error}"
                        ],
                        validation_type=ValidationType.TEMPORAL,
                    )
                )
                continue

            context = ordering.context or (
                f"{entity_type}.{ordering.before_field} <= "
                f"{entity_type}.{ordering.after_field}"
            )
            result = result.merge(
                self.validate_ordering(parsed_before, parsed_after, context)
            )

        return result

    def _coerce_datetime(
        self,
        value: object,
    ) -> tuple[datetime | None, str | None]:
        """Parse a concrete field value into a datetime for ordering checks."""
        if isinstance(value, datetime):
            return value, None
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized), None
            except ValueError:
                return None, f"invalid datetime value {value!r}"
        return None, f"unsupported datetime value {value!r}"

    def validate_ordering(
        self,
        before: datetime,
        after: datetime,
        context: str,
    ) -> ValidationResult:
        """Validate that *before* precedes or equals *after*.

        Args:
            before: The earlier timestamp.
            after: The later timestamp.
            context: A human-readable description of what is being checked.

        Returns:
            A :class:`ValidationResult` indicating whether the ordering holds.
        """
        try:
            is_misordered = before > after
        except TypeError:
            return ValidationResult(
                valid=False,
                errors=["Cannot compare timezone-aware and timezone-naive timestamps"],
                validation_type=ValidationType.TEMPORAL,
            )
        if is_misordered:
            return ValidationResult(
                valid=False,
                errors=[
                    f"Temporal ordering violation ({context}): "
                    f"{before.isoformat()} is after {after.isoformat()}"
                ],
                validation_type=ValidationType.TEMPORAL,
            )
        return ValidationResult(
            valid=True,
            validation_type=ValidationType.TEMPORAL,
        )
