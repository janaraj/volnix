"""State-machine transition validation for the Terrarium framework.

Validates that proposed state transitions are legal according to a
state-machine definition (adjacency map of valid transitions).
"""

from __future__ import annotations

from terrarium.validation.schema import ValidationResult


class StateMachineValidator:
    """Validates state transitions against a state-machine definition."""

    def validate_transition(
        self,
        current_state: str,
        new_state: str,
        state_machine: dict,
    ) -> ValidationResult:
        """Check whether a transition from *current_state* to *new_state* is valid.

        Args:
            current_state: The current state of the entity.
            new_state: The proposed new state.
            state_machine: A dict mapping states to lists of valid successor states.

        Returns:
            A :class:`ValidationResult` indicating whether the transition is allowed.
        """
        ...

    def get_valid_transitions(
        self,
        current_state: str,
        state_machine: dict,
    ) -> list[str]:
        """Return the list of valid successor states from *current_state*.

        Args:
            current_state: The current state of the entity.
            state_machine: A dict mapping states to lists of valid successor states.

        Returns:
            A list of valid target state strings.
        """
        ...
