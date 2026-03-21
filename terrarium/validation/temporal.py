"""Temporal validation for the Terrarium framework.

Validates timestamp plausibility and ordering constraints to ensure
events are not created with impossible temporal relationships.
"""

from __future__ import annotations

from datetime import datetime

from terrarium.validation.schema import ValidationResult


class TemporalValidator:
    """Validates temporal constraints on events and timestamps."""

    def validate_timestamp(
        self,
        event_time: datetime,
        world_time: datetime,
    ) -> ValidationResult:
        """Validate that an event timestamp is plausible relative to world time.

        Args:
            event_time: The timestamp of the event.
            world_time: The current simulated world time.

        Returns:
            A :class:`ValidationResult` flagging any temporal anomalies.
        """
        ...

    def validate_ordering(
        self,
        before: datetime,
        after: datetime,
        context: str,
    ) -> ValidationResult:
        """Validate that *before* precedes *after*.

        Args:
            before: The earlier timestamp.
            after: The later timestamp.
            context: A human-readable description of what is being checked.

        Returns:
            A :class:`ValidationResult` indicating whether the ordering holds.
        """
        ...
