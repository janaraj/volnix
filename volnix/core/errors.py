"""Exception hierarchy for the Volnix framework.

Every exception raised intentionally by Volnix code inherits from
:class:`VolnixError`, which carries a structured ``context`` dict for
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


class VolnixError(Exception):
    """Root exception for all Volnix errors.

    Attributes:
        message: Human-readable error description.
        context: Structured metadata for diagnostics and logging.
    """

    def __init__(self, message: str = "", context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


class ConfigError(VolnixError):
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


class EngineError(VolnixError):
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
        super().__init__(message, context)
        self.engine_name = engine_name


class EngineInitError(EngineError):
    """An engine failed during initialisation."""

    pass


class EngineDependencyError(EngineError):
    """A required engine dependency is missing or failed to start."""

    pass


# ---------------------------------------------------------------------------
# Pipeline errors
# ---------------------------------------------------------------------------


class PipelineError(VolnixError):
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
        super().__init__(message, context)
        self.step_name = step_name


class PipelineShortCircuit(PipelineError):
    """Flow-control exception used to terminate the pipeline early.

    This is not necessarily an error -- it indicates a legitimate early exit
    (e.g., a DENY verdict from the permission step).
    """

    pass


# ---------------------------------------------------------------------------
# Bus errors
# ---------------------------------------------------------------------------


class BusError(VolnixError):
    """Base error for event-bus failures."""

    pass


class BusPersistenceError(BusError):
    """The event bus could not persist an event to its backing store."""

    pass


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class ValidationError(VolnixError):
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
        super().__init__(message, context)
        self.validation_type = validation_type


# ---------------------------------------------------------------------------
# State errors
# ---------------------------------------------------------------------------


class StateError(VolnixError):
    """Base error for world-state operations."""

    pass


class EntityNotFoundError(StateError):
    """The requested entity does not exist in the world state."""

    pass


class InvalidTransitionError(StateError):
    """A proposed state transition violates domain invariants."""

    pass


# ---------------------------------------------------------------------------
# Pack errors
# ---------------------------------------------------------------------------


class PackError(VolnixError):
    """Base error for service pack operations."""

    pass


class PackNotFoundError(PackError):
    """No pack registered for the requested name or tool."""

    pass


class PackLoadError(PackError):
    """A pack module could not be loaded from disk."""

    pass


class DuplicatePackError(PackError):
    """A pack with the same pack_name is already registered."""

    pass


# ---------------------------------------------------------------------------
# LLM errors
# ---------------------------------------------------------------------------


class LLMError(VolnixError):
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


class GatewayError(VolnixError):
    """Base error for the external-facing gateway."""

    pass


class RateLimitError(GatewayError):
    """The caller has exceeded its rate limit."""

    pass


# ---------------------------------------------------------------------------
# Ledger errors
# ---------------------------------------------------------------------------


class LedgerError(VolnixError):
    """Base error for append-only ledger operations."""

    pass


# ---------------------------------------------------------------------------
# Reality errors
# ---------------------------------------------------------------------------


class RealityError(VolnixError):
    """Base error for reality dimension operations."""

    pass


class InvalidLabelError(RealityError):
    """An unrecognized dimension label was provided."""

    pass


class InvalidPresetError(RealityError):
    """An unrecognized reality preset was requested."""

    pass


class DimensionValueError(RealityError):
    """A dimension attribute value is out of the valid range."""

    pass


# ---------------------------------------------------------------------------
# Actor errors
# ---------------------------------------------------------------------------


class ActorError(VolnixError):
    """Base error for actor-related failures."""

    pass


class ActorNotFoundError(ActorError):
    """The requested actor does not exist in the registry."""

    pass


class DuplicateActorError(ActorError):
    """An actor with the same ID is already registered."""

    pass


class ActorGenerationError(ActorError):
    """Actor generation (personality, friction, batch) failed."""

    pass


# ---------------------------------------------------------------------------
# Session errors (PMF Plan Phase 4C Step 5)
# ---------------------------------------------------------------------------


class ReplayJournalMismatch(VolnixError):
    """Raised by ``ReplayLLMProvider`` when the utterance journal
    does not contain the expected entries for a replay lookup key.

    Subclass of ``VolnixError`` per Step-1 error-hierarchy lock.
    PMF Plan Phase 4C Step 8.
    """

    pass


class ReplayProviderNotFound(VolnixError):
    """Raised by ``LLMRouter.route`` when ``replay_mode=True`` is
    requested but no ``"replay"`` provider is registered in the
    provider registry.

    PMF Plan Phase 4C Step 8.
    """

    pass


class SessionNotFoundError(VolnixError):
    """Raised when ``SessionManager`` is asked for a session id
    that isn't in the store.

    Subclass of ``VolnixError`` so consumers catching the root still
    catch it — locked by
    ``tests/architecture/test_public_api.py::
    test_negative_every_exported_error_inherits_volnix_error``.
    """

    def __init__(self, session_id: str, message: str = "") -> None:
        super().__init__(
            message or f"Session {session_id!r} not found",
            context={"session_id": session_id},
        )
        self.session_id = session_id


# ---------------------------------------------------------------------------
# Kernel errors
# ---------------------------------------------------------------------------


class KernelError(VolnixError):
    """Base error for semantic kernel operations."""

    pass


class ServiceResolutionError(KernelError):
    """A service could not be resolved to a ServiceSurface."""

    pass


class SpecParseError(KernelError):
    """An API specification could not be parsed."""

    pass


# ---------------------------------------------------------------------------
# Compiler errors
# ---------------------------------------------------------------------------


class CompilerError(VolnixError):
    """Base error for world compiler operations."""

    pass


class YAMLParseError(CompilerError):
    """A YAML world definition or compiler settings file could not be parsed."""

    pass


class NLParseError(CompilerError):
    """Natural language parsing (LLM translation) failed."""

    pass


class ServiceResolutionFailedError(CompilerError):
    """A service could not be resolved during world compilation."""

    pass


class WorldPlanValidationError(CompilerError):
    """The assembled WorldPlan failed validation."""

    pass


class WorldGenerationValidationError(CompilerError):
    """Generated world data failed post-generation validation."""

    pass
