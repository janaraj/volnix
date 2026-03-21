"""Exception hierarchy for the Terrarium framework.

Every exception raised intentionally by Terrarium code inherits from
:class:`TerrariumError`, which carries a structured ``context`` dict for
machine-readable diagnostics.  The hierarchy mirrors the major subsystems:

* **Config** -- loading, layering, and validation of configuration.
* **Engine** -- engine lifecycle and dependency resolution.
* **Pipeline** -- step execution and short-circuit flow control.
* **Bus** -- event bus delivery and persistence.
* **Validation** -- schema and semantic validation.
* **State** -- entity store operations.
* **LLM** -- language-model calls and output parsing.
* **Gateway** -- external API surface errors.
* **Ledger** -- append-only event log operations.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


class TerrariumError(Exception):
    """Root exception for all Terrarium errors.

    Attributes:
        message: Human-readable error description.
        context: Structured metadata for diagnostics and logging.
    """

    def __init__(self, message: str = "", context: dict[str, Any] | None = None) -> None:
        ...


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


class ConfigError(TerrariumError):
    """Base error for configuration-related failures."""

    pass


class ConfigLayerError(ConfigError):
    """A specific configuration layer could not be loaded or merged."""

    pass


class ConfigValidationError(ConfigError):
    """Configuration values failed schema or semantic validation."""

    pass


# ---------------------------------------------------------------------------
# Engine errors
# ---------------------------------------------------------------------------


class EngineError(TerrariumError):
    """Base error for engine lifecycle failures.

    Attributes:
        engine_name: Name of the engine that encountered the error.
    """

    def __init__(
        self,
        message: str = "",
        engine_name: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        ...


class EngineInitError(EngineError):
    """An engine failed during initialisation."""

    pass


class EngineDependencyError(EngineError):
    """A required engine dependency is missing or failed to start."""

    pass


# ---------------------------------------------------------------------------
# Pipeline errors
# ---------------------------------------------------------------------------


class PipelineError(TerrariumError):
    """Base error for governance-pipeline failures."""

    pass


class PipelineStepError(PipelineError):
    """A specific pipeline step raised an error.

    Attributes:
        step_name: Name of the step that failed.
    """

    def __init__(
        self,
        message: str = "",
        step_name: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        ...


class PipelineShortCircuit(PipelineError):
    """Flow-control exception used to terminate the pipeline early.

    This is not necessarily an error -- it indicates a legitimate early exit
    (e.g., a DENY verdict from the permission step).
    """

    pass


# ---------------------------------------------------------------------------
# Bus errors
# ---------------------------------------------------------------------------


class BusError(TerrariumError):
    """Base error for event-bus failures."""

    pass


class BusPersistenceError(BusError):
    """The event bus could not persist an event to its backing store."""

    pass


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class ValidationError(TerrariumError):
    """A validation check failed.

    Attributes:
        validation_type: Category of validation that failed (e.g. ``"schema"``,
            ``"semantic"``, ``"state_consistency"``).
    """

    def __init__(
        self,
        message: str = "",
        validation_type: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        ...


# ---------------------------------------------------------------------------
# State errors
# ---------------------------------------------------------------------------


class StateError(TerrariumError):
    """Base error for world-state operations."""

    pass


class EntityNotFoundError(StateError):
    """The requested entity does not exist in the world state."""

    pass


class InvalidTransitionError(StateError):
    """A proposed state transition violates domain invariants."""

    pass


# ---------------------------------------------------------------------------
# LLM errors
# ---------------------------------------------------------------------------


class LLMError(TerrariumError):
    """Base error for language-model integration failures."""

    pass


class LLMTimeoutError(LLMError):
    """An LLM call exceeded its timeout."""

    pass


class LLMOutputValidationError(LLMError):
    """The LLM returned output that failed structured-output validation."""

    pass


# ---------------------------------------------------------------------------
# Gateway errors
# ---------------------------------------------------------------------------


class GatewayError(TerrariumError):
    """Base error for the external-facing gateway."""

    pass


class RateLimitError(GatewayError):
    """The caller has exceeded its rate limit."""

    pass


# ---------------------------------------------------------------------------
# Ledger errors
# ---------------------------------------------------------------------------


class LedgerError(TerrariumError):
    """Base error for append-only ledger operations."""

    pass
