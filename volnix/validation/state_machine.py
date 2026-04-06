"""State-machine transition validation for the Volnix framework.

Validates that proposed state transitions are legal according to a
state-machine definition (adjacency map of valid transitions).
"""

from __future__ import annotations

from volnix.core.types import ValidationType
from volnix.validation.schema import ValidationResult


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
            state_machine: A dict with a ``"transitions"`` key mapping states
                to lists of valid successor states.

        Returns:
            A :class:`ValidationResult` indicating whether the transition is allowed.
        """
        transitions = state_machine.get("transitions", {})
        valid_targets = transitions.get(current_state, [])

        if new_state in valid_targets:
            return ValidationResult(
                valid=True,
                validation_type=ValidationType.STATE_MACHINE,
            )

        # Collect all known states (sources + targets)
        all_known_states = set(transitions.keys())
        for targets in transitions.values():
            all_known_states.update(targets)

        if current_state not in transitions:
            error_msg = f"State '{current_state}' is not defined in the state machine"
        elif new_state not in all_known_states:
            error_msg = (
                f"Target state '{new_state}' is not a recognized state in the "
                f"state machine. Known states: {sorted(all_known_states)}"
            )
        else:
            error_msg = (
                f"Invalid transition from '{current_state}' to '{new_state}'. "
                f"Valid transitions: {valid_targets}"
            )
        return ValidationResult(
            valid=False,
            errors=[error_msg],
            validation_type=ValidationType.STATE_MACHINE,
        )

    def get_valid_transitions(
        self,
        current_state: str,
        state_machine: dict,
    ) -> list[str]:
        """Return the list of valid successor states from *current_state*.

        Args:
            current_state: The current state of the entity.
            state_machine: A dict with a ``"transitions"`` key mapping states
                to lists of valid successor states.

        Returns:
            A list of valid target state strings (empty if state is unknown).
        """
        transitions = state_machine.get("transitions", {})
        return list(transitions.get(current_state, []))
