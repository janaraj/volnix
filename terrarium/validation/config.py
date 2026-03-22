"""Configuration for the Terrarium validation framework."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ValidationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    """Validation framework configuration.

    Attributes:
        strict_mode: When True, treat warnings as errors.
        max_retries: Maximum LLM retry attempts on validation failure.
        max_reference_depth: Maximum depth for following entity references.
    """

    strict_mode: bool = True
    max_retries: int = 1
    max_reference_depth: int = 5
