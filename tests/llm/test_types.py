"""Tests for volnix.llm.types — specifically LLMUsage None tolerance.

Regression guards for the ``gemini-3-flash-preview`` quirk observed
during the P6.3 supply-chain live run (run_3cddf66b187c): the provider
occasionally returned ``response.usage_metadata.candidates_token_count =
None`` (attribute set, value null). The Google provider's defensive
``getattr(usage_meta, "candidates_token_count", 0)`` default only fires
when the attribute is *missing*, not when it's *None*, so ``None`` was
passed to ``LLMUsage(completion_tokens=None)`` and pydantic v2 raised
``ValidationError`` — which the router treated as non-retryable and the
agency loop silently collapsed to ``do_nothing``, eating the agent's
turn.

The fix: ``LLMUsage`` field validators in ``mode="before"`` coerce
``None`` to ``0`` / ``0.0`` at the model boundary. These tests lock in
that behavior and guard against future regressions.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.llm.types import LLMUsage


class TestLLMUsageDefaults:
    """Default construction path — regression guard on the normal case."""

    def test_default_construction_all_zero(self):
        """`LLMUsage()` with no args produces all-zero fields."""
        usage = LLMUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.cost_usd == 0.0

    def test_explicit_values_echo_through(self):
        """Explicit int/float values pass through unchanged."""
        usage = LLMUsage(
            prompt_tokens=100,
            completion_tokens=42,
            total_tokens=142,
            cost_usd=0.005,
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 42
        assert usage.total_tokens == 142
        assert usage.cost_usd == 0.005

    def test_frozen_model_rejects_mutation(self):
        """LLMUsage is frozen — assignment after construction is rejected.

        Regression guard: frozen=True must not be lost when we added
        the field validators.
        """
        usage = LLMUsage(prompt_tokens=10)
        with pytest.raises(ValidationError):
            usage.prompt_tokens = 20  # type: ignore[misc]


class TestLLMUsageNoneCoercion:
    """The main regression guard: None → 0 coercion at the model boundary."""

    def test_none_completion_tokens_coerced_to_zero(self):
        """`LLMUsage(completion_tokens=None)` does NOT raise; field is 0.

        This is the exact shape that crashed in run_3cddf66b187c.
        """
        usage = LLMUsage(completion_tokens=None)  # type: ignore[arg-type]
        assert usage.completion_tokens == 0

    def test_none_prompt_tokens_coerced_to_zero(self):
        """`LLMUsage(prompt_tokens=None)` does NOT raise; field is 0."""
        usage = LLMUsage(prompt_tokens=None)  # type: ignore[arg-type]
        assert usage.prompt_tokens == 0

    def test_none_total_tokens_coerced_to_zero(self):
        """`LLMUsage(total_tokens=None)` does NOT raise; field is 0."""
        usage = LLMUsage(total_tokens=None)  # type: ignore[arg-type]
        assert usage.total_tokens == 0

    def test_none_cost_usd_coerced_to_zero_float(self):
        """`LLMUsage(cost_usd=None)` does NOT raise; field is 0.0."""
        usage = LLMUsage(cost_usd=None)  # type: ignore[arg-type]
        assert usage.cost_usd == 0.0
        assert isinstance(usage.cost_usd, float)

    def test_all_fields_none_coerced(self):
        """Construction with None for every field produces an all-zero usage.

        Belt-and-suspenders guard: the scenario where a provider
        bulk-passes None for an entire usage block (e.g. when the
        underlying SDK returns a usage object whose fields are all
        null) should still produce a valid LLMUsage.
        """
        usage = LLMUsage(
            prompt_tokens=None,  # type: ignore[arg-type]
            completion_tokens=None,  # type: ignore[arg-type]
            total_tokens=None,  # type: ignore[arg-type]
            cost_usd=None,  # type: ignore[arg-type]
        )
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.cost_usd == 0.0

    def test_mixed_none_and_values(self):
        """Mix of None and real values — Nones coerced, values preserved."""
        usage = LLMUsage(
            prompt_tokens=50,
            completion_tokens=None,  # type: ignore[arg-type]
            total_tokens=50,
            cost_usd=0.001,
        )
        assert usage.prompt_tokens == 50
        assert usage.completion_tokens == 0  # coerced
        assert usage.total_tokens == 50
        assert usage.cost_usd == 0.001


class TestLLMUsageInvalidTypesStillRejected:
    """Non-None invalid types still fail validation — None tolerance is narrow.

    We only tolerate None, not arbitrary garbage. Strings, lists, and
    other non-numeric types should still raise ValidationError as
    pydantic's default behavior.
    """

    def test_string_prompt_tokens_rejected(self):
        """A non-numeric string for prompt_tokens still raises."""
        with pytest.raises(ValidationError):
            LLMUsage(prompt_tokens="lots")  # type: ignore[arg-type]

    def test_list_completion_tokens_rejected(self):
        """A list for completion_tokens still raises."""
        with pytest.raises(ValidationError):
            LLMUsage(completion_tokens=[1, 2, 3])  # type: ignore[arg-type]

    def test_float_for_int_field_tolerated(self):
        """A float (e.g. 50.0) for an int field is coerced by pydantic.

        Not our validator's job — this is pydantic's standard int
        coercion. We include the test to document the contract.
        """
        usage = LLMUsage(prompt_tokens=50.0)  # type: ignore[arg-type]
        assert usage.prompt_tokens == 50
