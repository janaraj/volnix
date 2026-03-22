"""Composite validation pipeline for the Terrarium framework.

Orchestrates multiple validators to validate response proposals,
with optional LLM-assisted retry for correctable validation failures.
"""

from __future__ import annotations

from typing import Any, Callable

from terrarium.core.context import ResponseProposal
from terrarium.core.protocols import StateEngineProtocol
from terrarium.core.types import ValidationType
from terrarium.validation.amounts import AmountValidator
from terrarium.validation.config import ValidationConfig
from terrarium.validation.consistency import ConsistencyValidator
from terrarium.validation.schema import SchemaValidator, ValidationResult
from terrarium.validation.state_machine import StateMachineValidator
from terrarium.validation.temporal import TemporalValidator


class ValidationPipeline:
    """Composite validator that runs multiple validators in sequence.

    Supports LLM-assisted retry: when validation fails, a callback can
    regenerate the proposal before re-validation.

    All schema, state-machine, and entity-schema data is passed as
    parameters — nothing is hardcoded.
    """

    def __init__(self, config: ValidationConfig | None = None) -> None:
        self._config = config or ValidationConfig()
        self._schema_validator = SchemaValidator()
        self._state_machine_validator = StateMachineValidator()
        self._consistency_validator = ConsistencyValidator()
        self._temporal_validator = TemporalValidator()
        self._amount_validator = AmountValidator()

    async def validate_response_proposal(
        self,
        proposal: ResponseProposal,
        state: StateEngineProtocol,
        response_schema: dict[str, Any] | None = None,
        state_machines: dict[str, dict] | None = None,
        entity_schemas: dict[str, dict] | None = None,
    ) -> ValidationResult:
        """Validate a response proposal against all registered validators.

        Args:
            proposal: The response proposal to validate.
            state: The state engine for consistency checks.
            response_schema: Optional JSON Schema for the response body.
            state_machines: Optional mapping of entity type to state machine
                definitions (each with a ``"transitions"`` key).
            entity_schemas: Optional mapping of entity type to entity schema
                (each with a ``"fields"`` key).

        Returns:
            A combined :class:`ValidationResult` from all validators.
        """
        result = ValidationResult(valid=True)

        # 1. Schema validation on response body
        if response_schema is not None:
            schema_result = self._schema_validator.validate_response(
                proposal.response_body, response_schema
            )
            result = result.merge(schema_result)

        # 2. State-machine validation on deltas
        if state_machines is not None:
            for delta in proposal.proposed_state_deltas:
                sm = state_machines.get(delta.entity_type)
                if sm is None:
                    continue
                # If the delta has a "status" field and previous "status",
                # validate the transition
                new_status = delta.fields.get("status")
                prev_status = (
                    delta.previous_fields.get("status")
                    if delta.previous_fields
                    else None
                )
                if new_status is not None and prev_status is not None:
                    sm_result = self._state_machine_validator.validate_transition(
                        prev_status, new_status, sm
                    )
                    result = result.merge(sm_result)
                elif new_status is not None and prev_status is None:
                    # On create, validate that new_status is a valid state in the machine
                    all_states: set[str] = set(sm.get("transitions", {}).keys())
                    for targets in sm.get("transitions", {}).values():
                        all_states.update(targets)
                    if all_states and new_status not in all_states:
                        result = result.merge(ValidationResult(
                            valid=False,
                            errors=[f"Initial state '{new_status}' is not defined in the state machine"],
                            validation_type=ValidationType.STATE_MACHINE,
                        ))

        # 3. Consistency validation on deltas
        if entity_schemas is not None:
            for delta in proposal.proposed_state_deltas:
                es = entity_schemas.get(delta.entity_type)
                if es is None:
                    continue
                cons_result = await self._consistency_validator.validate_references(
                    delta, es, state
                )
                result = result.merge(cons_result)

        # 4. Amount validation — check for non-negative amounts in deltas
        for delta in proposal.proposed_state_deltas:
            amount = delta.fields.get("amount")
            if amount is not None and isinstance(amount, (int, float)):
                amt_result = self._amount_validator.validate_non_negative(
                    amount, f"{delta.entity_type}.amount"
                )
                result = result.merge(amt_result)

            # If this is a refund, validate refund <= charge
            refund = delta.fields.get("refund_amount")
            charge = delta.fields.get("charge_amount")
            if refund is not None and charge is not None:
                ref_result = self._amount_validator.validate_refund_amount(
                    refund, charge
                )
                result = result.merge(ref_result)

        return result

    async def validate_with_retry(
        self,
        proposal: ResponseProposal,
        state: StateEngineProtocol,
        llm_callback: Callable[..., Any],
        max_retries: int | None = None,
        response_schema: dict[str, Any] | None = None,
        state_machines: dict[str, dict] | None = None,
        entity_schemas: dict[str, dict] | None = None,
    ) -> tuple[ResponseProposal, ValidationResult]:
        """Validate with optional LLM-assisted retry on failure.

        If validation fails and retries remain, invokes *llm_callback* with
        the validation errors to produce a corrected proposal, then
        re-validates.

        Args:
            proposal: The initial response proposal.
            state: The state engine for consistency checks.
            llm_callback: An async callable that takes a proposal and error list
                and returns a corrected proposal.
            max_retries: Maximum number of retry attempts.  Defaults to
                ``config.max_retries``.
            response_schema: Optional JSON Schema for the response body.
            state_machines: Optional state machine definitions.
            entity_schemas: Optional entity schema definitions.

        Returns:
            A tuple of the (possibly corrected) proposal and its validation result.
        """
        hard_cap = 10
        effective_retries = min(max_retries, hard_cap) if max_retries is not None else min(self._config.max_retries, hard_cap)
        current_proposal = proposal

        result = await self.validate_response_proposal(
            current_proposal,
            state,
            response_schema=response_schema,
            state_machines=state_machines,
            entity_schemas=entity_schemas,
        )

        attempts = 0
        while not result.valid and attempts < effective_retries:
            try:
                new_proposal = await llm_callback(current_proposal, result.errors)
            except Exception:
                break  # Return last known result
            if new_proposal is None:
                break
            current_proposal = new_proposal
            result = await self.validate_response_proposal(
                current_proposal,
                state,
                response_schema=response_schema,
                state_machines=state_machines,
                entity_schemas=entity_schemas,
            )
            attempts += 1

        return current_proposal, result
