"""Validation framework for the Terrarium framework.

Provides schema validation, state-machine transition checking, referential
consistency verification, temporal ordering, amount validation, and a
composite validation pipeline with LLM-assisted retry.

Re-exports the primary public API surface::

    from terrarium.validation import ValidationPipeline, ValidationResult
"""

from terrarium.core.types import ValidationType
from terrarium.validation.amounts import AmountValidator
from terrarium.validation.config import ValidationConfig
from terrarium.validation.consistency import ConsistencyValidator
from terrarium.validation.pipeline import ValidationPipeline
from terrarium.validation.schema import SchemaValidator, ValidationResult
from terrarium.validation.state_machine import StateMachineValidator
from terrarium.validation.temporal import TemporalValidator

__all__ = [
    "AmountValidator",
    "ConsistencyValidator",
    "SchemaValidator",
    "StateMachineValidator",
    "TemporalValidator",
    "ValidationConfig",
    "ValidationPipeline",
    "ValidationResult",
    "ValidationType",
]
