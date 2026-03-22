"""Amount and budget validation for the Terrarium framework.

Validates monetary amounts, refund constraints, budget deductions,
and non-negativity invariants.
"""

from __future__ import annotations

from terrarium.core.types import ValidationType
from terrarium.validation.schema import ValidationResult


class AmountValidator:
    """Validates numeric amounts and budget constraints."""

    def validate_refund_amount(
        self,
        refund_amount: int,
        charge_amount: int,
    ) -> ValidationResult:
        """Validate that a refund does not exceed the original charge.

        Args:
            refund_amount: The proposed refund amount.
            charge_amount: The original charge amount.

        Returns:
            A :class:`ValidationResult` indicating validity.
        """
        if refund_amount > charge_amount:
            return ValidationResult(
                valid=False,
                errors=[
                    f"Refund amount {refund_amount} exceeds "
                    f"charge amount {charge_amount}"
                ],
                validation_type=ValidationType.AMOUNT,
            )
        return ValidationResult(
            valid=True,
            validation_type=ValidationType.AMOUNT,
        )

    def validate_budget_deduction(
        self,
        deduction: float,
        remaining: float,
    ) -> ValidationResult:
        """Validate that a budget deduction does not exceed remaining funds.

        Args:
            deduction: The proposed deduction amount.
            remaining: The remaining budget.

        Returns:
            A :class:`ValidationResult` indicating validity.
        """
        if deduction > remaining + 1e-9:  # epsilon tolerance for float precision
            return ValidationResult(
                valid=False,
                errors=[
                    f"Deduction {deduction} exceeds "
                    f"remaining budget {remaining}"
                ],
                validation_type=ValidationType.AMOUNT,
            )
        return ValidationResult(
            valid=True,
            validation_type=ValidationType.AMOUNT,
        )

    def validate_non_negative(
        self,
        value: float,
        field_name: str,
    ) -> ValidationResult:
        """Validate that a value is non-negative.

        Args:
            value: The value to check.
            field_name: Human-readable name of the field being checked.

        Returns:
            A :class:`ValidationResult` indicating validity.
        """
        if value < 0:
            return ValidationResult(
                valid=False,
                errors=[
                    f"Field '{field_name}' has negative value: {value}"
                ],
                validation_type=ValidationType.AMOUNT,
            )
        return ValidationResult(
            valid=True,
            validation_type=ValidationType.AMOUNT,
        )
