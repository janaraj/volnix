I have thoroughly explored every relevant file in the codebase. Now I will produce the comprehensive implementation plan directly in this response, as the system limitations prevent me from writing to the plan file.

---

# Terrarium AgencyEngine -- Complete Implementation Plan

## Pre-Plan: Codebase Inventory

The following files were read and their patterns analyzed to inform this plan:

**Core infrastructure (reused as-is):**
- `/Users/jana/workspace/terrarium/terrarium/core/engine.py` -- BaseEngine with lifecycle hooks, bus integration
- `/Users/jana/workspace/terrarium/terrarium/core/types.py` -- All typed IDs (ActorId, EntityId, etc.), enums (ActorType, BehaviorMode, StepVerdict)
- `/Users/jana/workspace/terrarium/terrarium/core/events.py` -- Event hierarchy (WorldEvent, AnimatorEvent, SimulationEvent, etc.)
- `/Users/jana/workspace/terrarium/terrarium/core/context.py` -- ActionContext (mutable pipeline input), StepResult, ResponseProposal
- `/Users/jana/workspace/terrarium/terrarium/core/protocols.py` -- All Protocol interfaces (EventBusProtocol, StateEngineProtocol, etc.)
- `/Users/jana/workspace/terrarium/terrarium/core/errors.py` -- TerrariumError hierarchy
- `/Users/jana/workspace/terrarium/terrarium/bus/bus.py` -- EventBus with persistence, fanout, wildcard subscriptions
- `/Users/jana/workspace/terrarium/terrarium/ledger/entries.py` -- LedgerEntry hierarchy (PipelineStepEntry, LLMCallEntry, etc.)
- `/Users/jana/workspace/terrarium/terrarium/pipeline/dag.py` -- PipelineDAG executor with step recording
- `/Users/jana/workspace/terrarium/terrarium/llm/router.py` -- LLMRouter with engine_name + use_case routing
- `/Users/jana/workspace/terrarium/terrarium/llm/types.py` -- LLMRequest, LLMResponse, LLMUsage

**Actor system (extended by this plan):**
- `/Users/jana/workspace/terrarium/terrarium/actors/definition.py` -- ActorDefinition (frozen Pydantic model)
- `/Users/jana/workspace/terrarium/terrarium/actors/registry.py` -- ActorRegistry (in-memory, indices by role/type/team)
- `/Users/jana/workspace/terrarium/terrarium/actors/personality.py` -- Personality, FrictionProfile
- `/Users/jana/workspace/terrarium/terrarium/actors/config.py` -- ActorConfig
- `/Users/jana/workspace/terrarium/terrarium/actors/simple_generator.py` -- SimpleActorGenerator (heuristic, no LLM)

**Engines (modified by this plan):**
- `/Users/jana/workspace/terrarium/terrarium/engines/animator/engine.py` -- WorldAnimatorEngine (current tick-based, generates all events including per-actor)
- `/Users/jana/workspace/terrarium/terrarium/engines/animator/context.py` -- AnimatorContext
- `/Users/jana/workspace/terrarium/terrarium/engines/animator/config.py` -- AnimatorConfig
- `/Users/jana/workspace/terrarium/terrarium/engines/world_compiler/engine.py` -- WorldCompilerEngine (generates entities + actors)
- `/Users/jana/workspace/terrarium/terrarium/engines/world_compiler/plan.py` -- WorldPlan (frozen)
- `/Users/jana/workspace/terrarium/terrarium/engines/world_compiler/generation_context.py` -- WorldGenerationContext

**Application layer (modified by this plan):**
- `/Users/jana/workspace/terrarium/terrarium/app.py` -- TerrariumApp (bootstrap, handle_action, configure_governance, configure_animator)
- `/Users/jana/workspace/terrarium/terrarium/registry/composition.py` -- create_default_registry (only place importing concrete engine classes)
- `/Users/jana/workspace/terrarium/terrarium/registry/wiring.py` -- wire_engines, inject_dependencies
- `/Users/jana/workspace/terrarium/terrarium/gateway/gateway.py` -- Gateway (protocol translation, tool routing)
- `/Users/jana/workspace/terrarium/terrarium/engines/adapter/protocols/mcp_server.py` -- MCPServerAdapter
- `/Users/jana/workspace/terrarium/terrarium/engines/adapter/protocols/http_rest.py` -- HTTPRestAdapter

**Config and persistence:**
- `/Users/jana/workspace/terrarium/terrarium/config/schema.py` -- TerrariumConfig (assembles all subsystem configs)
- `/Users/jana/workspace/terrarium/terrarium/persistence/manager.py` -- ConnectionManager
- `/Users/jana/workspace/terrarium/terrarium/persistence/database.py` -- Database ABC
- `/Users/jana/workspace/terrarium/terrarium/scheduling/scheduler.py` -- WorldScheduler

**Tests:**
- `/Users/jana/workspace/terrarium/tests/conftest.py` -- Shared fixtures (mock_event_bus, mock_ledger, make_action_context, etc.)
- `/Users/jana/workspace/terrarium/terrarium.toml` -- Base configuration

---

## Phase 1: Foundation Types (ActionEnvelope, ActionSource, WorldEvent.source)

### Purpose
Establish the universal action shape and source tracking that all subsequent phases depend on.

### File 1.1: Modify `/Users/jana/workspace/terrarium/terrarium/core/types.py`

**Add `ActionSource` enum** (after `WorldMode` around line 132):

```python
class ActionSource(enum.StrEnum):
    """Originator of an action in the simulation."""
    EXTERNAL = "external"      # user's agent via MCP/HTTP
    INTERNAL = "internal"      # internal actor via AgencyEngine
    ENVIRONMENT = "environment"  # world event via Animator
```

**Add `EnvelopeId` NewType** (after `ProfileVersion` around line 52):

```python
EnvelopeId = NewType("EnvelopeId", str)
"""Unique identifier for an ActionEnvelope."""
```

**Add `EnvelopePriority` enum** (after `ActionSource`):

```python
class EnvelopePriority(enum.IntEnum):
    """Priority for tie-breaking in EventQueue. Lower = higher priority."""
    ENVIRONMENT = 0   # environment events first (world state changes)
    EXTERNAL = 1      # external agent actions next
    INTERNAL = 2      # internal actor actions last
```

### File 1.2: Create `/Users/jana/workspace/terrarium/terrarium/core/envelope.py`

```python
"""ActionEnvelope -- universal action shape for all actions in the world.

Every action (external agent, internal actor, environment) is wrapped in
an ActionEnvelope before entering the EventQueue.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from terrarium.core.types import (
    ActorId,
    ActionSource,
    EnvelopeId,
    EnvelopePriority,
    EventId,
    ServiceId,
)


def _generate_envelope_id() -> EnvelopeId:
    return EnvelopeId(f"env-{uuid.uuid4().hex[:12]}")


class ActionEnvelope(BaseModel, frozen=True):
    """Universal action shape. Every action in the world is an ActionEnvelope."""

    envelope_id: EnvelopeId = Field(default_factory=_generate_envelope_id)
    actor_id: ActorId
    source: ActionSource
    action_type: str                           # service-specific action name
    target_service: ServiceId | None = None    # which service (None for meta-actions)
    payload: dict[str, Any] = Field(default_factory=dict)
    logical_time: float = 0.0                  # ordering key
    priority: EnvelopePriority = EnvelopePriority.INTERNAL
    parent_event_ids: list[EventId] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### File 1.3: Modify `/Users/jana/workspace/terrarium/terrarium/core/events.py`

**Add `source` field to `WorldEvent`** (after `causes` field, around line 106):

```python
source: ActionSource | None = None  # "external" / "internal" / "environment"
```

This requires importing `ActionSource` from `terrarium.core.types`.

### File 1.4: Modify `/Users/jana/workspace/terrarium/terrarium/core/__init__.py`

Add exports for the new types:

```python
from terrarium.core.types import ActionSource, EnvelopeId, EnvelopePriority
from terrarium.core.envelope import ActionEnvelope
```

And add them to `__all__`.

### File 1.5: Modify `/Users/jana/workspace/terrarium/terrarium/core/context.py`

**Add `source` and `envelope_id` fields to `ActionContext`** (after `run_id`, around line 143):

```python
source: ActionSource | None = None
envelope_id: str | None = None
```

This allows the pipeline to know the origin of the action being processed.

### Tests for Phase 1

Create `/Users/jana/workspace/terrarium/tests/core/test_envelope.py`:
- `test_envelope_creation` -- default values, frozen immutability
- `test_envelope_id_generation` -- unique IDs
- `test_action_source_enum` -- all three values
- `test_envelope_priority_ordering` -- ENVIRONMENT < EXTERNAL < INTERNAL
- `test_envelope_with_parent_events` -- causal chain tracking

---

## Phase 2: ActorState + Persistence + Registry Updates

### Purpose
Create the per-actor mutable runtime state model, its persistence layer, and behavioral trait extraction used for tier classification.

### File 2.1: Create `/Users/jana/workspace/terrarium/terrarium/actors/state.py`

```python
"""Persistent runtime state for internal actors.

ActorState is mutable (unlike ActorDefinition which is frozen).
Updated deterministically after each committed event.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from terrarium.core.types import ActorId, EntityId


class WaitingFor(BaseModel, frozen=True):
    """Describes what an actor is waiting for."""
    description: str
    since: float              # logical_time when waiting started
    patience: float           # duration before frustration increases
    escalation_action: str | None = None


class ScheduledAction(BaseModel, frozen=True):
    """An action scheduled for a future logical time."""
    logical_time: float
    action_type: str
    description: str
    target_service: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ActorBehaviorTraits(BaseModel, frozen=True):
    """Normalized behavioral traits extracted from persona at compile time.

    These structured fields are used for tier classification routing.
    The persona dict remains freeform for LLM prompt realism.
    """
    cooperation_level: float = 0.5    # 0.0=hostile, 1.0=fully cooperative
    deception_risk: float = 0.0       # 0.0=honest, 1.0=highly deceptive
    authority_level: float = 0.0      # 0.0=no authority, 1.0=full authority
    stakes_level: float = 0.3         # 0.0=trivial, 1.0=critical
    ambient_activity_rate: float = 0.1  # 0.0=never initiates, 1.0=constantly active


class ActorState(BaseModel):
    """Persistent mutable state for an internal actor.

    This is NOT frozen -- it is updated deterministically during simulation.
    One ActorState per internal actor, managed by AgencyEngine.
    """
    actor_id: ActorId
    role: str
    actor_type: str = "internal"   # "external" | "internal"

    # Identity (generated at compile time, immutable during run)
    persona: dict[str, Any] = Field(default_factory=dict)
    behavior_traits: ActorBehaviorTraits = Field(default_factory=ActorBehaviorTraits)

    # Goal (v1: single active goal)
    current_goal: str | None = None
    goal_strategy: str | None = None

    # Reactive state (updated during simulation)
    waiting_for: WaitingFor | None = None
    frustration: float = 0.0        # 0.0 - 1.0
    urgency: float = 0.3            # 0.0 - 1.0

    # Memory
    pending_notifications: list[str] = Field(default_factory=list)
    recent_interactions: list[str] = Field(default_factory=list)

    # Scheduling
    scheduled_action: ScheduledAction | None = None

    # Activation
    activation_tier: int = 0         # 0, 1, 2, or 3
    watched_entities: list[EntityId] = Field(default_factory=list)

    # Configuration
    max_recent_interactions: int = 20
```

### File 2.2: Create `/Users/jana/workspace/terrarium/terrarium/actors/state_store.py`

```python
"""SQLite-backed persistence for ActorState.

Uses the persistence module (Database ABC). Stores serialized ActorState
as JSON in an actor_states table. Provides batch load/save for efficiency.
"""
from __future__ import annotations

import json
from typing import Any

from terrarium.core.types import ActorId
from terrarium.persistence.database import Database
from terrarium.actors.state import ActorState


class ActorStateStore:
    """Persistent store for ActorState instances."""

    TABLE = "actor_states"

    def __init__(self, db: Database) -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create the actor_states table if it does not exist."""
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                actor_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def save(self, state: ActorState) -> None:
        """Upsert a single ActorState."""
        await self._db.execute(
            f"""INSERT OR REPLACE INTO {self.TABLE}
                (actor_id, role, state_json, updated_at)
                VALUES (?, ?, ?, datetime('now'))""",
            (str(state.actor_id), state.role, state.model_dump_json()),
        )

    async def save_batch(self, states: list[ActorState]) -> None:
        """Upsert multiple ActorStates in a single transaction."""
        async with self._db.transaction():
            await self._db.executemany(
                f"""INSERT OR REPLACE INTO {self.TABLE}
                    (actor_id, role, state_json, updated_at)
                    VALUES (?, ?, ?, datetime('now'))""",
                [
                    (str(s.actor_id), s.role, s.model_dump_json())
                    for s in states
                ],
            )

    async def load(self, actor_id: ActorId) -> ActorState | None:
        """Load a single ActorState by ID."""
        row = await self._db.fetchone(
            f"SELECT state_json FROM {self.TABLE} WHERE actor_id = ?",
            (str(actor_id),),
        )
        if row is None:
            return None
        return ActorState.model_validate_json(row["state_json"])

    async def load_all(self) -> list[ActorState]:
        """Load all ActorStates."""
        rows = await self._db.fetchall(
            f"SELECT state_json FROM {self.TABLE}"
        )
        return [ActorState.model_validate_json(r["state_json"]) for r in rows]

    async def load_by_role(self, role: str) -> list[ActorState]:
        """Load all ActorStates with a given role."""
        rows = await self._db.fetchall(
            f"SELECT state_json FROM {self.TABLE} WHERE role = ?",
            (role,),
        )
        return [ActorState.model_validate_json(r["state_json"]) for r in rows]

    async def delete(self, actor_id: ActorId) -> None:
        """Delete an ActorState."""
        await self._db.execute(
            f"DELETE FROM {self.TABLE} WHERE actor_id = ?",
            (str(actor_id),),
        )
```

### File 2.3: Modify `/Users/jana/workspace/terrarium/terrarium/actors/__init__.py`

Add exports:
```python
from terrarium.actors.state import ActorBehaviorTraits, ActorState, ScheduledAction, WaitingFor
from terrarium.actors.state_store import ActorStateStore
```

### File 2.4: Create `/Users/jana/workspace/terrarium/terrarium/actors/trait_extractor.py`

```python
"""Extract ActorBehaviorTraits from ActorDefinition persona and friction_profile.

Pure deterministic logic -- no LLM. Maps existing ActorDefinition fields
to the normalized structured traits used for tier 2/3 routing.
"""
from __future__ import annotations

from terrarium.actors.definition import ActorDefinition
from terrarium.actors.state import ActorBehaviorTraits


def extract_behavior_traits(actor_def: ActorDefinition) -> ActorBehaviorTraits:
    """Extract normalized traits from an ActorDefinition.

    Mapping rules:
    - cooperation_level: inverse of friction intensity (no friction = 1.0)
    - deception_risk: from friction_profile.category == "deceptive" or "hostile"
    - authority_level: from role-based heuristic + permissions
    - stakes_level: from friction intensity + role
    - ambient_activity_rate: from personality.traits or default
    """
    cooperation = 1.0
    deception = 0.0
    authority = 0.0
    stakes = 0.3
    ambient = 0.1

    fp = actor_def.friction_profile
    if fp is not None:
        cooperation = max(0.0, 1.0 - fp.intensity / 100.0)
        if fp.category == "deceptive":
            deception = fp.intensity / 100.0
        elif fp.category == "hostile":
            deception = min(1.0, fp.intensity / 100.0 * 0.7)
        stakes = max(stakes, fp.intensity / 100.0)

    # Authority from permissions
    perms = actor_def.permissions
    if perms.get("approve") or perms.get("escalate") or perms.get("admin"):
        authority = 0.8
    if perms.get("write") == "all":
        authority = max(authority, 0.5)

    # Ambient activity from personality traits
    personality = actor_def.personality
    if personality and personality.traits:
        ambient = personality.traits.get("ambient_activity_rate", ambient)

    return ActorBehaviorTraits(
        cooperation_level=cooperation,
        deception_risk=deception,
        authority_level=authority,
        stakes_level=stakes,
        ambient_activity_rate=ambient,
    )
```

### Tests for Phase 2

Create `/Users/jana/workspace/terrarium/tests/actors/test_state.py`:
- `test_actor_state_creation` -- defaults, mutable fields
- `test_waiting_for_frozen` -- WaitingFor is frozen
- `test_scheduled_action_frozen`
- `test_behavior_traits_defaults`
- `test_actor_state_serialization_roundtrip`

Create `/Users/jana/workspace/terrarium/tests/actors/test_state_store.py`:
- `test_save_and_load` -- round trip through SQLite
- `test_save_batch` -- multiple states at once
- `test_load_by_role`
- `test_load_nonexistent_returns_none`
- `test_upsert_overwrites`

Create `/Users/jana/workspace/terrarium/tests/actors/test_trait_extractor.py`:
- `test_default_actor_cooperative`
- `test_hostile_friction_sets_low_cooperation`
- `test_deceptive_friction_sets_deception_risk`
- `test_admin_permissions_set_authority`
- `test_ambient_from_personality_traits`

---

## Phase 3: EventQueue + SimulationRunner

### Purpose
Create the priority queue that orders all actions by logical time, and the SimulationRunner that drives the main simulation loop.

### File 3.1: Create `/Users/jana/workspace/terrarium/terrarium/simulation/event_queue.py`

```python
"""EventQueue -- priority queue ordering all actions by logical time.

The single entry point for all actions in the world. External agents,
AgencyEngine, and Animator all submit ActionEnvelopes here.

Tie-breaking: (logical_time, priority, actor_id, envelope_id)
"""
from __future__ import annotations

import heapq
import logging
from typing import Any

from terrarium.core.envelope import ActionEnvelope
from terrarium.core.types import EnvelopePriority

logger = logging.getLogger(__name__)


class EventQueue:
    """Priority queue with logical time ordering for all world actions."""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, str, str, ActionEnvelope]] = []
        self._current_time: float = 0.0
        self._counter: int = 0  # monotonic insertion counter for stable sort

    def submit(self, envelope: ActionEnvelope) -> None:
        """Add an action to the queue for immediate processing."""
        entry = (
            envelope.logical_time,
            envelope.priority.value,
            str(envelope.actor_id),
            str(envelope.envelope_id),
            envelope,
        )
        heapq.heappush(self._heap, entry)
        self._counter += 1

    def schedule(self, envelope: ActionEnvelope, delay: float) -> None:
        """Schedule an action for future logical time."""
        future_time = self._current_time + delay
        updated = envelope.model_copy(update={"logical_time": future_time})
        self.submit(updated)

    def pop_next(self) -> ActionEnvelope | None:
        """Dequeue the next envelope (lowest logical_time). Returns None if empty."""
        if not self._heap:
            return None
        _, _, _, _, envelope = heapq.heappop(self._heap)
        self._current_time = max(self._current_time, envelope.logical_time)
        return envelope

    def has_pending(self) -> bool:
        """Check if queue has actions to process."""
        return len(self._heap) > 0

    def peek_time(self) -> float | None:
        """Return the logical_time of the next envelope without popping."""
        if not self._heap:
            return None
        return self._heap[0][0]

    @property
    def current_time(self) -> float:
        """Current logical time (advances as events are processed)."""
        return self._current_time

    @current_time.setter
    def current_time(self, value: float) -> None:
        self._current_time = value

    @property
    def size(self) -> int:
        """Number of envelopes in the queue."""
        return len(self._heap)
```

### File 3.2: Create `/Users/jana/workspace/terrarium/terrarium/simulation/config.py`

```python
"""Configuration for the simulation runner and event queue."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SimulationRunnerConfig(BaseModel):
    """Config for SimulationRunner safety rails and limits."""
    model_config = ConfigDict(frozen=True)

    # End conditions
    max_logical_time: float = 86400.0     # 24h of simulated time
    max_total_events: int = 10000         # hard cap on total events processed
    stop_on_empty_queue: bool = True      # stop when queue + scheduled are empty

    # Runaway loop protection
    max_envelopes_per_event: int = 20     # max envelopes AgencyEngine + Animator can submit from one committed event
    max_actions_per_actor_per_window: int = 5  # max actions from one actor in a 60s logical-time window
    max_environment_reactions_per_window: int = 10  # max animator reactions in a 60s window
    loop_breaker_threshold: int = 50      # consecutive events without external input triggers pause

    # Tick interval (how often to check scheduled events)
    tick_interval_seconds: float = 60.0

    # Agent slot binding
    max_external_agents: int = 10
    slot_claim_timeout_seconds: float = 300.0
```

### File 3.3: Create `/Users/jana/workspace/terrarium/terrarium/simulation/runner.py`

```python
"""SimulationRunner -- drives the main simulation loop.

Coordinates EventQueue processing, Animator scheduled checks,
AgencyEngine scheduled checks, external agent input, and
simulation end conditions.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from terrarium.core.envelope import ActionEnvelope
from terrarium.core.events import WorldEvent
from terrarium.core.types import ActionSource, ActorId, EnvelopePriority, EventId, ServiceId
from terrarium.simulation.config import SimulationRunnerConfig
from terrarium.simulation.event_queue import EventQueue

logger = logging.getLogger(__name__)


class SimulationStatus(StrEnum):
    """Simulation lifecycle status."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"


class StopReason(StrEnum):
    """Why the simulation stopped."""
    ALL_AGENTS_DISCONNECTED = "all_agents_disconnected"
    ALL_BUDGETS_EXHAUSTED = "all_budgets_exhausted"
    MISSION_COMPLETED = "mission_completed"
    MANUAL_STOP = "manual_stop"
    MAX_TIME_REACHED = "max_time_reached"
    QUEUE_EMPTY = "queue_empty"
    MAX_EVENTS_REACHED = "max_events_reached"
    LOOP_BREAKER = "loop_breaker"


class SimulationRunner:
    """Drives the simulation loop.

    Dependencies (injected, not imported):
    - event_queue: EventQueue
    - pipeline_executor: callable(ActionEnvelope) -> WorldEvent | None
    - agency_engine: AgencyEngineProtocol (notify, check_scheduled)
    - animator: AnimatorProtocol (notify, check_scheduled_events)
    - config: SimulationRunnerConfig
    """

    def __init__(
        self,
        event_queue: EventQueue,
        pipeline_executor: Any,  # async callable(ActionEnvelope) -> WorldEvent | None
        agency_engine: Any | None = None,  # AgencyEngineProtocol
        animator: Any | None = None,       # AnimatorProtocol
        budget_checker: Any | None = None, # async callable() -> bool (all exhausted?)
        config: SimulationRunnerConfig | None = None,
        ledger: Any | None = None,
    ) -> None:
        self._queue = event_queue
        self._execute_pipeline = pipeline_executor
        self._agency = agency_engine
        self._animator = animator
        self._budget_checker = budget_checker
        self._config = config or SimulationRunnerConfig()
        self._ledger = ledger

        self._status = SimulationStatus.IDLE
        self._stop_reason: StopReason | None = None
        self._total_events_processed: int = 0
        self._events_since_external: int = 0
        self._connected_agents: set[ActorId] = set()
        self._mission: str | None = None
        self._mission_completed: bool = False

        # Runaway protection tracking
        self._actor_action_counts: dict[str, list[float]] = {}  # actor_id -> [logical_times]
        self._env_reaction_times: list[float] = []

    @property
    def status(self) -> SimulationStatus:
        return self._status

    @property
    def stop_reason(self) -> StopReason | None:
        return self._stop_reason

    @property
    def total_events_processed(self) -> int:
        return self._total_events_processed

    def set_mission(self, mission: str) -> None:
        """Set the mission text for mission-complete detection."""
        self._mission = mission

    def connect_agent(self, actor_id: ActorId) -> None:
        """Register an external agent connection."""
        self._connected_agents.add(actor_id)

    def disconnect_agent(self, actor_id: ActorId) -> None:
        """Unregister an external agent connection."""
        self._connected_agents.discard(actor_id)

    def mark_mission_completed(self) -> None:
        """Mark the mission as completed (external signal)."""
        self._mission_completed = True

    async def stop(self) -> None:
        """Manual stop."""
        self._stop_reason = StopReason.MANUAL_STOP
        self._status = SimulationStatus.STOPPED

    async def run(self) -> StopReason:
        """Run the main simulation loop until an end condition is met.

        Loop:
        1. Check end conditions
        2. Animator checks for due environment events -> submit envelopes
        3. AgencyEngine checks for due scheduled actor actions -> submit envelopes
        4. Dequeue next envelope -> pipeline -> commit
        5. Notify AgencyEngine and Animator of committed event
        6. Update actor states
        7. Record to ReplayLog
        8. Repeat
        """
        self._status = SimulationStatus.RUNNING
        self._stop_reason = None

        while self._status == SimulationStatus.RUNNING:
            # Step 1: Check end conditions
            reason = self._check_end_conditions()
            if reason is not None:
                self._stop_reason = reason
                self._status = SimulationStatus.COMPLETED
                break

            # Step 2: Animator scheduled events
            if self._animator is not None:
                animator_envelopes = await self._animator.check_scheduled_events(
                    self._queue.current_time
                )
                for env in (animator_envelopes or []):
                    self._queue.submit(env)

            # Step 3: AgencyEngine scheduled actions
            if self._agency is not None:
                agency_envelopes = await self._agency.check_scheduled_actions(
                    self._queue.current_time
                )
                for env in (agency_envelopes or []):
                    self._queue.submit(env)

            # Step 4: Process next envelope
            envelope = self._queue.pop_next()
            if envelope is None:
                # Queue is empty -- yield control briefly, then re-check
                await asyncio.sleep(0.01)
                continue

            # Runaway protection
            if not self._check_runaway_limits(envelope):
                logger.warning(
                    "Runaway protection: dropping envelope %s from %s",
                    envelope.envelope_id, envelope.actor_id,
                )
                continue

            # Execute through pipeline
            committed_event = await self._execute_pipeline(envelope)
            if committed_event is None:
                continue  # Pipeline rejected (short-circuited)

            self._total_events_processed += 1

            # Track external vs internal for loop breaker
            if envelope.source == ActionSource.EXTERNAL:
                self._events_since_external = 0
            else:
                self._events_since_external += 1

            # Step 5: Notify AgencyEngine
            if self._agency is not None:
                response_envelopes = await self._agency.notify(committed_event)
                count = 0
                for env in (response_envelopes or []):
                    if count >= self._config.max_envelopes_per_event:
                        break
                    self._queue.submit(env)
                    count += 1

            # Step 6: Notify Animator
            if self._animator is not None:
                env_envelopes = await self._animator.notify_event(committed_event)
                count = 0
                for env in (env_envelopes or []):
                    if count >= self._config.max_envelopes_per_event:
                        break
                    self._queue.submit(env)
                    count += 1

        return self._stop_reason

    def _check_end_conditions(self) -> StopReason | None:
        """Check all 6 simulation end conditions plus safety limits."""
        # 1. Manual stop already requested
        if self._status == SimulationStatus.STOPPED:
            return StopReason.MANUAL_STOP

        # 2. Max total events
        if self._total_events_processed >= self._config.max_total_events:
            return StopReason.MAX_EVENTS_REACHED

        # 3. Max logical time
        if self._queue.current_time >= self._config.max_logical_time:
            return StopReason.MAX_TIME_REACHED

        # 4. All external agents disconnected (only if some were connected)
        if self._connected_agents is not None and len(self._connected_agents) == 0:
            # Only trigger if agents were expected (at least one connected at some point)
            pass  # Checked elsewhere after agents have had chance to connect

        # 5. Mission completed
        if self._mission_completed:
            return StopReason.MISSION_COMPLETED

        # 6. Queue empty and no scheduled future events
        if self._config.stop_on_empty_queue and not self._queue.has_pending():
            has_scheduled = False
            if self._agency is not None:
                has_scheduled = has_scheduled or getattr(self._agency, 'has_scheduled_actions', lambda: False)()
            if self._animator is not None:
                has_scheduled = has_scheduled or getattr(self._animator, 'has_scheduled_events', lambda: False)()
            if not has_scheduled:
                return StopReason.QUEUE_EMPTY

        # 7. Loop breaker
        if self._events_since_external >= self._config.loop_breaker_threshold:
            return StopReason.LOOP_BREAKER

        return None

    def _check_runaway_limits(self, envelope: ActionEnvelope) -> bool:
        """Return True if envelope passes runaway limits, False to drop it."""
        current_time = self._queue.current_time
        window = 60.0  # 60-second logical-time window

        actor_key = str(envelope.actor_id)
        if envelope.source == ActionSource.INTERNAL:
            times = self._actor_action_counts.setdefault(actor_key, [])
            times = [t for t in times if current_time - t < window]
            times.append(current_time)
            self._actor_action_counts[actor_key] = times
            if len(times) > self._config.max_actions_per_actor_per_window:
                return False

        if envelope.source == ActionSource.ENVIRONMENT:
            self._env_reaction_times = [
                t for t in self._env_reaction_times if current_time - t < window
            ]
            self._env_reaction_times.append(current_time)
            if len(self._env_reaction_times) > self._config.max_environment_reactions_per_window:
                return False

        return True
```

### File 3.4: Create `/Users/jana/workspace/terrarium/terrarium/simulation/__init__.py`

```python
"""Simulation runner and event queue for Terrarium."""
from terrarium.simulation.config import SimulationRunnerConfig
from terrarium.simulation.event_queue import EventQueue
from terrarium.simulation.runner import SimulationRunner, SimulationStatus, StopReason

__all__ = [
    "EventQueue",
    "SimulationRunner",
    "SimulationRunnerConfig",
    "SimulationStatus",
    "StopReason",
]
```

### Tests for Phase 3

Create `/Users/jana/workspace/terrarium/tests/simulation/test_event_queue.py`:
- `test_submit_and_pop` -- FIFO for same time
- `test_ordering_by_logical_time`
- `test_tie_breaking_by_priority` -- ENVIRONMENT < EXTERNAL < INTERNAL
- `test_tie_breaking_by_actor_id` -- deterministic string ordering
- `test_schedule_with_delay`
- `test_has_pending`
- `test_current_time_advances`
- `test_peek_time`

Create `/Users/jana/workspace/terrarium/tests/simulation/test_runner.py`:
- `test_empty_queue_stops` -- StopReason.QUEUE_EMPTY
- `test_max_events_stops`
- `test_max_time_stops`
- `test_manual_stop`
- `test_loop_breaker_triggers`
- `test_runaway_actor_protection`
- `test_runaway_environment_protection`
- `test_mission_completed_stops`
- `test_basic_loop_processes_envelope` -- mock pipeline executor

---

## Phase 4: AgencyEngine + ActorPromptBuilder + WorldContextBundle

### Purpose
Create the core engine that gives internal actors autonomous behavior.

### File 4.1: Create `/Users/jana/workspace/terrarium/terrarium/engines/agency/config.py`

```python
"""Configuration for the AgencyEngine."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgencyConfig(BaseModel):
    """Config for the AgencyEngine."""
    model_config = ConfigDict(frozen=True)

    # Tier classification thresholds
    frustration_threshold_tier3: float = 0.7
    high_stakes_roles: list[str] = Field(default_factory=list)

    # Batch settings
    batch_size: int = 5

    # Patience / frustration
    frustration_increase_per_patience: float = 0.1
    frustration_decrease_per_positive: float = 0.1
    default_patience: float = 300.0  # 5 minutes logical time

    # Actor state update
    max_recent_interactions: int = 20
    max_pending_notifications: int = 50

    # LLM routing
    llm_use_case_individual: str = "agency_individual"
    llm_use_case_batch: str = "agency_batch"
```

### File 4.2: Create `/Users/jana/workspace/terrarium/terrarium/simulation/world_context.py`

```python
"""WorldContextBundle -- frozen runtime context reused by all Agency/Animator LLM calls.

Created ONCE at compile time. Contains everything the LLM needs to understand
the world: description, reality dimensions, behavior mode, governance rules,
available services + schemas.

This is NOT re-generated per actor. Per-actor context is added by ActorPromptBuilder.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorldContextBundle(BaseModel, frozen=True):
    """Canonical world prompt/context bundle.

    Created once during compilation. Reused by ActorPromptBuilder and
    Animator for all LLM calls. Contains the shared world system prompt.
    """
    world_description: str = ""
    reality_summary: str = ""
    reality_dimensions: dict[str, Any] = Field(default_factory=dict)
    behavior_mode: str = "dynamic"
    behavior_description: str = ""
    governance_rules_summary: str = ""
    available_services: list[dict[str, Any]] = Field(default_factory=list)
    mission: str = ""

    def to_system_prompt(self) -> str:
        """Render the world context as an LLM system prompt string."""
        sections = [
            f"## World\n{self.world_description}",
            f"## Reality\n{self.reality_summary}",
            f"## Behavior Mode\n{self.behavior_mode}: {self.behavior_description}",
        ]
        if self.governance_rules_summary:
            sections.append(f"## Governance Rules\n{self.governance_rules_summary}")
        if self.mission:
            sections.append(f"## Mission\n{self.mission}")
        if self.available_services:
            svc_lines = []
            for svc in self.available_services:
                name = svc.get("name", "unknown")
                actions = svc.get("actions", [])
                svc_lines.append(f"- {name}: {', '.join(a.get('name', '?') for a in actions)}")
            sections.append(f"## Available Services\n" + "\n".join(svc_lines))
        return "\n\n".join(sections)
```

### File 4.3: Create `/Users/jana/workspace/terrarium/terrarium/engines/agency/prompt_builder.py`

```python
"""ActorPromptBuilder -- assembles per-actor LLM prompts.

Domain-agnostic. Combines actor-specific context (persona, state, trigger)
with the shared WorldContextBundle system prompt. Supports both individual
and batch prompt formats.
"""
from __future__ import annotations

import json
from typing import Any

from terrarium.actors.state import ActorState
from terrarium.core.events import WorldEvent
from terrarium.simulation.world_context import WorldContextBundle


# Output schema for action generation
ACTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string", "description": "The action to take (or 'do_nothing')"},
        "target_service": {"type": ["string", "null"], "description": "Service to target"},
        "payload": {"type": "object", "description": "Action parameters"},
        "reasoning": {"type": "string", "description": "Brief reasoning for this action"},
        "state_updates": {
            "type": "object",
            "properties": {
                "frustration_delta": {"type": "number"},
                "urgency": {"type": "number"},
                "new_goal": {"type": ["string", "null"]},
                "goal_strategy": {"type": ["string", "null"]},
                "schedule_action": {"type": ["object", "null"]},
            },
        },
    },
    "required": ["action_type", "reasoning"],
}

BATCH_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "actor_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "actor_id": {"type": "string"},
                    "action_type": {"type": "string"},
                    "target_service": {"type": ["string", "null"]},
                    "payload": {"type": "object"},
                    "reasoning": {"type": "string"},
                    "state_updates": {"type": "object"},
                },
                "required": ["actor_id", "action_type", "reasoning"],
            },
        },
    },
    "required": ["actor_actions"],
}


class ActorPromptBuilder:
    """Builds LLM prompts for actor action generation."""

    def __init__(self, world_context: WorldContextBundle) -> None:
        self._world_context = world_context

    def build_system_prompt(self) -> str:
        """Return the shared world system prompt (layers 1-2)."""
        return self._world_context.to_system_prompt()

    def build_individual_prompt(
        self,
        actor: ActorState,
        trigger_event: WorldEvent | None,
        activation_reason: str,
        available_actions: list[dict[str, Any]],
    ) -> str:
        """Build per-actor user prompt (layers 3-4).

        Structure:
        - Actor identity (persona, role)
        - Current state (goal, waiting_for, frustration, recent interactions)
        - Trigger (what just happened)
        - Available actions
        - Output schema
        """
        sections: list[str] = []

        # Actor identity
        sections.append(f"## You are: {actor.role} (ID: {actor.actor_id})")
        if actor.persona:
            sections.append(f"### Persona\n{json.dumps(actor.persona, indent=2)}")

        # Current state
        state_lines = [
            f"- Goal: {actor.current_goal or 'None'}",
            f"- Strategy: {actor.goal_strategy or 'None'}",
            f"- Frustration: {actor.frustration:.2f}",
            f"- Urgency: {actor.urgency:.2f}",
        ]
        if actor.waiting_for:
            state_lines.append(
                f"- Waiting for: {actor.waiting_for.description} "
                f"(since t={actor.waiting_for.since:.1f}, patience={actor.waiting_for.patience:.1f})"
            )
        if actor.pending_notifications:
            state_lines.append(f"- Pending notifications: {len(actor.pending_notifications)}")
            for notif in actor.pending_notifications[-5:]:  # last 5
                state_lines.append(f"  - {notif}")
        if actor.recent_interactions:
            state_lines.append(f"- Recent interactions ({len(actor.recent_interactions)}):")
            for interaction in actor.recent_interactions[-5:]:
                state_lines.append(f"  - {interaction}")
        sections.append("### Current State\n" + "\n".join(state_lines))

        # Trigger
        sections.append(f"### Activation Reason: {activation_reason}")
        if trigger_event:
            trigger_info = {
                "event_type": trigger_event.event_type,
                "actor_id": str(trigger_event.actor_id),
                "action": trigger_event.action,
                "service": str(trigger_event.service_id),
            }
            if trigger_event.post_state:
                trigger_info["result"] = trigger_event.post_state
            sections.append(f"### Trigger Event\n{json.dumps(trigger_info, indent=2)}")

        # Available actions
        if available_actions:
            action_lines = []
            for action in available_actions:
                name = action.get("name", "?")
                desc = action.get("description", "")
                action_lines.append(f"- {name}: {desc}")
            sections.append("### Available Actions\n" + "\n".join(action_lines))

        # Output instruction
        sections.append(
            "### Instructions\n"
            "Choose ONE action or 'do_nothing'. Respond with JSON matching the output schema.\n"
            f"Output schema: {json.dumps(ACTION_OUTPUT_SCHEMA, indent=2)}"
        )

        return "\n\n".join(sections)

    def build_batch_prompt(
        self,
        actors_with_triggers: list[tuple[ActorState, WorldEvent | None, str]],
        available_actions: list[dict[str, Any]],
    ) -> str:
        """Build batch prompt for multiple actors in one LLM call.

        Each actor gets a summary section. The LLM generates actions for all.
        """
        sections: list[str] = []
        sections.append(
            "## Batch Action Generation\n"
            "Generate actions for each of the following actors. "
            "Each actor may choose 'do_nothing' if they have no reason to act."
        )

        for actor, trigger, reason in actors_with_triggers:
            actor_section = [
                f"### Actor: {actor.role} (ID: {actor.actor_id})",
                f"- Goal: {actor.current_goal or 'None'}",
                f"- Frustration: {actor.frustration:.2f}",
                f"- Activation reason: {reason}",
            ]
            if actor.persona:
                persona_brief = str(actor.persona)[:200]
                actor_section.append(f"- Persona: {persona_brief}")
            if trigger:
                actor_section.append(
                    f"- Trigger: {trigger.event_type} by {trigger.actor_id} -> {trigger.action}"
                )
            sections.append("\n".join(actor_section))

        if available_actions:
            action_lines = [f"- {a.get('name', '?')}: {a.get('description', '')}" for a in available_actions]
            sections.append("### Available Actions\n" + "\n".join(action_lines))

        sections.append(
            f"### Output Schema\n{json.dumps(BATCH_OUTPUT_SCHEMA, indent=2)}"
        )

        return "\n\n".join(sections)
```

### File 4.4: Create `/Users/jana/workspace/terrarium/terrarium/engines/agency/engine.py`

```python
"""AgencyEngine -- manages internal actor lifecycle.

Only active when the world has internal actors. Handles:
- Event-first activation (which actors should act after each committed event)
- Tiered action generation (Tier 1 check -> Tier 2 batch -> Tier 3 individual)
- Deterministic state updates after committed events
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, ClassVar

from terrarium.core.engine import BaseEngine
from terrarium.core.envelope import ActionEnvelope
from terrarium.core.events import Event, WorldEvent
from terrarium.core.types import (
    ActionSource,
    ActorId,
    EnvelopePriority,
    EnvelopeId,
    EventId,
    ServiceId,
)
from terrarium.actors.state import ActorState, ScheduledAction, WaitingFor
from terrarium.engines.agency.config import AgencyConfig
from terrarium.engines.agency.prompt_builder import ActorPromptBuilder
from terrarium.simulation.world_context import WorldContextBundle

logger = logging.getLogger(__name__)


class AgencyEngine(BaseEngine):
    """Manages internal actor lifecycle: activation, action generation, state updates."""

    engine_name: ClassVar[str] = "agency"
    subscriptions: ClassVar[list[str]] = ["world", "simulation"]
    dependencies: ClassVar[list[str]] = ["state"]

    async def _on_initialize(self) -> None:
        self._typed_config = AgencyConfig(
            **{k: v for k, v in self._config.items() if not k.startswith("_")}
        )
        self._actor_states: dict[ActorId, ActorState] = {}
        self._prompt_builder: ActorPromptBuilder | None = None
        self._world_context: WorldContextBundle | None = None
        self._llm_router: Any = None
        self._state_store: Any = None
        self._available_actions: list[dict[str, Any]] = []

    async def configure(
        self,
        actor_states: list[ActorState],
        world_context: WorldContextBundle,
        available_actions: list[dict[str, Any]] | None = None,
    ) -> None:
        """Configure after world compilation.

        Args:
            actor_states: Initial ActorState for each internal actor.
            world_context: The frozen WorldContextBundle.
            available_actions: Service actions available to actors.
        """
        self._actor_states = {s.actor_id: s for s in actor_states}
        self._world_context = world_context
        self._prompt_builder = ActorPromptBuilder(world_context)
        self._available_actions = available_actions or []
        self._llm_router = self._config.get("_llm_router")

        logger.info(
            "AgencyEngine configured: %d internal actors",
            len(self._actor_states),
        )

    async def _handle_event(self, event: Event) -> None:
        """Handle bus events (for tracking, not for activation)."""
        pass

    # -- Activation (called by SimulationRunner) --

    async def notify(self, committed_event: WorldEvent) -> list[ActionEnvelope]:
        """Called after every committed event. Returns envelopes for activated actors.

        Tier 1: deterministic check -- find affected actors (no LLM)
        Classify into Tier 2 (batch) or Tier 3 (individual)
        Generate actions via LLM
        Return ActionEnvelopes for EventQueue
        """
        if not self._actor_states:
            return []

        # Tier 1: deterministic activation check
        activated = self._tier1_activation_check(committed_event)
        if not activated:
            return []

        # Update pending notifications for all actors affected
        for actor_id, reason in activated:
            actor = self._actor_states.get(actor_id)
            if actor:
                notif = f"[t={committed_event.timestamp.tick}] {committed_event.event_type}: {committed_event.action} by {committed_event.actor_id}"
                actor.pending_notifications.append(notif)
                if len(actor.pending_notifications) > self._typed_config.max_pending_notifications:
                    actor.pending_notifications = actor.pending_notifications[-self._typed_config.max_pending_notifications:]

        # Classify into Tier 2 (batch) and Tier 3 (individual)
        tier2_actors: list[tuple[ActorState, str]] = []
        tier3_actors: list[tuple[ActorState, str]] = []

        for actor_id, reason in activated:
            actor = self._actor_states.get(actor_id)
            if actor is None:
                continue
            tier = self._classify_tier(actor, reason)
            if tier == 3:
                tier3_actors.append((actor, reason))
            else:
                tier2_actors.append((actor, reason))

        envelopes: list[ActionEnvelope] = []

        # Tier 3: individual LLM calls
        for actor, reason in tier3_actors:
            env = await self._activate_individual(actor, reason, committed_event)
            if env is not None:
                envelopes.append(env)

        # Tier 2: batch LLM call
        if tier2_actors:
            batch_envs = await self._activate_batch(tier2_actors, committed_event)
            envelopes.extend(batch_envs)

        return envelopes

    async def check_scheduled_actions(self, current_time: float) -> list[ActionEnvelope]:
        """Check for actors with scheduled actions that are due."""
        envelopes: list[ActionEnvelope] = []
        for actor in self._actor_states.values():
            if actor.scheduled_action and actor.scheduled_action.logical_time <= current_time:
                sa = actor.scheduled_action
                env = ActionEnvelope(
                    actor_id=actor.actor_id,
                    source=ActionSource.INTERNAL,
                    action_type=sa.action_type,
                    target_service=ServiceId(sa.target_service) if sa.target_service else None,
                    payload=sa.payload,
                    logical_time=current_time,
                    priority=EnvelopePriority.INTERNAL,
                    metadata={"activation_reason": "scheduled", "scheduled_description": sa.description},
                )
                envelopes.append(env)
                actor.scheduled_action = None
        return envelopes

    def has_scheduled_actions(self) -> bool:
        """Return True if any actor has a scheduled action."""
        return any(a.scheduled_action is not None for a in self._actor_states.values())

    # -- Tier 1: Deterministic activation check --

    def _tier1_activation_check(
        self, event: WorldEvent
    ) -> list[tuple[ActorId, str]]:
        """Determine which actors should activate. Pure Python, no LLM.

        Triggers:
        1. Event-affected: committed event touched an entity this actor watches
        2. Scheduled: actor's scheduled_action.logical_time has arrived
        3. Wait-threshold: actor's waiting_for patience has expired
        4. Frustration-threshold: actor's frustration crossed escalation threshold
        """
        activated: list[tuple[ActorId, str]] = []

        target = event.target_entity
        event_time = event.timestamp.tick  # use tick as proxy for logical time

        for actor_id, actor in self._actor_states.items():
            # Skip the actor that generated this event
            if str(actor_id) == str(event.actor_id):
                continue

            # 1. Event-affected: watched entity touched
            if target and str(target) in [str(e) for e in actor.watched_entities]:
                activated.append((actor_id, "event_affected"))
                continue

            # 2. Wait-threshold: patience expired
            if actor.waiting_for:
                elapsed = event_time - actor.waiting_for.since
                if elapsed >= actor.waiting_for.patience:
                    activated.append((actor_id, "wait_threshold"))
                    continue

            # 3. Frustration-threshold
            if actor.frustration >= self._typed_config.frustration_threshold_tier3:
                activated.append((actor_id, "frustration_threshold"))
                continue

        return activated

    # -- Tier classification --

    def _classify_tier(self, actor: ActorState, reason: str) -> int:
        """Classify an activated actor as Tier 2 (batch) or Tier 3 (individual).

        Rules (from spec):
        - frustration > threshold -> Tier 3
        - role in high_stakes_roles -> Tier 3
        - deception_risk > 0.5 -> Tier 3
        - reason == "threshold_crossed" or "frustration_threshold" -> Tier 3
        - else -> Tier 2
        """
        if actor.frustration > self._typed_config.frustration_threshold_tier3:
            return 3
        if actor.role in self._typed_config.high_stakes_roles:
            return 3
        if actor.behavior_traits.deception_risk > 0.5:
            return 3
        if actor.behavior_traits.authority_level > 0.7:
            return 3
        if reason in ("frustration_threshold", "wait_threshold"):
            return 3
        return 2

    # -- Tier 3: Individual LLM --

    async def _activate_individual(
        self,
        actor: ActorState,
        reason: str,
        trigger_event: WorldEvent,
    ) -> ActionEnvelope | None:
        """Generate action for a single actor via individual LLM call."""
        if not self._llm_router or not self._prompt_builder:
            return None

        system_prompt = self._prompt_builder.build_system_prompt()
        user_prompt = self._prompt_builder.build_individual_prompt(
            actor=actor,
            trigger_event=trigger_event,
            activation_reason=reason,
            available_actions=self._available_actions,
        )

        from terrarium.llm.types import LLMRequest
        request = LLMRequest(
            system_prompt=system_prompt,
            user_content=user_prompt,
            output_schema=None,  # We parse JSON from text
            temperature=0.7,
        )
        response = await self._llm_router.route(
            request, "agency", self._typed_config.llm_use_case_individual,
        )

        return self._parse_llm_action(actor, response.content, reason, trigger_event)

    # -- Tier 2: Batch LLM --

    async def _activate_batch(
        self,
        actors_with_reasons: list[tuple[ActorState, str]],
        trigger_event: WorldEvent,
    ) -> list[ActionEnvelope]:
        """Batch-generate actions for multiple actors in one LLM call."""
        if not self._llm_router or not self._prompt_builder:
            return []

        # Group into batches of batch_size
        batches: list[list[tuple[ActorState, str]]] = []
        for i in range(0, len(actors_with_reasons), self._typed_config.batch_size):
            batches.append(actors_with_reasons[i:i + self._typed_config.batch_size])

        envelopes: list[ActionEnvelope] = []
        for batch in batches:
            actors_triggers = [
                (actor, trigger_event, reason)
                for actor, reason in batch
            ]
            system_prompt = self._prompt_builder.build_system_prompt()
            user_prompt = self._prompt_builder.build_batch_prompt(
                actors_with_triggers=actors_triggers,
                available_actions=self._available_actions,
            )

            from terrarium.llm.types import LLMRequest
            request = LLMRequest(
                system_prompt=system_prompt,
                user_content=user_prompt,
                temperature=0.7,
            )
            response = await self._llm_router.route(
                request, "agency", self._typed_config.llm_use_case_batch,
            )

            batch_envs = self._parse_batch_response(batch, response.content, trigger_event)
            envelopes.extend(batch_envs)

        return envelopes

    # -- Response parsing --

    def _parse_llm_action(
        self,
        actor: ActorState,
        raw_output: str,
        reason: str,
        trigger_event: WorldEvent,
    ) -> ActionEnvelope | None:
        """Parse LLM output into ActionEnvelope. Returns None for do_nothing."""
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM output for actor %s", actor.actor_id)
            return None

        action_type = data.get("action_type", "do_nothing")
        if action_type == "do_nothing":
            return None

        # Apply state updates from LLM
        state_updates = data.get("state_updates", {})
        self._apply_state_updates(actor, state_updates)

        return ActionEnvelope(
            actor_id=actor.actor_id,
            source=ActionSource.INTERNAL,
            action_type=action_type,
            target_service=ServiceId(data["target_service"]) if data.get("target_service") else None,
            payload=data.get("payload", {}),
            logical_time=self._get_current_time(),
            priority=EnvelopePriority.INTERNAL,
            parent_event_ids=[trigger_event.event_id],
            metadata={
                "activation_reason": reason,
                "activation_tier": 3,
                "reasoning": data.get("reasoning", ""),
            },
        )

    def _parse_batch_response(
        self,
        batch: list[tuple[ActorState, str]],
        raw_output: str,
        trigger_event: WorldEvent,
    ) -> list[ActionEnvelope]:
        """Parse batch LLM output into per-actor ActionEnvelopes."""
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            logger.warning("Failed to parse batch LLM output")
            return []

        actor_map = {str(a.actor_id): (a, r) for a, r in batch}
        envelopes: list[ActionEnvelope] = []

        for action_data in data.get("actor_actions", []):
            actor_id_str = action_data.get("actor_id", "")
            if actor_id_str not in actor_map:
                continue
            actor, reason = actor_map[actor_id_str]

            action_type = action_data.get("action_type", "do_nothing")
            if action_type == "do_nothing":
                continue

            state_updates = action_data.get("state_updates", {})
            self._apply_state_updates(actor, state_updates)

            envelopes.append(ActionEnvelope(
                actor_id=actor.actor_id,
                source=ActionSource.INTERNAL,
                action_type=action_type,
                target_service=ServiceId(action_data["target_service"]) if action_data.get("target_service") else None,
                payload=action_data.get("payload", {}),
                logical_time=self._get_current_time(),
                priority=EnvelopePriority.INTERNAL,
                parent_event_ids=[trigger_event.event_id],
                metadata={
                    "activation_reason": reason,
                    "activation_tier": 2,
                    "reasoning": action_data.get("reasoning", ""),
                },
            ))

        return envelopes

    # -- Deterministic state updates (Gap 4) --

    def update_actor_state(self, actor: ActorState, committed_event: WorldEvent) -> None:
        """Update actor's reactive state after a committed event. Deterministic, no LLM.

        Rules:
        - Frustration: +0.1 per patience window exceeded, -0.1 per positive event
        - WaitingFor: set when actor submits action needing response, cleared on response
        - Recent interactions: append summary, keep last max_recent_interactions
        - Pending notifications: cleared when actor activates, new events added between activations
        - Scheduled action: cleared when executed, can be set by LLM response
        """
        # Frustration update
        if actor.waiting_for:
            elapsed = committed_event.timestamp.tick - actor.waiting_for.since
            if elapsed >= actor.waiting_for.patience:
                actor.frustration = min(1.0, actor.frustration + self._typed_config.frustration_increase_per_patience)

        # Check if this event resolves what the actor was waiting for
        if actor.waiting_for and str(committed_event.actor_id) != str(actor.actor_id):
            # Simple heuristic: if the event mentions this actor or their watched entity
            if str(actor.actor_id) in str(committed_event.input_data) or (
                committed_event.target_entity and str(committed_event.target_entity) in [str(e) for e in actor.watched_entities]
            ):
                actor.waiting_for = None
                actor.frustration = max(0.0, actor.frustration - self._typed_config.frustration_decrease_per_positive)

        # Recent interactions
        summary = f"[t={committed_event.timestamp.tick}] {committed_event.action} by {committed_event.actor_id}"
        actor.recent_interactions.append(summary)
        if len(actor.recent_interactions) > self._typed_config.max_recent_interactions:
            actor.recent_interactions = actor.recent_interactions[-self._typed_config.max_recent_interactions:]

    def _apply_state_updates(self, actor: ActorState, updates: dict[str, Any]) -> None:
        """Apply LLM-suggested state updates to actor (within safe bounds)."""
        if "frustration_delta" in updates:
            delta = float(updates["frustration_delta"])
            actor.frustration = max(0.0, min(1.0, actor.frustration + delta))
        if "urgency" in updates:
            actor.urgency = max(0.0, min(1.0, float(updates["urgency"])))
        if "new_goal" in updates and updates["new_goal"]:
            actor.current_goal = str(updates["new_goal"])
        if "goal_strategy" in updates and updates["goal_strategy"]:
            actor.goal_strategy = str(updates["goal_strategy"])
        if "schedule_action" in updates and updates["schedule_action"]:
            sa = updates["schedule_action"]
            actor.scheduled_action = ScheduledAction(
                logical_time=float(sa.get("logical_time", self._get_current_time() + 60)),
                action_type=str(sa.get("action_type", "check_status")),
                description=str(sa.get("description", "")),
                target_service=sa.get("target_service"),
                payload=sa.get("payload", {}),
            )

    def _get_current_time(self) -> float:
        """Get current logical time from the event queue (or 0 if not wired)."""
        return 0.0  # Overridden when wired to EventQueue

    # -- Public accessors --

    def get_actor_state(self, actor_id: ActorId) -> ActorState | None:
        return self._actor_states.get(actor_id)

    def get_all_states(self) -> list[ActorState]:
        return list(self._actor_states.values())
```

### File 4.5: Create `/Users/jana/workspace/terrarium/terrarium/engines/agency/__init__.py`

```python
"""AgencyEngine -- makes internal actors autonomous."""
from terrarium.engines.agency.config import AgencyConfig
from terrarium.engines.agency.engine import AgencyEngine
from terrarium.engines.agency.prompt_builder import ActorPromptBuilder

__all__ = ["AgencyConfig", "AgencyEngine", "ActorPromptBuilder"]
```

### Tests for Phase 4

Create `/Users/jana/workspace/terrarium/tests/engines/agency/test_engine.py`:
- `test_tier1_activation_event_affected` -- actor watching entity gets activated
- `test_tier1_activation_wait_threshold`
- `test_tier1_activation_frustration_threshold`
- `test_tier1_no_self_activation` -- actor doesn't activate from own event
- `test_classify_tier2_routine`
- `test_classify_tier3_high_frustration`
- `test_classify_tier3_high_stakes_role`
- `test_classify_tier3_deception_risk`
- `test_update_actor_state_frustration_increase`
- `test_update_actor_state_frustration_decrease`
- `test_update_actor_state_waiting_cleared`
- `test_update_actor_state_recent_interactions_capped`
- `test_no_activation_with_zero_actors`

Create `/Users/jana/workspace/terrarium/tests/engines/agency/test_prompt_builder.py`:
- `test_individual_prompt_structure`
- `test_batch_prompt_structure`
- `test_system_prompt_from_world_context`

---

## Phase 5: Wiring (Animator Refactor, Gateway, App, Composition Root)

### Purpose
Wire the new AgencyEngine into the existing system. Refactor Animator to environment-only. Update Gateway for multi-agent.

### File 5.1: Modify `/Users/jana/workspace/terrarium/terrarium/registry/composition.py`

Add AgencyEngine import and registration:

```python
from terrarium.engines.agency.engine import AgencyEngine
# ... in create_default_registry():
registry.register(AgencyEngine())
```

### File 5.2: Modify `/Users/jana/workspace/terrarium/terrarium/config/schema.py`

Add imports and fields:

```python
from terrarium.engines.agency.config import AgencyConfig
from terrarium.simulation.config import SimulationRunnerConfig

# In TerrariumConfig:
agency: AgencyConfig = Field(default_factory=AgencyConfig)
simulation_runner: SimulationRunnerConfig = Field(default_factory=SimulationRunnerConfig)
```

### File 5.3: Modify `/Users/jana/workspace/terrarium/terrarium.toml`

Add new sections:

```toml
# -- Agency Engine --
[agency]
frustration_threshold_tier3 = 0.7
batch_size = 5
max_recent_interactions = 20

# -- Simulation Runner --
[simulation_runner]
max_logical_time = 86400.0
max_total_events = 10000
max_envelopes_per_event = 20
max_actions_per_actor_per_window = 5
loop_breaker_threshold = 50

# -- LLM Routing for Agency --
[llm.routing.agency_individual]
provider = "codex_acp"
model = ""
max_tokens = 4096
temperature = 0.7

[llm.routing.agency_batch]
provider = "codex_acp"
model = ""
max_tokens = 8192
temperature = 0.7
```

### File 5.4: Modify `/Users/jana/workspace/terrarium/terrarium/app.py`

Add to `_inject_cross_engine_deps()`:

```python
# Agency engine wiring
agency = self._registry.get("agency")
agency._config["_llm_router"] = self._llm_router
agency._config["_actor_registry"] = actor_registry
```

Add new method `configure_agency()`:

```python
async def configure_agency(self, plan: Any, result: dict) -> None:
    """Configure the AgencyEngine from compilation results.

    Creates ActorState for each internal actor, builds WorldContextBundle,
    extracts available actions from service packs.
    """
    from terrarium.actors.state import ActorState
    from terrarium.actors.trait_extractor import extract_behavior_traits
    from terrarium.simulation.world_context import WorldContextBundle
    from terrarium.engines.world_compiler.generation_context import WorldGenerationContext

    agency = self._registry.get("agency")
    actors = result.get("actors", [])

    # Build WorldContextBundle
    gen_ctx = WorldGenerationContext(plan)
    ctx_vars = gen_ctx.for_entity_generation()

    # Gather available actions from service packs
    available_actions = []
    responder = self._registry.get("responder")
    if hasattr(responder, "_pack_registry"):
        for tool_info in responder._pack_registry.list_tools():
            available_actions.append({
                "name": tool_info.get("name", ""),
                "description": tool_info.get("description", ""),
                "service": tool_info.get("pack_name", ""),
            })

    world_context = WorldContextBundle(
        world_description=plan.description,
        reality_summary=ctx_vars.get("reality_summary", ""),
        behavior_mode=plan.behavior,
        behavior_description=ctx_vars.get("behavior_description", ""),
        governance_rules_summary=ctx_vars.get("policies_summary", ""),
        mission=plan.mission,
        available_services=available_actions,
    )

    # Create ActorState for each internal actor
    actor_states = []
    for actor_def in actors:
        if str(actor_def.type) in ("human", "system"):
            # Internal actors get ActorState
            traits = extract_behavior_traits(actor_def)
            state = ActorState(
                actor_id=actor_def.id,
                role=actor_def.role,
                actor_type="internal",
                persona=actor_def.personality.model_dump() if actor_def.personality else {},
                behavior_traits=traits,
                current_goal=actor_def.metadata.get("goal"),
                goal_strategy=actor_def.metadata.get("goal_strategy"),
            )
            actor_states.append(state)

    await agency.configure(actor_states, world_context, available_actions)
```

Update `compile_and_run()` to call `configure_agency()`:

```python
async def compile_and_run(self, plan: Any) -> dict:
    compiler = self._registry.get("world_compiler")
    result = await compiler.generate_world(plan)
    self.configure_governance(plan)
    await self.configure_animator(plan)
    await self.configure_agency(plan, result)
    return result
```

### File 5.5: Modify `/Users/jana/workspace/terrarium/terrarium/engines/animator/engine.py`

Refactor to produce `ActionEnvelope` with `source=ActionSource.ENVIRONMENT` and add `notify_event()` method. The key changes:

1. Add `notify_event(committed_event: WorldEvent) -> list[ActionEnvelope]` method that generates environment reaction envelopes
2. Add `check_scheduled_events(current_time: float) -> list[ActionEnvelope]` method
3. Add `has_scheduled_events() -> bool` method
4. Modify `_execute_event()` to return `ActionEnvelope` instead of executing through app directly (that is now SimulationRunner's job)

### File 5.6: Add `AgencyEngineProtocol` to `/Users/jana/workspace/terrarium/terrarium/core/protocols.py`

```python
@runtime_checkable
class AgencyEngineProtocol(Protocol):
    """Interface for the internal actor management engine."""

    async def notify(self, committed_event: Event) -> list[Any]:
        """Called after every committed event. Returns ActionEnvelopes."""
        ...

    async def check_scheduled_actions(self, current_time: float) -> list[Any]:
        """Check for actors with scheduled actions that are due."""
        ...

    def has_scheduled_actions(self) -> bool:
        """Return True if any actor has a scheduled action."""
        ...
```

### Tests for Phase 5

Create `/Users/jana/workspace/terrarium/tests/engines/agency/test_wiring.py`:
- `test_agency_engine_in_registry` -- composition root includes it
- `test_agency_engine_receives_config`
- `test_agency_engine_lifecycle` -- initialize, start, stop

---

## Phase 6: External Agent Slot Binding (Gap 3)

### Purpose
Enable multiple external agents to connect via MCP/HTTP, each claiming an actor slot.

### File 6.1: Create `/Users/jana/workspace/terrarium/terrarium/simulation/slot_manager.py`

```python
"""External agent slot binding manager.

Rules:
- Each external agent claims a slot by actor_id at connection time
- If two agents try to claim the same slot, the second is rejected
- Permissions/capabilities come from the ActorDefinition in that slot
- Reconnect resumes the same slot (matched by actor_id)
"""
from __future__ import annotations

import logging
from typing import Any

from terrarium.core.errors import TerrariumError
from terrarium.core.types import ActorId

logger = logging.getLogger(__name__)


class SlotAlreadyClaimedError(TerrariumError):
    """Raised when an agent tries to claim a slot that is already occupied."""
    pass


class SlotNotFoundError(TerrariumError):
    """Raised when an agent tries to claim a slot that doesn't exist."""
    pass


class AgentSlot:
    """Represents a slot an external agent can occupy."""

    def __init__(self, actor_id: ActorId, role: str, permissions: dict[str, Any]) -> None:
        self.actor_id = actor_id
        self.role = role
        self.permissions = permissions
        self.claimed_by: str | None = None  # connection/session ID
        self.connected: bool = False

    def claim(self, connection_id: str) -> None:
        if self.claimed_by is not None and self.claimed_by != connection_id:
            raise SlotAlreadyClaimedError(
                f"Slot {self.actor_id} already claimed by {self.claimed_by}",
                context={"actor_id": str(self.actor_id), "existing_connection": self.claimed_by},
            )
        self.claimed_by = connection_id
        self.connected = True

    def release(self) -> None:
        self.connected = False
        # Do NOT clear claimed_by -- allows reconnect with same connection_id

    def disconnect(self) -> None:
        self.connected = False
        self.claimed_by = None


class SlotManager:
    """Manages external agent slot binding."""

    def __init__(self) -> None:
        self._slots: dict[ActorId, AgentSlot] = {}

    def register_slot(self, actor_id: ActorId, role: str, permissions: dict[str, Any]) -> None:
        """Register a slot for an external agent (from world definition)."""
        self._slots[actor_id] = AgentSlot(actor_id, role, permissions)

    def claim_slot(self, actor_id: ActorId, connection_id: str) -> AgentSlot:
        """Claim a slot for an external agent.

        Raises SlotNotFoundError if no slot exists.
        Raises SlotAlreadyClaimedError if already claimed by another connection.
        """
        slot = self._slots.get(actor_id)
        if slot is None:
            raise SlotNotFoundError(
                f"No slot for actor_id={actor_id}",
                context={"actor_id": str(actor_id), "available": [str(s) for s in self._slots]},
            )
        slot.claim(connection_id)
        return slot

    def release_slot(self, actor_id: ActorId) -> None:
        """Release a slot (disconnect but allow reconnect)."""
        slot = self._slots.get(actor_id)
        if slot:
            slot.release()

    def disconnect_slot(self, actor_id: ActorId) -> None:
        """Fully disconnect a slot (no reconnect)."""
        slot = self._slots.get(actor_id)
        if slot:
            slot.disconnect()

    def get_connected_agents(self) -> list[ActorId]:
        """Return list of currently connected agent actor_ids."""
        return [s.actor_id for s in self._slots.values() if s.connected]

    def get_slot(self, actor_id: ActorId) -> AgentSlot | None:
        return self._slots.get(actor_id)

    def all_slots_empty(self) -> bool:
        """True if no slots are claimed."""
        return all(not s.connected for s in self._slots.values())

    @property
    def total_slots(self) -> int:
        return len(self._slots)
```

### File 6.2: Modify Gateway and MCP/HTTP adapters

The Gateway should use SlotManager. On connection:
1. Agent provides `actor_id` (or a default "mcp-agent"/"http-agent" is used)
2. Gateway calls `slot_manager.claim_slot(actor_id, connection_id)`
3. If successful, all subsequent requests use that actor_id's permissions
4. On disconnect, `slot_manager.release_slot(actor_id)`

The MCPServerAdapter's `_actor_id` field becomes dynamic via slot binding.

### Tests for Phase 6

Create `/Users/jana/workspace/terrarium/tests/simulation/test_slot_manager.py`:
- `test_register_and_claim_slot`
- `test_claim_already_claimed_raises`
- `test_reconnect_same_connection_succeeds`
- `test_release_allows_reconnect`
- `test_disconnect_clears_claim`
- `test_get_connected_agents`
- `test_claim_nonexistent_slot_raises`

---

## Phase 7: ReplayLog

### Purpose
Record all decisions for exact replay.

### File 7.1: Create `/Users/jana/workspace/terrarium/terrarium/simulation/replay.py`

```python
"""ReplayLog -- records all decisions for exact replay.

In record mode: saves every LLM prompt/output and pipeline result.
In replay mode: returns recorded LLM output instead of calling LLM.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from terrarium.core.envelope import ActionEnvelope
from terrarium.core.events import WorldEvent
from terrarium.persistence.database import Database


class ReplayEntry(BaseModel, frozen=True):
    """Records everything needed for exact replay of one action."""
    logical_time: float
    envelope: dict[str, Any]         # ActionEnvelope serialized
    activation_reason: str           # "event_affected" | "scheduled" | "threshold" | "external"
    activation_tier: int             # 0, 1, 2, or 3
    llm_prompt: str | None = None    # None for external agents and Tier 0/1
    llm_output: str | None = None    # None for external agents and Tier 0/1
    pipeline_result: dict[str, Any] = Field(default_factory=dict)
    actor_state_after: dict[str, Any] | None = None


class ReplayLog:
    """Records all decisions for exact replay."""

    def __init__(self, db: Database | None = None) -> None:
        self._db = db
        self._entries: list[ReplayEntry] = []  # in-memory fallback
        self._replay_mode: bool = False
        self._replay_index: dict[tuple[float, str], ReplayEntry] = {}

    async def initialize(self) -> None:
        """Create replay_log table if using database persistence."""
        if self._db:
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS replay_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    logical_time REAL NOT NULL,
                    actor_id TEXT NOT NULL,
                    entry_json TEXT NOT NULL
                )
            """)

    async def record(self, entry: ReplayEntry) -> None:
        """Record a replay entry."""
        self._entries.append(entry)
        if self._db:
            actor_id = entry.envelope.get("actor_id", "")
            await self._db.execute(
                "INSERT INTO replay_log (logical_time, actor_id, entry_json) VALUES (?, ?, ?)",
                (entry.logical_time, actor_id, entry.model_dump_json()),
            )

    def set_replay_mode(self, entries: list[ReplayEntry]) -> None:
        """Switch to replay mode with pre-loaded entries."""
        self._replay_mode = True
        self._replay_index = {
            (e.logical_time, e.envelope.get("actor_id", "")): e
            for e in entries
        }

    @property
    def replay_mode(self) -> bool:
        return self._replay_mode

    def get_recorded_output(self, logical_time: float, actor_id: str) -> str | None:
        """In replay mode, return the recorded LLM output."""
        entry = self._replay_index.get((logical_time, actor_id))
        if entry:
            return entry.llm_output
        return None

    def get_entries(self) -> list[ReplayEntry]:
        return list(self._entries)

    async def load_from_db(self) -> list[ReplayEntry]:
        """Load all entries from database."""
        if not self._db:
            return self._entries
        rows = await self._db.fetchall("SELECT entry_json FROM replay_log ORDER BY seq")
        return [ReplayEntry.model_validate_json(r["entry_json"]) for r in rows]
```

### Tests for Phase 7

Create `/Users/jana/workspace/terrarium/tests/simulation/test_replay.py`:
- `test_record_and_retrieve`
- `test_replay_mode_returns_recorded_output`
- `test_replay_mode_missing_returns_none`
- `test_entry_serialization_roundtrip`

---

## Phase 8: Compilation Updates (ActorState generation, trait extraction)

### Purpose
Modify the world compiler to produce ActorState objects with traits and goals during compilation.

### File 8.1: Modify world compiler's `generate_world()` in `/Users/jana/workspace/terrarium/terrarium/engines/world_compiler/engine.py`

After Step 4b (actor personality generation), add ActorState creation:

```python
# Step 4c: Create ActorState for internal actors
from terrarium.actors.state import ActorState
from terrarium.actors.trait_extractor import extract_behavior_traits

actor_states = []
for actor_def in actors:
    if str(actor_def.type) in ("human", "system"):
        traits = extract_behavior_traits(actor_def)
        state = ActorState(
            actor_id=actor_def.id,
            role=actor_def.role,
            actor_type="internal",
            persona=actor_def.personality.model_dump() if actor_def.personality else {},
            behavior_traits=traits,
            current_goal=actor_def.metadata.get("goal"),
            goal_strategy=actor_def.metadata.get("goal_strategy"),
        )
        actor_states.append(state)
```

Add `actor_states` to the result dict:

```python
result["actor_states"] = actor_states
```

### File 8.2: Extend the `ActorDefinition.metadata` convention

The world compiler's personality generator should populate `metadata.goal` and `metadata.goal_strategy` during generation. These are domain-agnostic goal strings that the AgencyEngine uses.

The YAML schema already supports arbitrary metadata per actor spec. The LLM prompt templates for personality generation should include instructions to generate goal and goal_strategy fields.

### File 8.3: Add `watched_entities` generation

During compilation, after entities are generated, the compiler should assign `watched_entities` to ActorStates based on domain heuristics. For example, in a support world, customers watch their own tickets. This mapping is generated by the LLM alongside actor states.

The ActorState's `watched_entities` field links actors to the State Engine entities they care about.

### Tests for Phase 8

Create `/Users/jana/workspace/terrarium/tests/engines/world_compiler/test_actor_state_generation.py`:
- `test_internal_actors_get_actor_state`
- `test_external_actors_do_not_get_actor_state`
- `test_behavior_traits_extracted_from_friction`
- `test_goal_from_metadata`

---

## Phase 9: Tests (Integration)

### File 9.1: Create `/Users/jana/workspace/terrarium/tests/integration/test_agency_integration.py`

End-to-end test:
1. Compile a small world (3 internal actors, 1 service)
2. Start SimulationRunner
3. Submit an external action
4. Verify AgencyEngine activates affected internal actors
5. Verify internal actor actions go through pipeline
6. Verify actor states are updated
7. Verify simulation ends on QUEUE_EMPTY

### File 9.2: Create `/Users/jana/workspace/terrarium/tests/integration/test_multi_agent.py`

1. Create world with 2 external agent slots
2. Claim both slots via SlotManager
3. Submit actions from both agents
4. Verify both go through pipeline with correct actor_ids
5. Verify slot rejection when third agent tries to claim occupied slot

### File 9.3: Update `/Users/jana/workspace/terrarium/tests/conftest.py`

Add fixtures:

```python
@pytest.fixture
def make_actor_state():
    """Factory for creating ActorState with defaults."""
    def _make(**kwargs):
        from terrarium.actors.state import ActorState
        defaults = {
            "actor_id": ActorId("test-actor"),
            "role": "customer",
        }
        defaults.update(kwargs)
        return ActorState(**defaults)
    return _make

@pytest.fixture
def make_action_envelope():
    """Factory for creating ActionEnvelope with defaults."""
    def _make(**kwargs):
        from terrarium.core.envelope import ActionEnvelope
        from terrarium.core.types import ActionSource
        defaults = {
            "actor_id": ActorId("test-actor"),
            "source": ActionSource.EXTERNAL,
            "action_type": "test_action",
        }
        defaults.update(kwargs)
        return ActionEnvelope(**defaults)
    return _make

@pytest.fixture
def world_context_bundle():
    """Minimal WorldContextBundle for testing."""
    from terrarium.simulation.world_context import WorldContextBundle
    return WorldContextBundle(
        world_description="A test world",
        reality_summary="Ideal conditions",
        behavior_mode="dynamic",
    )
```

---

## Phase 10: Verification and Post-Implementation

### 10.1: Run full test suite
```bash
uv run pytest --cov=terrarium --cov-report=term-missing
```

### 10.2: Type checking
```bash
uv run mypy terrarium/
```

### 10.3: Lint
```bash
uv run ruff check terrarium/ tests/
uv run ruff format --check terrarium/ tests/
```

### 10.4: Verify no cross-engine imports
The AgencyEngine must only import from `terrarium.core`, `terrarium.actors`, `terrarium.simulation`, and `terrarium.engines.agency`. It must never import from `terrarium.engines.state`, `terrarium.engines.policy`, etc.

### 10.5: Documentation updates
- Update `CLAUDE.md` to include AgencyEngine in the 10 engines table (now 11 engines)
- Add agency engine to the Architecture section
- Document the SimulationRunner in the "Simulation Loop" section

---

## Dependency Graph (Phase Ordering)

```
Phase 1 (Foundation types)
   |
   v
Phase 2 (ActorState + Persistence)
   |
   v
Phase 3 (EventQueue + SimulationRunner) -- depends on Phase 1
   |
   v
Phase 4 (AgencyEngine + PromptBuilder) -- depends on Phases 1, 2, 3
   |
   v
Phase 5 (Wiring) -- depends on Phases 1-4
   |
   +---> Phase 6 (Slot Binding) -- can be done in parallel with Phase 7
   +---> Phase 7 (ReplayLog) -- can be done in parallel with Phase 6
   |
   v
Phase 8 (Compilation Updates) -- depends on Phase 2
   |
   v
Phase 9 (Integration Tests) -- depends on all above
   |
   v
Phase 10 (Verification)
```

## Summary of All New Files

| File | Type | Phase |
|------|------|-------|
| `terrarium/core/envelope.py` | New | 1 |
| `terrarium/actors/state.py` | New | 2 |
| `terrarium/actors/state_store.py` | New | 2 |
| `terrarium/actors/trait_extractor.py` | New | 2 |
| `terrarium/simulation/__init__.py` | New | 3 |
| `terrarium/simulation/event_queue.py` | New | 3 |
| `terrarium/simulation/config.py` | New | 3 |
| `terrarium/simulation/runner.py` | New | 3 |
| `terrarium/simulation/world_context.py` | New | 4 |
| `terrarium/engines/agency/__init__.py` | New | 4 |
| `terrarium/engines/agency/config.py` | New | 4 |
| `terrarium/engines/agency/engine.py` | New | 4 |
| `terrarium/engines/agency/prompt_builder.py` | New | 4 |
| `terrarium/simulation/slot_manager.py` | New | 6 |
| `terrarium/simulation/replay.py` | New | 7 |

## Summary of All Modified Files

| File | Change | Phase |
|------|--------|-------|
| `terrarium/core/types.py` | Add ActionSource, EnvelopeId, EnvelopePriority | 1 |
| `terrarium/core/events.py` | Add source field to WorldEvent | 1 |
| `terrarium/core/context.py` | Add source, envelope_id fields | 1 |
| `terrarium/core/__init__.py` | Export new types | 1 |
| `terrarium/actors/__init__.py` | Export new state types | 2 |
| `terrarium/core/protocols.py` | Add AgencyEngineProtocol | 5 |
| `terrarium/registry/composition.py` | Register AgencyEngine | 5 |
| `terrarium/config/schema.py` | Add AgencyConfig, SimulationRunnerConfig | 5 |
| `terrarium.toml` | Add agency + simulation_runner sections | 5 |
| `terrarium/app.py` | Add configure_agency(), update compile_and_run() | 5 |
| `terrarium/engines/animator/engine.py` | Add notify_event(), check_scheduled_events(), has_scheduled_events() | 5 |
| `terrarium/gateway/gateway.py` | Integrate SlotManager | 6 |
| `terrarium/engines/adapter/protocols/mcp_server.py` | Dynamic actor_id via slot binding | 6 |
| `terrarium/engines/adapter/protocols/http_rest.py` | Dynamic actor_id via slot binding | 6 |
| `terrarium/engines/world_compiler/engine.py` | Generate ActorState during compilation | 8 |
| `tests/conftest.py` | Add make_actor_state, make_action_envelope, world_context_bundle | 9 |

---

### Critical Files for Implementation
- `/Users/jana/workspace/terrarium/terrarium/engines/agency/engine.py` - Core AgencyEngine: activation, tier classification, LLM action generation, deterministic state updates
- `/Users/jana/workspace/terrarium/terrarium/simulation/runner.py` - SimulationRunner: main loop, end conditions, runaway protection, coordinates all components
- `/Users/jana/workspace/terrarium/terrarium/core/envelope.py` - ActionEnvelope: universal action shape that all other components depend on
- `/Users/jana/workspace/terrarium/terrarium/actors/state.py` - ActorState + WaitingFor + ScheduledAction + ActorBehaviorTraits: the per-actor runtime state model
- `/Users/jana/workspace/terrarium/terrarium/app.py` - TerrariumApp: wiring point that connects AgencyEngine, SimulationRunner, and existing infrastructure