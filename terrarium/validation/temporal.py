"""Temporal validation for the Terrarium framework.

Validates timestamp plausibility and ordering constraints to ensure
events are not created with impossible temporal relationships.
"""

from __future__ import annotations

from datetime import datetime

from terrarium.core.types import ValidationType
from terrarium.validation.schema import ValidationResult


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
