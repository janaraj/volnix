"""Terrarium core -- shared abstractions imported by every other module.

This package re-exports the most commonly used types, events, protocols,
context objects, the base engine class, and the error hierarchy so that
downstream code can do::

    from terrarium.core import ActionContext, Event, BaseEngine, ...
"""

# --- Identity newtypes ---------------------------------------------------
from terrarium.core.types import (
    ActorId,
    EntityId,
    EventId,
    PolicyId,
    ProfileVersion,
    RunId,
    ServiceId,
    SnapshotId,
    ToolName,
    WorldId,
)

# --- Enumerations ---------------------------------------------------------
from terrarium.core.types import (
    ActorType,
    EnforcementMode,
    FidelityMode,
    FidelitySource,
    FidelityTier,
    GapResponse,
    RealityPreset,
    StepVerdict,
    ValidationType,
    WorldMode,
)

# --- Value objects --------------------------------------------------------
from terrarium.core.types import (
    ActionCost,
    BudgetState,
    FidelityMetadata,
    SideEffect,
    StateDelta,
    Timestamp,
)

# --- Events ---------------------------------------------------------------
from terrarium.core.events import (
    AnimatorEvent,
    AnnotationEvent,
    ApprovalEvent,
    BudgetDeductionEvent,
    BudgetEvent,
    BudgetExhaustedEvent,
    BudgetWarningEvent,
    CapabilityGapEvent,
    EngineLifecycleEvent,
    Event,
    PermissionDeniedEvent,
    PolicyBlockEvent,
    PolicyEscalateEvent,
    PolicyEvent,
    PolicyFlagEvent,
    PolicyHoldEvent,
    SimulationEvent,
    TierPromotionEvent,
    ValidationFailureEvent,
    WorldEvent,
)

# --- Context & pipeline ---------------------------------------------------
from terrarium.core.context import ActionContext, ResponseProposal, StepResult

# --- Protocols ------------------------------------------------------------
from terrarium.core.protocols import (
    AdapterProtocol,
    AnimatorProtocol,
    BudgetEngineProtocol,
    FeedbackProtocol,
    GatewayProtocol,
    LedgerProtocol,
    PermissionEngineProtocol,
    PipelineStep,
    PolicyEngineProtocol,
    ReporterProtocol,
    ResponderProtocol,
    StateEngineProtocol,
    WorldCompilerProtocol,
)

# --- Base engine ----------------------------------------------------------
from terrarium.core.engine import BaseEngine

# --- Errors ---------------------------------------------------------------
from terrarium.core.errors import (
    BusError,
    BusPersistenceError,
    ConfigError,
    ConfigLayerError,
    ConfigValidationError,
    DuplicatePackError,
    EngineDependencyError,
    EngineError,
    EngineInitError,
    EntityNotFoundError,
    GatewayError,
    InvalidTransitionError,
    LedgerError,
    LLMError,
    LLMOutputValidationError,
    LLMTimeoutError,
    PackError,
    PackLoadError,
    PackNotFoundError,
    PipelineError,
    PipelineShortCircuit,
    PipelineStepError,
    RateLimitError,
    StateError,
    TerrariumError,
    ValidationError,
)

__all__ = [
    # Identity
    "ActorId",
    "EntityId",
    "EventId",
    "PolicyId",
    "ProfileVersion",
    "RunId",
    "ServiceId",
    "SnapshotId",
    "ToolName",
    "WorldId",
    # Enums
    "ActorType",
    "EnforcementMode",
    "FidelityMode",
    "FidelitySource",
    "FidelityTier",
    "GapResponse",
    "RealityPreset",
    "StepVerdict",
    "ValidationType",
    "WorldMode",
    # Value objects
    "ActionCost",
    "BudgetState",
    "FidelityMetadata",
    "SideEffect",
    "StateDelta",
    "Timestamp",
    # Events
    "AnimatorEvent",
    "AnnotationEvent",
    "ApprovalEvent",
    "BudgetDeductionEvent",
    "BudgetEvent",
    "BudgetExhaustedEvent",
    "BudgetWarningEvent",
    "CapabilityGapEvent",
    "EngineLifecycleEvent",
    "Event",
    "PermissionDeniedEvent",
    "PolicyBlockEvent",
    "PolicyEscalateEvent",
    "PolicyEvent",
    "PolicyFlagEvent",
    "PolicyHoldEvent",
    "SimulationEvent",
    "TierPromotionEvent",
    "ValidationFailureEvent",
    "WorldEvent",
    # Context
    "ActionContext",
    "ResponseProposal",
    "StepResult",
    # Protocols
    "AdapterProtocol",
    "AnimatorProtocol",
    "BudgetEngineProtocol",
    "FeedbackProtocol",
    "GatewayProtocol",
    "LedgerProtocol",
    "PermissionEngineProtocol",
    "PipelineStep",
    "PolicyEngineProtocol",
    "ReporterProtocol",
    "ResponderProtocol",
    "StateEngineProtocol",
    "WorldCompilerProtocol",
    # Engine
    "BaseEngine",
    # Errors
    "BusError",
    "BusPersistenceError",
    "ConfigError",
    "ConfigLayerError",
    "ConfigValidationError",
    "DuplicatePackError",
    "EngineDependencyError",
    "EngineError",
    "EngineInitError",
    "EntityNotFoundError",
    "GatewayError",
    "InvalidTransitionError",
    "LedgerError",
    "LLMError",
    "LLMOutputValidationError",
    "LLMTimeoutError",
    "PackError",
    "PackLoadError",
    "PackNotFoundError",
    "PipelineError",
    "PipelineShortCircuit",
    "PipelineStepError",
    "RateLimitError",
    "StateError",
    "TerrariumError",
    "ValidationError",
]
