"""Composite validation pipeline for the Terrarium framework.

Orchestrates multiple validators to validate response proposals,
with optional LLM-assisted retry for correctable validation failures.
"""

from __future__ import annotations

from typing import Any, Callable

from terrarium.core.context import ResponseProposal
from terrarium.core.protocols import StateEngineProtocol
from terrarium.validation.schema import ValidationResult


class ValidationPipeline:
    """Composite validator that runs multiple validators in sequence.

    Supports LLM-assisted retry: when validation fails, a callback can
    regenerate the proposal before re-validation.
    """

    def __init__(self, validators: list[Any]) -> None:
        ...

    async def validate_response_proposal(
        self,
        proposal: ResponseProposal,
        state: StateEngineProtocol,
    ) -> ValidationResult:
        """Validate a response proposal against all registered validators.

        Args:
            proposal: The response proposal to validate.
            state: The state engine for consistency checks.

        Returns:
            A combined :class:`ValidationResult` from all validators.
        """
        ...

    async def validate_with_retry(
        self,
        proposal: ResponseProposal,
        state: StateEngineProtocol,
        llm_callback: Callable[..., Any],
        max_retries: int = 1,
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
            max_retries: Maximum number of retry attempts.

        Returns:
            A tuple of the (possibly corrected) proposal and its validation result.
        """
        ...
