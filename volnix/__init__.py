"""Volnix — a world engine for AI agents.

Public API for library consumers. Import everything you need from this
module; reaching into submodules is not supported and may break across
minor releases.

Semantic versioning: 0.2.x is the first stable library surface. Minor
bumps (0.2.0 → 0.3.0) MAY add new API but never break existing
signatures; patch bumps (0.2.0 → 0.2.1) are bug-fix only.

The ``__all__`` list below groups exports by category; imports below
are sorted alphabetically by module path for linter compatibility.

Additional exports land in later Phase 4C steps — see
``internal_docs/pmf/phase-4c-platform-hardening.md`` for the roadmap.
Reserved for future steps (not yet exported):
    Step 2 — ConfigBuilder
    Step 3 — UnknownLedgerEntry
    Step 4 — Session, SessionId, SessionStatus, SessionType,
             Session{Started,Ended,Resumed}Event
    Step 5 — SessionManager, SessionNotFoundError
    Step 9 — TrajectoryFieldNotFound
    Step 10 — ObservationQuery, UnifiedTimeline, TrajectoryPoint,
              IntentBehaviorGap, PersonaContribution,
              VariantDeltaReport, intent_behavior_gap,
              load_bearing_personas, variant_delta
    Step 11 — CharacterDefinition, CharacterLoader
    Step 12 — BehavioralSignature
    Step 13 — PackManifest, IncompatiblePackError,
              PackManifestMismatchError
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__: str = _pkg_version("volnix")
except PackageNotFoundError:  # running from source tree, unpackaged
    __version__ = "0.0.0+source"

from volnix.actors.definition import ActorDefinition
from volnix.actors.state import ActorState
from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.core.envelope import ActionEnvelope
from volnix.core.errors import (
    DuplicatePackError,
    PackNotFoundError,
    VolnixError,
)
from volnix.core.events import WorldEvent
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
from volnix.core.types import (
    ActorId,
    ActorType,
    EntityId,
    EventId,
    MemoryRecordId,
    RunId,
    ServiceId,
    SnapshotId,
    Timestamp,
    ToolName,
    WorldId,
)
from volnix.ledger.entries import LedgerEntry
from volnix.ledger.query import LedgerQuery
from volnix.packs.base import ServicePack, ServiceProfile
from volnix.packs.registry import PackRegistry
from volnix.simulation.config import SimulationRunnerConfig
from volnix.simulation.runner import SimulationRunner, SimulationType, StopReason

__all__ = [
    "__version__",
    # Entry points
    "VolnixApp",
    "VolnixConfig",
    # Core value objects
    "ActionEnvelope",
    "WorldEvent",
    "MemoryRecord",
    "MemoryQuery",
    "MemoryRecall",
    "MemoryScope",
    "MemoryWrite",
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
    # Protocols — prefer these over concrete engine classes when type-hinting
    # collaborators; concrete engines are imported only in composition roots.
    "MemoryEngineProtocol",
    "NPCActivatorProtocol",
    "PermissionEngineProtocol",
    # Ledger
    "LedgerEntry",
    "LedgerQuery",
    # Simulation
    "SimulationRunner",
    "SimulationRunnerConfig",
    "SimulationType",
    "StopReason",
    # Errors
    "VolnixError",
    "DuplicatePackError",
    "PackNotFoundError",
]
