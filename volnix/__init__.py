"""Volnix — a world engine for AI agents.

Public API for library consumers. Import everything you need from this
module; reaching into submodules is not supported and may break across
minor releases.

Semantic versioning: 0.2.x is the first stable library surface. Minor
bumps (0.2.0 → 0.3.0) MAY add new API but never break existing
signatures; patch bumps (0.2.0 → 0.2.1) are bug-fix only.

The ``__all__`` list below groups exports by category; imports below
are sorted alphabetically by module path for linter compatibility.

**Intentionally NOT exported** (implementation details — reach into
the submodule only if you know what you're doing and accept the
minor-release-break risk):

- ``volnix.llm.providers.replay.ReplayLLMProvider`` — products that
  want to register the replay provider directly can import it, but
  the supported path is ``VolnixApp`` auto-registering it at start()
  when both ``ledger`` and ``llm_router`` are wired.
- ``volnix._internal.*`` — private helpers shared across the platform.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__: str = _pkg_version("volnix")
except PackageNotFoundError:  # running from source tree, unpackaged
    __version__ = "0.0.0+source"

from volnix.actors.behavioral_signature import (
    ActorBehaviorTraits,
    BehavioralSignature,
)
from volnix.actors.character import CharacterDefinition
from volnix.actors.character_loader import CharacterCatalogError, CharacterLoader
from volnix.actors.definition import ActorDefinition
from volnix.actors.state import ActorState
from volnix.actors.trait_extractor import (
    TraitExtractorHookError,
    resolve_extractor_hook,
)
from volnix.app import VolnixApp
from volnix.config.builder import ConfigBuilder
from volnix.config.schema import PackSearchPath, PrivacyConfig, VolnixConfig
from volnix.core.envelope import ActionEnvelope
from volnix.core.errors import (
    DuplicatePackError,
    IncompatiblePackError,
    PackManifestMismatchError,
    PackNotFoundError,
    ReplayJournalMismatch,
    ReplayProviderNotFound,
    SessionNotFoundError,
    TrajectoryFieldNotFound,
    VolnixError,
)
from volnix.core.events import (
    SessionEndedEvent,
    SessionPausedEvent,
    SessionResumedEvent,
    SessionStartedEvent,
    WorldEvent,
)
from volnix.core.memory_types import (
    MemoryQuery,
    MemoryRecall,
    MemoryRecord,
    MemoryScope,
    MemoryWrite,
)
from volnix.core.protocols import (
    MemoryEngineProtocol,
    NPCActivatorProtocol,
    PermissionEngineProtocol,
)
from volnix.core.session import Session, SessionStatus, SessionType
from volnix.core.types import (
    ActorId,
    ActorType,
    EntityId,
    EventId,
    MemoryRecordId,
    RunId,
    ServiceId,
    SessionId,
    SnapshotId,
    Timestamp,
    ToolName,
    WorldId,
)
from volnix.engines.state.trajectory import TrajectoryPoint
from volnix.ledger.entries import LedgerEntry, UnknownLedgerEntry
from volnix.ledger.query import LedgerQuery
from volnix.llm.types import LLMStreamChunk
from volnix.observation import (
    IntentBehaviorGap,
    ObservationQuery,
    PersonaContribution,
    TimelineEvent,
    TimelineSource,
    UnifiedTimeline,
    VariantDeltaReport,
    intent_behavior_gap,
    load_bearing_personas,
    variant_delta,
)
from volnix.packs.base import ServicePack, ServiceProfile
from volnix.packs.manifest import PackManifest, PackManifestLoadError
from volnix.packs.registry import PackRegistry
from volnix.privacy.redaction import (
    LedgerRedactorError,
    identity_redactor,
    resolve_ledger_redactor,
)
from volnix.sessions import SessionManager, SlotAssignment
from volnix.simulation.config import SimulationRunnerConfig
from volnix.simulation.runner import SimulationRunner, SimulationType, StopReason

__all__ = [
    "__version__",
    # Entry points
    "VolnixApp",
    "VolnixConfig",
    "ConfigBuilder",
    "PackSearchPath",
    # Core value objects
    "ActionEnvelope",
    "WorldEvent",
    "MemoryRecord",
    "MemoryQuery",
    "MemoryRecall",
    "MemoryScope",
    "MemoryWrite",
    "Session",
    "SessionEndedEvent",
    "SessionId",
    "SessionPausedEvent",
    "SessionResumedEvent",
    "SessionStartedEvent",
    "SessionStatus",
    "SessionType",
    "SessionManager",
    "SlotAssignment",
    "ActorId",
    "ActorType",
    "EntityId",
    "EventId",
    "MemoryRecordId",
    "RunId",
    "ServiceId",
    "SnapshotId",
    "Timestamp",
    "ToolName",
    "WorldId",
    # Actors
    "ActorDefinition",
    "ActorState",
    # Packs (author your own by subclassing ServicePack / ServiceProfile;
    # PackRegistry is exported as a concrete for construction in composition
    # roots — type-hint against the protocol surface once it lands).
    "ServicePack",
    "ServiceProfile",
    "PackRegistry",
    "PackManifest",
    # Protocols — prefer these over concrete engine classes when type-hinting
    # collaborators; concrete engines are imported only in composition roots.
    "MemoryEngineProtocol",
    "NPCActivatorProtocol",
    "PermissionEngineProtocol",
    # Ledger
    "LedgerEntry",
    "LedgerQuery",
    "UnknownLedgerEntry",
    # Simulation
    "SimulationRunner",
    "SimulationRunnerConfig",
    "SimulationType",
    "StopReason",
    # Character catalog (PMF Plan Phase 4C Step 11)
    "CharacterDefinition",
    "CharacterLoader",
    "CharacterCatalogError",
    # Behavioral signature (PMF Plan Phase 4C Step 12)
    "BehavioralSignature",
    "ActorBehaviorTraits",
    "TraitExtractorHookError",
    "resolve_extractor_hook",
    # Privacy (PMF Plan Phase 4C Step 14)
    "PrivacyConfig",
    "LedgerRedactorError",
    "identity_redactor",
    "resolve_ledger_redactor",
    # State trajectory (PMF Plan Phase 4C Step 9)
    "TrajectoryPoint",
    "LLMStreamChunk",
    # Observation (PMF Plan Phase 4C Step 10)
    "ObservationQuery",
    "UnifiedTimeline",
    "TimelineEvent",
    "TimelineSource",
    "IntentBehaviorGap",
    "PersonaContribution",
    "VariantDeltaReport",
    "intent_behavior_gap",
    "load_bearing_personas",
    "variant_delta",
    # Errors
    "VolnixError",
    "DuplicatePackError",
    "IncompatiblePackError",
    "PackManifestLoadError",
    "PackManifestMismatchError",
    "PackNotFoundError",
    "ReplayJournalMismatch",
    "ReplayProviderNotFound",
    "SessionNotFoundError",
    "TrajectoryFieldNotFound",
]
