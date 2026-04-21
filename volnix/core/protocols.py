"""Protocol interfaces for the Volnix engine ecosystem.

Every engine, adapter, and subsystem in Volnix is coded against one of
the protocols defined here.  Using :func:`typing.runtime_checkable` protocols
lets consumers verify structural compatibility at runtime while keeping the
core module free of concrete implementations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from volnix.core.context import ActionContext, StepResult
from volnix.core.events import Event
from volnix.core.memory_types import (
    MemoryQuery,
    MemoryRecall,
    MemoryScope,
    MemoryWrite,
)
from volnix.core.types import (
    ActorId,
    BudgetState,
    EntityId,
    EventId,
    FidelityTier,
    MemoryRecordId,
    PolicyId,
    RunResult,
    ServiceId,
    SnapshotId,
    StateDelta,
    ToolName,
    WorldId,
)

# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------


@runtime_checkable
class EventBusProtocol(Protocol):
    """Interface for the event bus pub/sub system."""

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        ...

    async def subscribe(
        self,
        topic: str,
        callback: Any,
        queue_size: int = 1000,
    ) -> Any:
        """Subscribe to events on a given topic."""
        ...

    async def unsubscribe(self, event_type: str, callback: Any) -> None:
        """Remove a subscription by event type and callback reference."""
        ...


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@runtime_checkable
class PipelineStep(Protocol):
    """A single step in the governance pipeline."""

    @property
    def step_name(self) -> str:
        """Canonical name of this pipeline step."""
        ...

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the step, reading from and writing to *ctx*.

        Args:
            ctx: The mutable action context for the current request.

        Returns:
            A :class:`StepResult` describing the outcome.
        """
        ...


# ---------------------------------------------------------------------------
# State engine
# ---------------------------------------------------------------------------


@runtime_checkable
class StateEngineProtocol(Protocol):
    """Interface to the world-state store."""

    async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict[str, Any]:
        """Retrieve a single entity by type and identifier."""
        ...

    async def query_entities(
        self,
        entity_type: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query entities of a given type with optional filters."""
        ...

    async def list_entity_types(self) -> list[str]:
        """Return distinct entity types in the store."""
        ...

    async def propose_mutation(
        self,
        deltas: list[StateDelta],
    ) -> list[StateDelta]:
        """Validate proposed state mutations (dry run). Returns validated deltas."""
        ...

    async def commit_event(self, event: Event) -> EventId:
        """Persist an event and record its causal edges. Returns the event ID."""
        ...

    async def snapshot(self, label: str = "default", tick: int = 0) -> SnapshotId:
        """Create an immutable point-in-time snapshot of the entire world state.

        ``tick`` (PMF Plan Phase 4C Step 9) stamps the logical tick
        onto the ledger's ``SnapshotEntry`` so consumers can
        correlate snapshots with simulation time. Default ``0``
        preserves pre-Step-9 callers byte-identical.
        """
        ...

    async def fork(self, snapshot_id: SnapshotId) -> WorldId:
        """Fork a new world from an existing snapshot."""
        ...

    async def diff(
        self,
        snapshot_a: SnapshotId,
        snapshot_b: SnapshotId,
    ) -> list[StateDelta] | dict[str, Any]:
        """Compute the set of deltas between two snapshots."""
        ...

    async def get_causal_chain(self, event_id: EventId, direction: str = "backward") -> list[Event]:
        """Walk the causal ancestry or descendants of an event."""
        ...

    async def get_timeline(
        self,
        start: Any = None,
        end: Any = None,
        entity_id: EntityId | None = None,
    ) -> list[Event]:
        """Return the ordered event timeline, optionally filtered by entity."""
        ...

    async def get_trajectory(
        self,
        entity_id: EntityId,
        field_path: str,
        tick_range: tuple[int, int] | None = None,
    ) -> list[Any]:
        """Reconstruct a field's historical-value sequence on an
        entity from committed ``state_deltas`` (PMF Plan Phase 4C
        Step 9). Returns an ordered list of
        ``volnix.engines.state.trajectory.TrajectoryPoint`` values.

        Return type is ``list[Any]`` on the protocol surface to
        avoid pulling ``TrajectoryPoint`` into the ``core``
        layer (``core.protocols`` must stay free of engine
        imports). Consumers type-hint against the concrete class
        when they need the narrower type.
        """
        ...


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------


@runtime_checkable
class PolicyEngineProtocol(Protocol):
    """Interface for governance policy evaluation."""

    async def evaluate(self, ctx: ActionContext) -> StepResult:
        """Evaluate all active policies against the current action context."""
        ...

    async def get_active_policies(
        self,
        service_id: ServiceId | None = None,
    ) -> list[PolicyId]:
        """Return the identifiers of all currently active policies."""
        ...

    async def resolve_hold(
        self,
        hold_id: str,
        approved: bool,
        approver: ActorId,
        reason: str | None = None,
    ) -> Event:
        """Resolve a held action by approving or rejecting it."""
        ...


# ---------------------------------------------------------------------------
# Permission engine
# ---------------------------------------------------------------------------


@runtime_checkable
class PermissionEngineProtocol(Protocol):
    """Interface for RBAC / capability-based permission checks."""

    async def check_permission(
        self,
        actor_id: ActorId,
        action: str,
        target_entity: EntityId | None = None,
    ) -> StepResult:
        """Check whether *actor_id* is permitted to perform *action*."""
        ...

    async def get_visible_entities(
        self,
        actor_id: ActorId,
        entity_type: str | None = None,
    ) -> list[EntityId]:
        """Return entity IDs visible to the given actor.

        Returns empty list when no visibility rules exist — callers
        interpret this as "no filtering, return all entities."
        """
        ...

    async def has_visibility_rules(
        self,
        actor_id: ActorId,
        entity_type: str,
    ) -> bool:
        """Check if visibility rules exist for this actor and entity type."""
        ...

    async def get_actor_permissions(
        self,
        actor_id: ActorId,
    ) -> dict[str, Any]:
        """Return the full permission set for an actor."""
        ...


# ---------------------------------------------------------------------------
# Budget engine
# ---------------------------------------------------------------------------


@runtime_checkable
class BudgetEngineProtocol(Protocol):
    """Interface for resource-budget tracking and enforcement."""

    async def check_budget(self, ctx: ActionContext) -> StepResult:
        """Check whether the actor's budget allows the proposed action."""
        ...

    async def deduct(
        self,
        actor_id: ActorId,
        api_calls: int = 0,
        llm_spend_usd: float = 0.0,
        world_actions: int = 0,
        spend_usd: float = 0.0,
        time_seconds: float = 0.0,
    ) -> BudgetState:
        """Deduct resources from an actor's budget and return the new state."""
        ...

    async def get_remaining(self, actor_id: ActorId) -> BudgetState:
        """Return the actor's current remaining budget."""
        ...

    async def get_spend_curve(
        self,
        actor_id: ActorId,
    ) -> list[dict[str, Any]]:
        """Return a time-series of the actor's spend across budget dimensions."""
        ...

    async def refill(self, actor_id: ActorId, dimension: str, amount: int) -> None:
        """Refill a budget dimension (for per-round resource reset in games).

        Args:
            actor_id: The actor whose budget to refill.
            dimension: Budget dimension name (e.g. ``"api_calls"``, ``"world_actions"``).
            amount: How much to refill. Use ``-1`` for a full refill back to total.
        """
        ...


# ---------------------------------------------------------------------------
# Responder
# ---------------------------------------------------------------------------


@runtime_checkable
class ResponderProtocol(Protocol):
    """Interface for generating simulated service responses."""

    async def generate_response(self, ctx: ActionContext) -> StepResult:
        """Produce a :class:`ResponseProposal` and attach it to *ctx*."""
        ...


# ---------------------------------------------------------------------------
# Animator
# ---------------------------------------------------------------------------


@runtime_checkable
class AnimatorProtocol(Protocol):
    """Interface for NPC / environment autonomous-event generation."""

    async def generate_events(
        self,
        world_id: WorldId,
        tick: int,
    ) -> list[Event]:
        """Generate autonomous events for the current tick."""
        ...

    async def get_pending_scheduled(
        self,
        world_id: WorldId,
    ) -> list[Event]:
        """Return events that are scheduled but not yet emitted."""
        ...

    async def tick(self, world_id: WorldId) -> list[Event]:
        """Advance the animator by one logical tick."""
        ...


# ---------------------------------------------------------------------------
# Agency
# ---------------------------------------------------------------------------


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


@runtime_checkable
class AgencyActivationProtocol(Protocol):
    """Structural contract for activating an actor via the agency engine.

    Used by ``GameOrchestrator`` (Cycle B) to kickstart and re-activate
    game players without depending on the concrete :class:`AgencyEngine`
    class. Preserves the "no cross-engine imports" rule from
    DESIGN_PRINCIPLES.md — the composition root wires the concrete
    agency engine as a dependency that satisfies this Protocol.

    Concrete :class:`AgencyEngine` implements this by providing
    ``activate_for_event`` in Cycle B.7; the orchestrator never
    imports the concrete class.
    """

    async def activate_for_event(
        self,
        actor_id: Any,  # ActorId — Any to avoid circular import with core.types
        reason: str,
        trigger_event: Event | None = None,
        max_calls_override: int | None = None,
        max_read_calls: int | None = None,
        state_summary: str | None = None,
    ) -> list[Any]:
        """Activate an actor for one multi-turn tool-loop iteration.

        Args:
            actor_id: The actor to activate.
            reason: Activation reason string. One of
                ``"game_kickstart"``, ``"game_event"``,
                ``"subscription_match"``, ``"event_affected"``,
                ``"autonomous_tick"``. Drives prompt shape in the
                prompt builder.
            trigger_event: The committed world event that caused this
                activation, if any. ``None`` for kickstart.
            max_calls_override: Override the per-activation tool-call
                budget. ``None`` falls back to
                ``max_tool_calls_per_activation`` from global agency
                config.
            state_summary: Optional compact game-state summary string
                that the caller (orchestrator) injects as a fresh user
                message at the top of the agent's rolling conversation.
                Used for game re-activations so the LLM sees ground
                truth from state without replaying full history.

        Returns:
            List of ActionEnvelope objects produced during the
            activation. Typed as ``list[Any]`` in the Protocol to
            avoid forward-importing ActionEnvelope into core.
        """
        ...


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@runtime_checkable
class RunnerProtocol(Protocol):
    """Interface for CLI-compatible simulation and game runners.

    Both :class:`SimulationRunner` and :class:`OrchestratorRunner`
    satisfy this protocol, allowing the CLI to operate on runners
    without importing concrete engine classes.
    """

    async def run(self) -> RunResult:
        """Block until the run terminates and return a unified result."""
        ...

    def set_mission(self, mission: str) -> None:
        """Set the mission description (may be a no-op for game runners)."""
        ...


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


@runtime_checkable
class AdapterProtocol(Protocol):
    """Interface for translating between external tool calls and internal events."""

    async def translate_inbound(
        self,
        tool_name: ToolName,
        raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate an external tool invocation into canonical internal form."""
        ...

    async def translate_outbound(
        self,
        tool_name: ToolName,
        internal_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate an internal response back to the external tool format."""
        ...

    async def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return the manifest of all tools this adapter exposes."""
        ...


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


@runtime_checkable
class ReporterProtocol(Protocol):
    """Interface for generating evaluation reports and diagnostics."""

    async def generate_scorecard(
        self,
        run_id: str,
    ) -> dict[str, Any]:
        """Generate a summary scorecard for a completed run."""
        ...

    async def generate_gap_log(
        self,
        run_id: str,
    ) -> list[dict[str, Any]]:
        """Generate a log of all capability gaps encountered during a run."""
        ...

    async def generate_causal_trace(
        self,
        event_id: EventId,
    ) -> dict[str, Any]:
        """Generate a causal trace rooted at the given event."""
        ...

    async def generate_diff(
        self,
        snapshot_a: SnapshotId,
        snapshot_b: SnapshotId,
    ) -> dict[str, Any]:
        """Generate a human-readable diff between two snapshots."""
        ...

    async def generate_full_report(
        self,
        run_id: str,
    ) -> dict[str, Any]:
        """Generate a comprehensive report combining all diagnostics."""
        ...


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


@runtime_checkable
class FeedbackProtocol(Protocol):
    """Interface for annotation, promotion, and drift detection."""

    async def add_annotation(
        self,
        service_id: ServiceId,
        annotation_text: str,
        author: str,
    ) -> EventId:
        """Attach an annotation to a service."""
        ...

    async def get_annotations(
        self,
        service_id: ServiceId,
    ) -> list[dict[str, Any]]:
        """Retrieve all annotations for a service."""
        ...

    async def propose_promotion(
        self,
        service_id: ServiceId,
        from_tier: FidelityTier,
        to_tier: FidelityTier,
    ) -> EventId:
        """Propose a fidelity-tier change for a service."""
        ...

    async def check_external_drift(
        self,
        service_id: ServiceId,
    ) -> dict[str, Any]:
        """Check whether the real-world API has drifted from the profile."""
        ...


# ---------------------------------------------------------------------------
# World compiler
# ---------------------------------------------------------------------------


@runtime_checkable
class WorldCompilerProtocol(Protocol):
    """Interface for compiling world definitions from various sources."""

    async def compile_from_yaml(
        self,
        yaml_path: str,
    ) -> dict[str, Any]:
        """Compile a world definition from a YAML file."""
        ...

    async def compile_from_nl(
        self,
        description: str,
    ) -> dict[str, Any]:
        """Compile a world definition from a natural-language description."""
        ...

    async def resolve_service_schema(
        self,
        service_id: ServiceId,
    ) -> dict[str, Any]:
        """Resolve and return the schema for a given service."""
        ...

    async def generate_world_data(
        self,
        world_id: WorldId,
    ) -> dict[str, Any]:
        """Generate seed data for a new world instance."""
        ...


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------


@runtime_checkable
class GatewayProtocol(Protocol):
    """Interface for the external-facing request gateway."""

    async def handle_request(
        self,
        actor_id: ActorId,
        tool_name: ToolName,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle an inbound tool-call request from an actor."""
        ...

    async def deliver_observation(
        self,
        actor_id: ActorId,
        observation: dict[str, Any],
    ) -> None:
        """Push an observation event to an actor."""
        ...


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


@runtime_checkable
class LedgerProtocol(Protocol):
    """Interface for the append-only audit ledger.

    Records operational entries (pipeline steps, LLM calls, gateway requests, etc.)
    This is separate from the event bus — the bus carries domain events between engines,
    the ledger records what the system did for observability and audit.
    """

    async def append(self, entry: Any) -> int:
        """Append a ledger entry and return its sequence ID.

        Args:
            entry: A LedgerEntry subclass (PipelineStepEntry, LLMCallEntry, etc.)
        Returns:
            int: The auto-assigned sequence ID.
        """
        ...

    async def query(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        """Query ledger entries with optional filters.

        Args:
            filters: Optional filter criteria (entry_type, time range, actor, etc.)
            limit: Maximum entries to return.
            offset: Pagination offset.
        Returns:
            list: Matching ledger entries.
        """
        ...

    async def get_count(self, entry_type: str | None = None) -> int:
        """Return the total number of ledger entries.

        Args:
            entry_type: If provided, count only entries of this type.
        """
        ...


# ---------------------------------------------------------------------------
# Active-NPC protocols (Layer 1 of the PMF plan)
#
# These protocols are the inter-module contract for Active NPCs. Phase 2
# wires concrete implementations in the composition root; in Phase 1
# nothing depends on them yet, but their shape is locked here so
# downstream engines (reporter signal computers, etc.) can be developed
# against a stable interface.
# ---------------------------------------------------------------------------


@runtime_checkable
class ActivationProfileLoaderProtocol(Protocol):
    """Loader for :class:`volnix.actors.activation_profile.ActivationProfile`.

    Engines that need to resolve a profile-name string into a profile
    instance (for example, to read its ``state_schema`` or
    ``tool_scope``) depend on this protocol, never on the concrete
    loader module. The concrete implementation is wired in
    ``volnix/registry/composition.py``.
    """

    def load(self, name: str) -> Any:
        """Return the :class:`ActivationProfile` for ``name``.

        Raises:
            FileNotFoundError: If no profile with that name exists.
            ValueError: If the profile YAML fails validation.
        """
        ...

    def list_available(self) -> list[str]:
        """Return the list of profile names known to the registry."""
        ...


@runtime_checkable
class NPCHostProtocol(Protocol):
    """The surface an :class:`NPCActivatorProtocol` needs from its hosting
    engine (in practice, :class:`AgencyEngine`).

    This captures the intra-package coupling between NPCActivator and
    AgencyEngine explicitly. Both live in ``volnix/engines/agency/``
    and share tool-loop plumbing (LLM router, tool executor, pipeline
    lock, ledger, and the tool-call parser). The protocol exists so:

    1. Test stubs can't silently drift from what the real engine exposes.
    2. A future refactor of ``AgencyEngine`` private internals surfaces
       as a Protocol mismatch, not a silent NPC-path break.
    3. The coupling surface is documented in one place.

    Attribute names retain their leading underscore because these are
    the existing engine internals — the Protocol reflects reality, not
    an aspirational rewrite.
    """

    _llm_router: Any
    _tool_executor: Any
    _tool_definitions: list[Any]
    _available_actions: list[dict[str, Any]]
    _tool_name_map: dict[str, str]
    _llm_semaphore: Any  # asyncio.Semaphore — kept Any to avoid hard import
    _pipeline_lock: Any  # asyncio.Lock
    _typed_config: Any
    _ledger: Any  # LedgerProtocol-compatible; may be None in tests

    def _parse_tool_call(
        self,
        actor: Any,
        tool_call: Any,
        reason: str,
        trigger_event: Any,
    ) -> Any:
        """Parse a native LLM tool call into an ActionEnvelope.

        Returns ``None`` for the ``do_nothing`` sentinel; the caller is
        expected to handle that separately.
        """
        ...


@runtime_checkable
class NPCActivatorProtocol(Protocol):
    """Entry point for activating an Active NPC on a trigger event.

    The concrete implementation (``volnix/engines/agency/npc_activator.py``)
    reuses the hosting agency engine's tool-loop plumbing so that every
    NPC action flows through the same 7-step pipeline as agent actions.
    There is no NPC-specific fast path.
    """

    async def activate_npc(
        self,
        *,
        actor: Any,  # ActorState
        reason: str,
        trigger_event: Event | None,
        max_calls_override: int | None,
        host: NPCHostProtocol,
    ) -> list[Any]:
        """Activate the NPC and return any ActionEnvelopes produced.

        Args:
            actor: The NPC's mutable ActorState. Its
                ``activation_profile_name`` must be set — this contract
                is for Active NPCs only.
            reason: The activation reason (``"npc_exposure"``,
                ``"npc_word_of_mouth"``, etc.). Surfaced in the prompt
                and recorded in the ledger.
            trigger_event: The event that woke the NPC, if any.
            max_calls_override: Optional per-activation tool-call cap.
                ``None`` defers to the profile's ``budget_defaults``.
            host: The hosting engine, typed as :class:`NPCHostProtocol`.

        Returns:
            List of :class:`ActionEnvelope` objects that reached the
            pipeline during this activation. Matches the shape returned
            by :meth:`AgencyEngine._activate_with_tool_loop`.
        """
        ...


# ---------------------------------------------------------------------------
# Active-cohort protocol (PMF Plan Phase 4A — activation cycling)
#
# The ``CohortManager`` caps how many Active NPCs consume LLM cycles
# at any given tick; dormant NPCs either have events queued on them
# (``defer``) or get preempt-promoted (``promote``). Consumers depend
# on this protocol, never on the concrete class in
# ``volnix.actors.cohort_manager``. Only the composition root
# (``volnix/registry/composition.py``) imports the concrete class.
# ---------------------------------------------------------------------------


@runtime_checkable
class CohortManagerProtocol(Protocol):
    """Full interface used by AgencyEngine and app.py for activation cycling.

    Pure logic — no bus, no LLM, no async. Decisions are deterministic
    at a given seed + tick under single-loop asyncio (all methods are
    sync, so two coroutines calling into the manager run atomically
    with respect to each other).

    Review fix M5+D4: every method / property actually called by the
    engine or composition root is declared here. Earlier versions
    declared only 9 members — ``register``, ``active_ids``,
    ``registered_ids``, ``stats``, ``queue_depth`` were missing even
    though the engine called them, which would have made any
    Protocol-typed mock blow up at those call sites.
    """

    @property
    def enabled(self) -> bool:
        """True when both a cap is set and NPCs have been registered."""
        ...

    def register(self, actor_ids: list[ActorId]) -> None:
        """Register all NPCs up front. Bootstraps the initial active
        cohort and resets all per-run state (queues, last-activation
        tracking, cursors).
        """
        ...

    def is_active(self, actor_id: ActorId) -> bool:
        """Is this NPC in the current active cohort?"""
        ...

    def active_ids(self) -> set[ActorId]:
        """Return a copy of the current active cohort."""
        ...

    def registered_ids(self) -> list[ActorId]:
        """Return a copy of the full registered list, stable order."""
        ...

    def policy_for(self, event_type: str) -> str:
        """Resolve inactive-event policy for ``event_type``.

        Returns one of ``"record_only"``, ``"defer"``, ``"promote"``.
        """
        ...

    def enqueue(self, actor_id: ActorId, queued: Any) -> bool:
        """Append an event to a dormant NPC's queue. Returns True if
        queued, False if the queue was at capacity and oldest was
        dropped.
        """
        ...

    def drain_queue(self, actor_id: ActorId) -> list[Any]:
        """Pop and return all queued events for ``actor_id``."""
        ...

    def queue_depth(self, actor_id: ActorId) -> int:
        """Current queue depth for ``actor_id`` (0 if no queue exists)."""
        ...

    def try_promote(self, actor_id: ActorId) -> tuple[bool, ActorId | None]:
        """Preempt-promote a dormant NPC. Returns
        ``(promoted, evicted_id)``. When the global
        ``promote_budget_per_tick`` is exhausted, returns
        ``(False, None)`` and the caller must fall back to ``defer``.
        """
        ...

    def rotate(self, tick: int) -> tuple[list[ActorId], list[ActorId]]:
        """Run one rotation cycle. Returns ``(demoted_ids, promoted_ids)``."""
        ...

    def record_activation(self, actor_id: ActorId, tick: int) -> None:
        """Log an activation for the ``recency`` policy and LRU eviction."""
        ...

    def stats(self) -> Any:
        """Return a :class:`CohortStats`-compatible snapshot.

        Shape: ``.active_count``, ``.registered_count``,
        ``.queue_total_depth``, ``.promote_budget_remaining``,
        ``.rotation_policy`` (review fix D4 — policy was previously
        reached via ``getattr(cm, "_rotation_policy", "unknown")``
        which defeats the Protocol indirection).
        """
        ...


# ---------------------------------------------------------------------------
# Memory Engine (Phase 4B — PMF Plan)
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryEngineProtocol(Protocol):
    """Caller-agnostic interface to the Memory Engine.

    Any caller (``NPCActivator``, agent activators, research-team
    primitives, external tools) depends only on this protocol. The
    concrete :class:`volnix.engines.memory.engine.MemoryEngine` is
    imported only in :mod:`volnix.registry.composition`.

    Scopes:
        - ``actor`` — private to a single actor. Cross-actor reads
          must pass the Permission Engine gate.
        - ``team`` — shared across team members (plumbed for 4D).

    Determinism contract: same seed + same inputs ⇒ byte-identical
    memory state at every tick. Implementations must honour this
    across all retrieval modes.

    Observability contract: every public method emits a ledger entry.
    See :mod:`volnix.ledger.entries` for the six 4B entry types.
    """

    async def remember(
        self,
        *,
        caller: ActorId,
        target_scope: MemoryScope,
        target_owner: str,
        write: MemoryWrite,
        tick: int,
    ) -> MemoryRecordId:
        """Persist a new memory record.

        Raises :class:`volnix.core.memory_types.MemoryAccessDenied`
        when ``caller`` lacks permission to write to the target scope.
        """
        ...

    async def recall(
        self,
        *,
        caller: ActorId,
        target_scope: MemoryScope,
        target_owner: str,
        query: MemoryQuery,
        tick: int,
    ) -> MemoryRecall:
        """Retrieve records matching ``query`` from the target scope.

        Graph-mode queries raise ``NotImplementedError`` in 4B
        (schema plumbed, traversal arrives in 4D).
        """
        ...

    async def consolidate(
        self,
        actor_id: ActorId,
        *,
        force: bool = False,
        tick: int = 0,
    ) -> Any:
        """Distill recent episodic records into semantic facts.

        Returns a ``ConsolidationResult`` (engine-internal type,
        typed as ``Any`` here to keep the protocol surface free of
        engine-internal imports).
        """
        ...

    async def evict(self, actor_id: ActorId) -> None:
        """Flush any write buffer for ``actor_id`` and run
        consolidation if ``"on_eviction"`` is in the cadence config.
        Called by the :class:`CohortRotationEvent` subscriber.
        """
        ...

    async def hydrate(self, actor_id: ActorId) -> None:
        """Warm any in-memory cache for ``actor_id``. Lazy-on-first-recall
        is an acceptable implementation — the ledger entry is the contract."""
        ...
