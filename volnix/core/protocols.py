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
from volnix.core.types import (
    ActorId,
    BudgetState,
    EntityId,
    EventId,
    FidelityTier,
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

    async def snapshot(self, label: str = "default") -> SnapshotId:
        """Create an immutable point-in-time snapshot of the entire world state."""
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
class NPCActivatorProtocol(Protocol):
    """Entry point for activating an Active NPC on a trigger event.

    The concrete implementation (Phase 2:
    ``volnix/engines/agency/npc_activator.py``) reuses the AgencyEngine
    tool-loop so that every NPC action flows through the same 7-step
    pipeline as agent actions. There is no NPC-specific fast path.
    """

    async def activate_npc(
        self,
        actor_id: ActorId,
        trigger_event: Event,
        actor_state: Any,
    ) -> None:
        """Activate the NPC in response to ``trigger_event``.

        Args:
            actor_id: The target NPC's actor id.
            trigger_event: The event that woke the NPC
                (e.g. :class:`NPCExposureEvent`).
            actor_state: The actor's mutable :class:`ActorState`. Its
                ``activation_profile_name`` must be set — this contract
                is for Active NPCs only.
        """
        ...
