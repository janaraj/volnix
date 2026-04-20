"""AgencyEngine -- manages internal actor lifecycle.

Only active when the world has internal actors. Handles:
- Event-first activation (which actors should act after each committed event)
- Tiered action generation (Tier 1 check -> Tier 2 batch -> Tier 3 individual)
- Deterministic state updates after committed events
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, ClassVar

from volnix.actors.queued_event import QueuedEvent
from volnix.actors.state import ActorState, InteractionRecord, ScheduledAction, Subscription
from volnix.core.engine import BaseEngine
from volnix.core.envelope import ActionEnvelope
from volnix.core.events import Event, WorldEvent
from volnix.core.types import (
    ActionSource,
    ActorId,
    EnvelopePriority,
    ServiceId,
)
from volnix.engines.agency.config import AgencyConfig
from volnix.engines.agency.prompt_builder import ActorPromptBuilder
from volnix.llm._history_compaction import compact_tool_results
from volnix.llm._tool_pairing import repair_tool_call_pairing
from volnix.llm.types import LLMRequest, ToolCall, ToolDefinition
from volnix.simulation.world_context import WorldContextBundle

logger = logging.getLogger(__name__)


def _build_tool_call_dict(tc: ToolCall, tc_id: str) -> dict[str, Any]:
    """Build an OpenAI-format tool_call dict from a ToolCall.

    Carries ``provider_metadata`` alongside the standard fields so
    provider-specific passthrough data (e.g., Gemini thought_signature)
    can be restored when the history is replayed on the next turn.
    Non-Gemini providers strip this key at their own boundary.
    """
    entry: dict[str, Any] = {
        "id": tc_id,
        "type": "function",
        "function": {
            "name": tc.name,
            "arguments": json.dumps(tc.arguments),
        },
    }
    if tc.provider_metadata:
        entry["provider_metadata"] = tc.provider_metadata
    return entry


# -- history sanitisation for two-phase game activation ----------------


def _sanitize_history_for_game_move(
    messages: list[dict[str, Any]],
    game_tool_names: frozenset[str],
    char_limit: int = 8000,
) -> list[dict[str, Any]]:
    """Replace non-game tool-call history with a text research summary.

    Phase 1 (``game_research``) leaves assistant messages containing
    ``tool_calls`` for non-game tools (``databases.retrieve``,
    ``pages.retrieve``, ``conversations.list``, etc.).  When Phase 2
    (``game_move``) replays this history, weaker models hallucinate
    calls to those tool names even though only game tools are in the
    ``tools`` parameter.

    This function:

    * Preserves system / user messages (identity, prompts, state updates)
    * Preserves assistant messages whose tool_calls are ALL game tools
    * Preserves text-only assistant messages
    * Replaces non-game (assistant + tool result) blocks with a single
      text-only assistant message containing the research findings

    Args:
        messages: The conversation history (OpenAI-format dicts).
        game_tool_names: Tool names registered under ``service="game"``
            (e.g. ``{"negotiate_propose", "negotiate_counter", …}``).
            Derived by the caller from ``_get_tools_for_actor`` so the
            function is game-type agnostic.

    Returns:
        A **new** list — the input is not mutated.
    """
    if len(messages) < 2:
        return list(messages)

    # -- Pre-pass: collect tool_call IDs that belong to game tools ------
    game_tc_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn_name = (tc.get("function") or {}).get("name", "")
                if fn_name in game_tool_names:
                    game_tc_ids.add(tc.get("id", ""))

    # -- Main pass: keep / skip / collect --------------------------------
    research_findings: list[str] = []
    result: list[dict[str, Any]] = []
    insert_pos: int | None = None  # where the first removed msg was

    for msg in messages:
        role = msg.get("role", "")

        # System and user messages are always preserved.
        if role in ("system", "user"):
            result.append(msg)
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                all_game = all(
                    (tc.get("function") or {}).get("name", "") in game_tool_names
                    for tc in tool_calls
                )
                any_game = any(
                    (tc.get("function") or {}).get("name", "") in game_tool_names
                    for tc in tool_calls
                )
                if all_game:
                    result.append(msg)
                elif any_game:
                    # Mixed game + non-game in one response — shouldn't
                    # happen (game calls trigger short-circuit in Phase 1)
                    # but strip the non-game tool_calls so the assistant
                    # only declares ids that will be answered by the tool
                    # responses we keep below. Non-game tool responses
                    # still get their content absorbed into research_findings.
                    logger.warning(
                        "_sanitize_history_for_game_move: mixed game/"
                        "non-game tool_calls in one assistant message, "
                        "stripping non-game tool_calls",
                    )
                    game_only_tcs = [
                        tc
                        for tc in tool_calls
                        if (tc.get("function") or {}).get("name", "") in game_tool_names
                    ]
                    # Mark insert_pos BEFORE this assistant so the
                    # research summary can't split the assistant from
                    # its tool responses (which would break pairing).
                    if insert_pos is None:
                        insert_pos = len(result)
                    result.append({**msg, "tool_calls": game_only_tcs})
                else:
                    # All non-game: skip, mark insertion position.
                    if insert_pos is None:
                        insert_pos = len(result)
            else:
                # Text-only assistant message: preserve.
                result.append(msg)
            continue

        if role == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id in game_tc_ids:
                result.append(msg)
            else:
                content = msg.get("content", "")
                if content:
                    research_findings.append(content)
            continue

        # Unknown role: preserve defensively.
        result.append(msg)

    # -- Inject research summary at the first-removed position ----------
    if research_findings:
        joined = "\n\n".join(research_findings)
        if len(joined) > char_limit:
            joined = joined[:char_limit] + "\n[...truncated]"
        summary_msg: dict[str, Any] = {
            "role": "assistant",
            "content": ("[I gathered the following information during research.]\n\n" + joined),
        }
        pos = insert_pos if insert_pos is not None else min(2, len(result))
        result.insert(pos, summary_msg)

    # Final structural invariant: tool_call ↔ tool-response pairing.
    # Handles edge cases (partial prior-turn blocks, unexpected orphans)
    # so no downstream provider sees a payload that would 400.
    return repair_tool_call_pairing(result)


class AgencyEngine(BaseEngine):
    """Manages internal actor lifecycle: activation, action generation, state updates."""

    engine_name: ClassVar[str] = "agency"
    # Agency is NOT driven by bus fanout. The legacy ``["world", "simulation"]``
    # subscriptions never actually matched any published event types
    # (events are published as ``world.negotiate_propose`` etc, not ``world``),
    # so ``_handle_event`` never fired for them. SimulationRunner and
    # GameOrchestrator both call agency methods directly (SimulationRunner
    # via ``notify``, orchestrator via ``activate_for_event``). Cleared to
    # ``[]`` in Cycle B.7 to make the contract explicit.
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state"]

    async def _on_initialize(self) -> None:
        """Read config, set up internal structures."""
        raw = {k: v for k, v in self._config.items() if not k.startswith("_")}
        self._typed_config = AgencyConfig(**raw)
        self._actor_states: dict[ActorId, ActorState] = {}
        self._prompt_builder: ActorPromptBuilder | None = None
        self._world_context: WorldContextBundle | None = None
        self._llm_router: Any = None
        self._available_actions: list[dict[str, Any]] = []
        self._tool_definitions: list[ToolDefinition] = []
        self._tool_name_map: dict[str, str] = {}  # sanitized API name → original action name
        self._tool_to_service: dict[str, str] = {}  # sanitized API name → service name
        self._llm_semaphore = asyncio.Semaphore(self._typed_config.max_concurrent_actor_calls)
        self._pipeline_lock = asyncio.Lock()  # Serializes pipeline execution across parallel agents
        # Per-actor locks serialize same-actor activations. Prevents the
        # feedback-loop race where GameOrchestrator re-activates a player
        # whose previous activation is still inside _activate_with_tool_loop
        # (Player A commits → bus → orchestrator activates Player B → B
        # commits → bus → orchestrator activates A *again*). Without the
        # lock, two concurrent activations mutate actor_state.activation_messages
        # interleaved. The lock is lazy — only created on first activation
        # for a given actor.
        self._actor_activation_locks: dict[ActorId, asyncio.Lock] = {}
        self._tool_executor: Any = None
        self._simulation_progress: tuple[int, int] | None = None  # (current_events, max_events)
        # Opt-in Active-NPC support. When None (the default), every
        # activation follows the existing agent path. When set via
        # ``set_npc_activator``, actors whose ``ActorState`` declares
        # an ``activation_profile_name`` are dispatched to the NPC
        # loop in ``activate_for_event`` below.
        self._npc_activator: Any = None
        # Opt-in activation cycling (PMF Plan Phase 4A). When None
        # (the default), the cohort gate short-circuits and Active
        # NPCs activate on every matching event exactly as today.
        # When set via ``set_cohort_manager``, the gate in
        # ``_activate_with_tool_loop`` applies the per-event-type
        # policy before letting the LLM loop run.
        self._cohort_manager: Any = None
        # PMF 4B Step 11 — MemoryEngine injection slot. Opt-in via
        # ``set_memory_engine``. When None (default), NPCActivator's
        # memory hooks short-circuit and the activation path is
        # byte-identical to Phase 4A / Step 10.
        self._memory_engine: Any = None

    def set_simulation_progress(self, current: int, total: int) -> None:
        """Update simulation progress for lead agent prompt awareness."""
        self._simulation_progress = (current, total)

    def set_tool_executor(self, executor: Any) -> None:
        """Set the pipeline executor for inline tool execution in multi-turn loops.

        The executor is ``async callable(ActionEnvelope) -> WorldEvent | None``.
        It runs the full 7-step governance pipeline. Returns the committed
        WorldEvent on success, or None if the pipeline blocked the action.
        """
        self._tool_executor = executor

    def set_npc_activator(self, activator: Any) -> None:
        """Opt in Active-NPC activation via the given activator.

        The activator must expose ``async activate_npc(...) ->
        list[ActionEnvelope]`` per
        :class:`volnix.core.protocols.NPCActivatorProtocol`. Until this
        is called, every activation follows the existing agent path —
        HUMAN actors without an ``activation_profile`` remain passive
        and their behavior is byte-identical to the pre-Layer-1 state.
        """
        self._npc_activator = activator

    def set_cohort_manager(self, manager: Any) -> None:
        """Opt-in activation cycling via the given cohort manager.

        The manager must satisfy
        :class:`volnix.core.protocols.CohortManagerProtocol`. When
        ``None`` (the default), the cohort gate in
        ``_activate_with_tool_loop`` short-circuits — every Active
        NPC activates on every matching event, matching pre-4A
        behavior byte-identical (locked by the Phase 0 regression
        oracle at ``tests/integration/test_passive_npc_regression.py``).

        Agents (non-NPC, ``activation_profile_name is None``) are
        never gated by the cohort regardless of this setting.
        """
        self._cohort_manager = manager

    def set_memory_engine(self, engine: Any) -> None:
        """Opt-in memory integration (PMF 4B Step 11).

        The engine must satisfy
        :class:`volnix.core.protocols.MemoryEngineProtocol`. When
        ``None`` (the default), the memory hooks in
        ``NPCActivator`` short-circuit — every NPC activation is
        byte-identical to the pre-Step-11 path (locked by the
        Phase 0 regression oracle at
        ``tests/integration/test_passive_npc_regression.py``).

        Called by ``app.py`` after ``build_memory_engine`` +
        lifecycle (``initialize`` + ``start``) succeed. The
        activator reads it via ``host._memory_engine`` for
        pre-activation recall and post-activation implicit
        remember.

        **Idempotent replacement (PMF 4B cleanup commit 4).** If a
        MemoryEngine is already installed, it is ``await stop()``-d
        before the new one is stored. Without this guard, long-lived
        processes (``volnix serve`` running multiple worlds, test
        harnesses re-entering ``configure_agency``) would leak
        ``cohort.rotated`` bus subscriptions on every world reset —
        each rotation would fire on a pile of dead engines.

        The stop is scheduled as an ``asyncio`` task and awaited
        inline so the caller sees a clean swap before control
        returns. A stop failure is logged and does NOT block the
        replacement; the new engine still takes the slot.
        """
        prior = self._memory_engine
        self._memory_engine = engine
        if prior is not None and prior is not engine and hasattr(prior, "stop"):
            # Fire-and-log pattern: we cannot block a synchronous
            # setter on async teardown. Schedule the stop; if the
            # caller needs deterministic teardown, they can await
            # prior.stop() themselves before calling the setter.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Not inside an event loop — fall back to logging.
                # Real callers (app.py) always hold a loop.
                logger.warning(
                    "AgencyEngine.set_memory_engine called outside an "
                    "event loop with a prior engine installed; the "
                    "prior engine is being replaced without being "
                    "stopped. Call ``await prior.stop()`` explicitly "
                    "before the setter if deterministic teardown is "
                    "required."
                )
                return

            async def _stop_prior() -> None:
                try:
                    await prior.stop()
                except Exception as exc:  # noqa: BLE001 — stop is best-effort
                    logger.warning(
                        "AgencyEngine.set_memory_engine: prior memory engine stop failed: %s",
                        exc,
                    )

            loop.create_task(_stop_prior())

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
        self._tool_definitions = self._build_tool_definitions()
        self._llm_router = self._config.get("_llm_router")

        logger.info(
            "AgencyEngine configured: %d internal actors, %d tool definitions",
            len(self._actor_states),
            len(self._tool_definitions),
        )

    def _build_tool_definitions(self) -> list[ToolDefinition]:
        """Convert available_actions to provider-agnostic ToolDefinitions.

        Uses simple sanitized names (matching the external adapter format).
        Only adds a ``{service}__`` prefix when two services share the same
        action name (collision avoidance).

        Adds shared metadata params (reasoning, intended_for, state_updates)
        that the agency engine extracts before building ActionEnvelopes.
        """
        meta_params: dict[str, Any] = {
            "reasoning": {"type": "string", "description": "Why you chose this action"},
            "intended_for": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Teammate roles to address (e.g. ['analyst', 'researcher']). Use specific roles, not 'all'.",
            },
            "state_updates": {
                "type": "object",
                "properties": {
                    "goal_context": {
                        "type": "string",
                        "description": "Updated progress notes",
                    },
                    "pending_tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Remaining tasks",
                    },
                },
            },
        }

        # First pass: detect collisions (two services with same sanitized name)
        name_services: dict[str, set[str]] = {}
        for action in self._available_actions:
            sanitized = action.get("name", "").replace(".", "_")
            name_services.setdefault(sanitized, set()).add(action.get("service", ""))
        collisions = {n for n, svcs in name_services.items() if len(svcs) > 1}

        # Second pass: build tool definitions
        tools: list[ToolDefinition] = []
        self._tool_name_map = {}
        self._tool_to_service = {}
        for action in self._available_actions:
            name = action.get("name", "")
            service = action.get("service", "")
            params = action.get("parameters", {})
            raw_properties = {**params.get("properties", {}), **meta_params}
            required = list(params.get("required", [])) + ["reasoning"]

            # Sanitize parameter schemas for provider compatibility.
            # OpenAI requires "object" types to have "properties" and
            # "array" types to have "items". Bootstrapped profiles may
            # generate bare types without these.
            properties: dict[str, Any] = {}
            for pname, pdef in raw_properties.items():
                if isinstance(pdef, dict):
                    pdef = dict(pdef)
                    if pdef.get("type") == "object" and "properties" not in pdef:
                        pdef["properties"] = {}
                    if pdef.get("type") == "array" and "items" not in pdef:
                        pdef["items"] = {"type": "string"}
                properties[pname] = pdef

            # Sanitize: OpenAI requires ^[a-zA-Z0-9_-]+$ — no dots allowed
            sanitized = name.replace(".", "_")
            # Only prefix when collision exists (two services share same action name)
            if sanitized in collisions and service:
                api_name = f"{service}__{sanitized}"
            else:
                api_name = sanitized

            self._tool_name_map[api_name] = name  # "chat_postMessage" → "chat.postMessage"
            self._tool_to_service[api_name] = service  # "chat_postMessage" → "slack"

            tools.append(
                ToolDefinition(
                    name=api_name,
                    service=service,
                    description=f"[{service}] {action.get('description', '')}",
                    parameters={
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                )
            )

        # do_nothing tool — agent skips this turn
        tools.append(
            ToolDefinition(
                name="do_nothing",
                service="",
                description="Skip this turn — nothing useful to do right now.",
                parameters={
                    "type": "object",
                    "properties": {
                        "reasoning": {
                            "type": "string",
                            "description": "Why you're skipping",
                        }
                    },
                    "required": ["reasoning"],
                },
            )
        )
        return tools

    def register_game_tools(self, actions: list[dict[str, Any]]) -> None:
        """Register structured game-move tools for the active game (NF1).

        Called by :meth:`volnix.app.VolnixApp.configure_game` after
        :meth:`GameOrchestrator.configure` and before the orchestrator's
        ``_on_start``. The actions come from
        ``volnix.packs.verified.game.tool_schema.build_negotiation_tools``
        and have the same shape as entries in ``self._available_actions``
        — raw action dicts with ``name``, ``service``, ``description``,
        ``parameters``, and ``http_method`` keys.

        This method layers the shared agency meta_params (``reasoning``,
        ``intended_for``, ``state_updates``) onto each action's
        parameters — matching :meth:`_build_tool_definitions` exactly —
        so the LLM sees a uniform tool interface. ``reasoning`` is always
        required. Parameter schemas are sanitized for provider
        compatibility (bare ``object`` types get empty ``properties``,
        bare ``array`` types get ``items: {type: string}``).

        Idempotent: registering the same tool ``name`` twice replaces
        the prior entry (safe for reloads). Tools registered here are
        naturally filtered by :meth:`_get_tools_for_actor` — only
        actors with ``write: [game]`` in their permissions see them.
        """
        meta_params: dict[str, Any] = {
            "reasoning": {
                "type": "string",
                "description": "Why you chose this action",
            },
            "intended_for": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Teammate roles to address (e.g. ['analyst', 'researcher']). "
                    "Use specific roles, not 'all'."
                ),
            },
            "state_updates": {
                "type": "object",
                "properties": {
                    "goal_context": {
                        "type": "string",
                        "description": "Updated progress notes",
                    },
                    "pending_tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Remaining tasks",
                    },
                },
            },
        }

        for action in actions:
            name = action.get("name", "")
            if not name:
                logger.warning("register_game_tools: skipping action with no name: %s", action)
                continue
            service = action.get("service", "")
            params = action.get("parameters") or {}
            raw_properties = {**params.get("properties", {}), **meta_params}
            required = list(params.get("required", [])) + ["reasoning"]

            # Sanitize for provider compatibility (matches _build_tool_definitions).
            properties: dict[str, Any] = {}
            for pname, pdef in raw_properties.items():
                if isinstance(pdef, dict):
                    pdef = dict(pdef)
                    if pdef.get("type") == "object" and "properties" not in pdef:
                        pdef["properties"] = {}
                    if pdef.get("type") == "array" and "items" not in pdef:
                        pdef["items"] = {"type": "string"}
                properties[pname] = pdef

            tool = ToolDefinition(
                name=name,
                service=service,
                description=action.get("description", ""),
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            )

            # Idempotent replace by name. PREPEND game tools so they
            # appear before Slack/service tools in the LLM's tool list.
            # LLMs (especially flash models) tend to prefer tools listed
            # first — prepending makes negotiate_* the default choice.
            self._tool_definitions = [tool] + [t for t in self._tool_definitions if t.name != name]
            # Identity mapping: tool name == action type
            self._tool_name_map[name] = name
            self._tool_to_service[name] = service
            logger.info(
                "Registered game tool %s (service=%s, %d params)",
                name,
                service,
                len(properties),
            )

    def _get_tools_for_actor(self, actor_id: str) -> list[ToolDefinition]:
        """Filter tool definitions by actor's service permissions.

        Uses the actor registry to check read/write permissions per service.
        Agents only see tools for services they have access to.
        """
        registry = self._config.get("_actor_registry")
        if not registry:
            return self._tool_definitions

        try:
            actor_def = registry.get_or_none(ActorId(actor_id))
        except Exception:
            return self._tool_definitions
        if not actor_def or not hasattr(actor_def, "permissions") or not actor_def.permissions:
            return self._tool_definitions

        perms = actor_def.permissions
        read_services = set(perms.get("read", []))
        write_services = set(perms.get("write", []))

        # "all" means access to everything
        all_services = {t.service for t in self._tool_definitions if t.service}
        if "all" in read_services:
            read_services = all_services
        if "all" in write_services:
            write_services = all_services

        # Build lookup: original action name → http_method
        method_lookup = {
            a.get("name", ""): a.get("http_method", "POST").upper() for a in self._available_actions
        }

        allowed = []
        for tool in self._tool_definitions:
            if not tool.service:
                allowed.append(tool)  # do_nothing, etc.
                continue
            original_name = self._tool_name_map.get(tool.name, "")
            method = method_lookup.get(original_name, "POST")
            if method == "GET" and tool.service in read_services:
                allowed.append(tool)
            elif method != "GET" and tool.service in write_services:
                allowed.append(tool)

        return allowed

    async def _handle_event(self, event: Event) -> None:
        """Handle bus events. WorldEvents trigger notify().

        When SimulationRunner is active (event_queue is wired), skip —
        the runner calls notify() directly. Running both paths causes
        a re-entrancy deadlock on _llm_semaphore.

        Note (PMF Plan Phase 4A, fix for review C1): ``CohortRotationEvent``
        is published by ``rotate_cohort`` for observability only. The
        drain path is already called inline inside ``rotate_cohort``,
        so we deliberately do NOT re-drain when the event comes back
        around through the bus — that would double-drain. The event
        exists for downstream observers (dashboards, runners) and is
        ignored by this engine.
        """
        if self._config.get("_event_queue") is not None:
            return  # SimulationRunner handles notify() directly

        if isinstance(event, WorldEvent):
            await self.notify(event)

    async def _drain_promoted_cohort_queues(self, promoted: list[ActorId]) -> None:
        """Replay queued events for newly-promoted NPCs.

        PMF Plan Phase 4A. Each queued event is re-fired through
        ``activate_for_event`` (which respects the per-actor lock and
        the existing activation-message cap). Broken replays are
        logged and swallowed — one bad NPC must not take down a tick.
        """
        if not promoted or self._cohort_manager is None:
            return
        for actor_id in promoted:
            queued = self._cohort_manager.drain_queue(actor_id)
            for q in queued:
                try:
                    await self.activate_for_event(
                        actor_id,
                        reason=f"cohort_drain:{q.event_type}",
                        trigger_event=q.event,
                    )
                except Exception as exc:  # noqa: BLE001 — intentionally contained
                    logger.warning(
                        "Cohort drain failed for %s/%s: %s",
                        actor_id,
                        q.event_type,
                        exc,
                    )

    async def rotate_cohort(self, tick: int) -> tuple[list[ActorId], list[ActorId]]:
        """Trigger one cohort rotation cycle.

        PMF Plan Phase 4A. Entry point for the simulation runner (or
        tests) to drive rotation. Rotation is engine state — not a
        world action — so this doesn't go through the pipeline.

        The method writes to three channels (review D1 — intentional):
          1. Asks the cohort manager to pick demotes + promotes
             (mutation of engine state).
          2. Publishes ``CohortRotationEvent`` on the bus — pure
             observability for external dashboards / runners.
             ``_handle_event`` specifically ignores this event on
             its way back in (review C1) so we never double-drain.
          3. Records a ``CohortRotationEntry`` in the ledger for
             audit.
          4. Drains queued events on promoted NPCs through the normal
             ``activate_for_event`` path.

        The three channels serve distinct consumers (runtime logic /
        real-time observers / audit) and aren't merge-able into one.

        Concurrency (review C2 / C3): single-loop asyncio makes all
        synchronous methods on the cohort manager (``rotate``,
        ``try_promote``, ``enqueue``) atomic w.r.t. each other — two
        coroutines calling in race-free because no ``await`` happens
        between the read-modify-write steps. If this engine is ever
        migrated to a thread pool, a real lock must be added to
        ``CohortManager``; today it's not needed.

        Returns ``([], [])`` when cohort is disabled so callers can
        treat it as a no-op cleanly.
        """
        cm = self._cohort_manager
        if cm is None or not getattr(cm, "enabled", False):
            return [], []

        demoted, promoted = cm.rotate(tick)
        if not promoted and not demoted:
            return demoted, promoted

        # Observability: emit the event + record the ledger entry.
        # Import locally so engine.py does not depend on 4A events at
        # module import time (they live in volnix.core.events).
        from datetime import UTC, datetime

        from volnix.core.events import CohortRotationEvent
        from volnix.core.types import Timestamp
        from volnix.ledger.entries import CohortRotationEntry

        now = datetime.now(UTC)
        stats = cm.stats()
        # Review fix D4: read rotation_policy via the protocol-exposed
        # stats snapshot, not via ``getattr(cm, "_rotation_policy", …)``
        # which reached a private attribute and defeated the Protocol.
        rotation_policy = getattr(stats, "rotation_policy", "unknown")

        # PMF 4B cleanup commit 5 — wrap publish in a narrow
        # try/except. Pre-cleanup this was unwrapped; a bus failure
        # would leave cohort state mutated but subscribers
        # (MemoryEngine) uninformed. Now a failure logs + continues;
        # the ledger write below still records the rotation as an
        # audit trail.
        try:
            await self.publish(
                CohortRotationEvent(
                    timestamp=Timestamp(world_time=now, wall_time=now, tick=tick),
                    promoted_ids=list(promoted),
                    demoted_ids=list(demoted),
                    rotation_policy=rotation_policy,
                    tick=tick,
                )
            )
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "rotate_cohort: CohortRotationEvent publish failed "
                "(cohort state still mutated; ledger still records): %s",
                exc,
            )
        # Await the ledger write directly (not fire-and-forget) so
        # callers / tests can observe the rotation record immediately
        # after ``rotate_cohort`` returns. Rotations are low-frequency
        # enough that the extra await doesn't impact the sim loop.
        ledger = self._config.get("_ledger") or getattr(self, "_ledger", None)
        if ledger is not None:
            entry = CohortRotationEntry(
                tick=tick,
                rotation_policy=rotation_policy,
                demoted_count=len(demoted),
                promoted_count=len(promoted),
                active_count=stats.active_count,
                registered_count=stats.registered_count,
                queue_total_depth=stats.queue_total_depth,
            )
            try:
                await ledger.append(entry)
            except (OSError, RuntimeError, ValueError) as exc:
                # Review fix N2: narrowed from bare ``except Exception``.
                # Realistic ledger failure modes: backing store I/O
                # (OSError), protocol contract breach (RuntimeError),
                # Pydantic/schema issue (ValueError). Anything else
                # — CancelledError, KeyboardInterrupt — must propagate.
                logger.warning("CohortRotationEntry append failed: %s", exc)

        # Drain first — the event is already published, so even if
        # drain fails partially the rotation record stands.
        await self._drain_promoted_cohort_queues(list(promoted))
        return demoted, promoted

    def _should_cohort_gate(self, actor: ActorState, cm: Any) -> bool:
        """Return True if this actor must go through the cohort gate.

        Review fix D3: the predicate is:

        * ``cm.enabled`` — cohort actually holding actors, else no gate.
        * ``activation_profile_name is not None`` — only Active NPCs
          are gated; agents + passive HUMANs bypass entirely.
        * ``not cm.is_active(actor_id)`` — active members flow through
          as usual.

        Kept as a dedicated method so future actor categories have one
        site to audit before widening the gate.
        """
        if not getattr(cm, "enabled", False):
            return False
        if actor.activation_profile_name is None:
            return False
        return not cm.is_active(actor.actor_id)

    def _record_cohort_decision(
        self,
        actor_id: ActorId,
        decision: str,
        event_type: str,
        cm: Any,
        *,
        evicted_actor_id: ActorId | None = None,
    ) -> None:
        """Ledger a cohort-gate decision (review fix M4).

        Fire-and-forget via ``_record_to_ledger`` so the gate stays
        fast. Absent ledger → no-op.
        """
        from volnix.ledger.entries import CohortDecisionEntry

        self._record_to_ledger(
            CohortDecisionEntry(
                actor_id=actor_id,
                decision=decision,
                event_type=event_type,
                queue_depth_after=cm.queue_depth(actor_id),
                evicted_actor_id=evicted_actor_id,
            )
        )

    def _current_tick(self) -> int:
        """Best-effort current tick; ``0`` when unknown.

        Phase 4A uses this to stamp ``QueuedEvent.queued_tick`` so
        drain + replay can reconstruct chronological order. The agent
        path already uses ``_simulation_progress`` the same way.

        Review fix M3: when ``_simulation_progress`` is absent and
        cohort policies depend on monotonic tick ordering (recency,
        event_pressure_weighted), silently returning 0 means every
        queued event and every activation record collapses to tick 0
        and recency policy degenerates to registered-order. We log a
        warning the first time it happens per process so runner
        mis-wiring shows up in logs. Tests routinely leave progress
        absent — the warning is informational, not fatal.
        """
        progress = self._simulation_progress
        if progress is not None:
            return progress[0]
        if not getattr(self, "_tick_fallback_warned", False):
            logger.warning(
                "AgencyEngine._current_tick() falling back to 0 — "
                "_simulation_progress is not set. In production the "
                "simulation runner must call set_simulation_progress "
                "so cohort recency/pressure policies have real ticks."
            )
            self._tick_fallback_warned = True
        return 0

    def _record_to_ledger(self, *entries) -> None:
        """Schedule ledger writes without blocking the caller.

        Ledger is observability — writes must never block the simulation loop.
        Uses asyncio.create_task for fire-and-forget scheduling.

        Accepts ledger from either ``self._config["_ledger"]`` (the
        production wiring path) OR ``self._ledger`` (the attribute path
        used in tests and directly from ``rotate_cohort``). Both are
        legitimate wiring modes and should work.
        """
        ledger = self._config.get("_ledger") or getattr(self, "_ledger", None)
        if ledger is None:
            return

        async def _write(lgr, items):
            for entry in items:
                try:
                    await lgr.append(entry)
                except (OSError, RuntimeError, ValueError):
                    # Review fix N2: narrowed from bare ``except:``.
                    # Backing-store I/O, protocol mismatch, schema
                    # issue — all non-fatal. Other exceptions propagate.
                    pass

        asyncio.create_task(_write(ledger, entries))

    # -- Activation (called by SimulationRunner or via _handle_event) --

    async def notify(self, committed_event: WorldEvent) -> list[ActionEnvelope]:
        """Called after every committed event. Returns envelopes for activated actors.

        Tier 1: deterministic check -- find affected actors (no LLM)
        Classify into Tier 2 (batch) or Tier 3 (individual)
        Generate actions via LLM
        Return ActionEnvelopes for EventQueue
        """
        logger.info(
            "[AGENCY.notify] event_type=%s, actor=%s, type=%s, actor_states=%d",
            type(committed_event).__name__,
            getattr(committed_event, "actor_id", "?"),
            getattr(committed_event, "event_type", "?"),
            len(self._actor_states),
        )
        if not self._actor_states:
            return []

        # Tier 1: deterministic activation check
        activated = self._tier1_activation_check(committed_event)

        # Subscription-based recording and activation (separated concerns).
        # RECORDING: agent sees event in recent_interactions if subscribed to service.
        # ACTIVATION: agent starts multi-turn loop only if intended_for includes them.
        if self._typed_config.collaboration_enabled:
            already_activated = {aid for aid, _ in activated}
            intended_for = committed_event.input_data.get("intended_for", [])
            event_service = str(committed_event.service_id)
            event_type = getattr(committed_event, "event_type", "")

            for actor_id, actor in self._actor_states.items():
                if str(actor_id) == str(committed_event.actor_id):
                    continue  # don't record/activate from own events
                if actor_id in already_activated:
                    continue

                # STEP 1: RECORDING — does this agent subscribe to this service,
                # or to this event_type via the subscription filter? Active NPCs
                # subscribe by event_type (e.g. ``npc.exposure``) so the service
                # emitting the event doesn't have to be known in advance. Agent
                # subscriptions continue to match by service_id as before.
                service_match = any(
                    event_service == sub.service_id
                    or (event_type and sub.filter.get("event_type") == event_type)
                    for sub in actor.subscriptions
                )
                if service_match:
                    record = self._build_interaction_record(
                        committed_event, actor, source="notified"
                    )
                    actor.recent_interactions.append(record)
                    if len(actor.recent_interactions) > actor.max_recent_interactions:
                        actor.recent_interactions = actor.recent_interactions[
                            -actor.max_recent_interactions :
                        ]

                # STEP 2: ACTIVATION — does intended_for include this agent?
                # The sender controls who reacts via intended_for.
                should_activate = False
                if intended_for and (
                    "all" in intended_for
                    or actor.role in intended_for
                    or str(actor_id) in intended_for
                ):
                    should_activate = True

                if should_activate:
                    activated.append((actor_id, "subscription_match"))
                    # Capture delegation text as goal_context
                    text = committed_event.input_data.get("text", "")
                    if text:
                        actor.goal_context = text[:500]

                # Record to ledger (non-blocking)
                if service_match or should_activate:
                    from volnix.ledger.entries import (
                        CollaborationNotificationEntry,
                        SubscriptionMatchEntry,
                    )

                    self._record_to_ledger(
                        SubscriptionMatchEntry(
                            actor_id=actor_id,
                            event_id=committed_event.event_id,
                            service_id=event_service,
                            sensitivity="immediate",
                            activated=should_activate,
                            reason="subscription_match" if should_activate else "passive",
                        ),
                        CollaborationNotificationEntry(
                            recipient_actor_id=actor_id,
                            source_actor_id=committed_event.actor_id,
                            event_id=committed_event.event_id,
                            channel=committed_event.input_data.get("channel"),
                            intended_for=intended_for,
                            sensitivity="immediate",
                        ),
                    )

        if not activated:
            return []

        # Respect max activations per event
        activated = activated[: self._typed_config.max_activations_per_event]

        # Update pending notifications for all actors affected
        for actor_id, reason in activated:
            actor = self._actor_states.get(actor_id)
            if actor:
                notif = (
                    f"[t={committed_event.timestamp.tick}]"
                    f" {committed_event.event_type}:"
                    f" {committed_event.action} by {committed_event.actor_id}"
                )
                actor.pending_notifications.append(notif)
                max_notif = self._typed_config.max_pending_notifications
                if len(actor.pending_notifications) > max_notif:
                    actor.pending_notifications = actor.pending_notifications[-max_notif:]

        # Record activations to ledger (non-blocking)
        from volnix.ledger.entries import ActorActivationEntry

        for actor_id, reason in activated:
            tier = self._classify_tier(self._actor_states[actor_id], reason)
            self._record_to_ledger(
                ActorActivationEntry(
                    actor_id=actor_id,
                    activation_reason=reason,
                    activation_tier=tier,
                    trigger_event_id=committed_event.event_id,
                )
            )

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

        # Tier 3: parallel multi-turn activations
        if tier3_actors:
            tasks = [
                self._activate_with_tool_loop(actor, reason, committed_event)
                for actor, reason in tier3_actors
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    envelopes.extend(result)
                elif isinstance(result, Exception):
                    logger.error("[AGENCY] activation failed: %s", result)

        # Tier 2: parallel multi-turn activations (same path as Tier 3)
        if tier2_actors:
            tasks = [
                self._activate_with_tool_loop(actor, reason, committed_event)
                for actor, reason in tier2_actors
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    envelopes.extend(result)
                elif isinstance(result, Exception):
                    logger.error("[AGENCY] activation failed: %s", result)

        # Respect max envelopes per event
        envelopes = envelopes[: self._typed_config.max_envelopes_per_event]

        # Record action generation to ledger (non-blocking)
        from volnix.ledger.entries import ActionGenerationEntry

        for env in envelopes:
            self._record_to_ledger(
                ActionGenerationEntry(
                    actor_id=env.actor_id,
                    envelope_id=env.envelope_id,
                    action_type=env.action_type,
                    tier=env.metadata.get("activation_tier", 0),
                )
            )

        return envelopes

    async def check_scheduled_actions(self, current_time: float) -> list[ActionEnvelope]:
        """Check for actors with scheduled actions that are due."""
        envelopes: list[ActionEnvelope] = []
        for actor in self._actor_states.values():
            due = [sa for sa in actor.scheduled_actions if sa.logical_time <= current_time]
            actor.scheduled_actions = [
                sa for sa in actor.scheduled_actions if sa.logical_time > current_time
            ]
            for sa in due:
                if sa.action_type == "continue_work":
                    # Autonomous agent work loop — activate via multi-turn loop
                    envs = await self._activate_with_tool_loop(actor, "continue_work", None)
                    envelopes.extend(envs)
                elif sa.action_type == "request_findings":
                    # Phase 3: Buffer period — lead gathers final findings
                    actor.goal_context = (
                        "BUFFER PERIOD: The simulation is nearing its end. "
                        "Instruct ALL team members to stop new investigations, "
                        "finalize current work, and share their final findings "
                        "immediately. Address each member by role."
                    )
                    envs = await self._activate_with_tool_loop(actor, "request_findings", None)
                    envelopes.extend(envs)
                else:
                    # Standard scheduled action (produce_deliverable, etc.)
                    env = ActionEnvelope(
                        actor_id=actor.actor_id,
                        source=ActionSource.INTERNAL,
                        action_type=sa.action_type,
                        target_service=(
                            ServiceId(sa.target_service) if sa.target_service else None
                        ),
                        payload=sa.payload,
                        logical_time=current_time,
                        priority=EnvelopePriority.SYSTEM,
                        metadata={
                            "activation_reason": "scheduled",
                            "scheduled_description": sa.description,
                        },
                    )
                    envelopes.append(env)
        return envelopes

    def has_scheduled_actions(self) -> bool:
        """Return True if any actor has a scheduled action."""
        return any(len(a.scheduled_actions) > 0 for a in self._actor_states.values())

    def next_scheduled_time(self) -> float | None:
        """Earliest logical_time of any actor's scheduled action, or None."""
        times = [sa.logical_time for a in self._actor_states.values() for sa in a.scheduled_actions]
        return min(times) if times else None

    async def generate_deliverable(
        self,
        actor_id: ActorId,
        payload: dict,
    ) -> dict:
        """Activate the lead actor to synthesize collaboration into a deliverable.

        Uses the actor's goal_context (preset instructions), recent interactions
        (conversation history), and the preset schema (from payload) to generate
        structured JSON via LLM.

        Args:
            actor_id: The lead actor who produces the deliverable.
            payload: Contains 'preset' name and 'schema' for output format.

        Returns:
            The synthesized deliverable JSON, or raw payload as fallback.
        """
        if not self._llm_router or not self._prompt_builder:
            return payload

        actor = self._actor_states.get(actor_id)
        if actor is None:
            return payload

        schema = payload.get("schema", {})
        goal_context = actor.goal_context or ""

        # Build conversation context from actor's recent interactions
        conversation = (
            "\n".join(
                f"[{r.actor_role or r.actor_id}] {r.summary}"
                for r in actor.recent_interactions[-20:]
            )
            if actor.recent_interactions
            else "(no conversation history)"
        )

        system_prompt = self._prompt_builder.build_system_prompt()
        preset_name = payload.get("preset", "deliverable")
        user_prompt = (
            f"## FINAL DELIVERABLE — GENERATE NOW\n\n"
            f"The simulation has concluded. Your ONLY job is to generate "
            f"the final {preset_name} deliverable.\n\n"
            f"{goal_context}\n\n"
            f"## TEAM CONVERSATION\n\n{conversation}\n\n"
            f"Review ALL validated findings from your team. "
            f"Do NOT ask any more questions. Use only the data already collected. "
            f"Be thorough — include all key findings, methodology, "
            f"and any dissenting views. Format according to the schema provided."
        )

        try:
            request = LLMRequest(
                system_prompt=system_prompt,
                user_content=user_prompt,
                output_schema=schema,
                temperature=0.3,
                cache_system_prompt=True,
                model_override=actor.llm_model,
                provider_override=actor.llm_provider,
            )
            response = await self._llm_router.route(
                request,
                "agency",
                self._typed_config.llm_use_case_individual,
            )

            # Structured output path (preferred)
            if response.structured_output:
                return response.structured_output

            # Fallback: parse from content
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:])
                if content.endswith("```"):
                    content = content[:-3].strip()

            return json.loads(content)
        except Exception as exc:
            logger.warning("Deliverable synthesis failed for %s: %s", actor_id, exc)
            return payload

    # -- Tier 1: Deterministic activation check --

    def _tier1_activation_check(self, event: WorldEvent) -> list[tuple[ActorId, str]]:
        """Determine which actors should activate. Pure Python, no LLM.

        Triggers:
        1. Event-affected: committed event touched an entity this actor watches
        2. Wait-threshold: actor's waiting_for patience has expired
        3. Frustration-threshold: actor's frustration crossed escalation threshold
        4. Scheduled action due
        """
        activated: list[tuple[ActorId, str]] = []

        target = event.target_entity
        event_time = event.timestamp.tick  # use tick as proxy for logical time

        for actor_id, actor in self._actor_states.items():
            # Skip the actor that generated this event
            if str(actor_id) == str(event.actor_id):
                continue

            # 1. Event-affected: watched entity touched OR actor referenced in input
            if target and str(target) in [str(e) for e in actor.watched_entities]:
                activated.append((actor_id, "event_affected"))
                continue

            # 1b. Actor referenced in event input_data (e.g., email to_addr contains actor info)
            if event.input_data:
                input_str = str(event.input_data).lower()
                actor_id_lower = str(actor_id).lower()
                if actor_id_lower in input_str:
                    activated.append((actor_id, "referenced"))
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

            # 4. Synthesis deadline (lead actor) — checked before generic
            #    scheduled action so the more specific reason is recorded
            if (
                actor.goal_context
                and "synthesis_deadline" in (actor.goal_context or "")
                and any(
                    sa.action_type == "produce_deliverable" and sa.logical_time <= event_time
                    for sa in actor.scheduled_actions
                )
            ):
                activated.append((actor_id, "synthesis_deadline"))
                continue

            # 5. Scheduled action due
            if any(sa.logical_time <= event_time for sa in actor.scheduled_actions):
                activated.append((actor_id, "scheduled"))
                continue

        return activated

    # -- Subscription matching --

    def _matches_subscription(self, event: WorldEvent, sub: Subscription) -> bool:
        """Check if a committed event matches an actor's subscription.

        Compares event service_id against subscription service_id,
        then checks all filter criteria against event input_data,
        metadata, and response_body.
        """
        logger.info(
            "[AGENCY._matches_sub] service=%s, filter=%s, input_channel=%s",
            sub.service_id,
            dict(sub.filter),
            event.input_data.get("channel", event.input_data.get("channel_id", "?")),
        )
        # Service must match
        if str(event.service_id) != sub.service_id:
            return False

        # Match filter criteria against event payload and metadata
        for key, value in sub.filter.items():
            if value == "self":
                continue  # resolved at activation time, not here

            # "entity" or "entity_type" filter matches against event's entity context
            # (e.g. filter={"entity_type": "message"} matches chat.postMessage)
            if key in ("entity", "entity_type"):
                action_lower = (event.action or "").lower()
                if value.lower() in action_lower or value.lower() in event.event_type.lower():
                    continue

            # Check event input_data (also check common aliases like channel/channel_id)
            if key in event.input_data and event.input_data[key] == value:
                continue
            # Check alias: "channel" filter matches "channel_id" in input
            if key == "channel" and event.input_data.get("channel_id") == value:
                continue

            # Check event metadata
            if key in event.metadata and event.metadata[key] == value:
                continue

            # Check response_body
            if (
                event.response_body
                and key in event.response_body
                and event.response_body[key] == value
            ):
                continue

            # No match on this filter key
            return False

        return True

    def _build_interaction_record(
        self, event: WorldEvent, observer: ActorState, source: str
    ) -> InteractionRecord:
        """Build a structured interaction record from a WorldEvent."""
        # Extract summary from event
        content = event.input_data.get("content", "")
        text = event.input_data.get("text", "")
        body = event.input_data.get("body", "")
        subject = event.input_data.get("subject", "")
        summary_text = content or text or body or subject or event.action

        # Truncate to reasonable length
        if len(summary_text) > 500:
            summary_text = summary_text[:497] + "..."

        # Get actor role from actor states
        actor_role = ""
        actor_state = self._actor_states.get(event.actor_id)
        if actor_state:
            actor_role = actor_state.role

        return InteractionRecord(
            tick=event.timestamp.tick,
            actor_id=str(event.actor_id),
            actor_role=actor_role,
            action=event.action,
            summary=summary_text,
            source=source,
            event_id=str(event.event_id),
            reply_to=event.input_data.get("reply_to_event_id"),
            channel=event.input_data.get("channel"),
            intended_for=event.input_data.get("intended_for", []),
        )

    def _get_actor_role(self, actor_id: ActorId) -> str:
        """Get the role string for an actor by ID."""
        actor_state = self._actor_states.get(actor_id)
        if actor_state:
            return actor_state.role
        return ""

    # -- Tier classification --

    def _classify_tier(self, actor: ActorState, reason: str) -> int:
        """Classify an activated actor as Tier 2 (batch) or Tier 3 (individual).

        Rules (from spec):
        - frustration > threshold -> Tier 3
        - role in high_stakes_roles -> Tier 3
        - deception_risk > 0.5 -> Tier 3
        - authority_level > 0.7 -> Tier 3
        - reason in threshold-related -> Tier 3
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
        # Subscription-triggered actors need full individual context
        # for meaningful collaborative responses
        if reason in ("subscription_immediate", "subscription_batch"):
            return 3
        return 2

    # -- Multi-Turn Tool Loop (replaces _activate_individual + _activate_autonomous_agent) --

    async def _activate_with_tool_loop(
        self,
        actor: ActorState,
        reason: str,
        trigger_event: WorldEvent | None,
        max_calls_override: int | None = None,
        append_closure: bool = True,
        state_summary: str | None = None,
    ) -> list[ActionEnvelope]:
        """Activate an agent with a multi-turn tool-calling loop.

        The agent maintains a conversation (messages array) across tool calls
        within this single activation. Each LLM response may contain multiple
        tool calls — all of them are executed in order (each through the full
        governance pipeline) and each appended to the conversation history so
        the next iteration sees the complete record. The loop terminates when:
        - Agent responds with text (findings) → auto-posted to team channel
          (unless the agent already explicitly chat-posted this activation)
        - Agent calls do_nothing
        - Total tool-call budget is exhausted

        Args:
            actor: The actor state to activate.
            reason: The activation reason string (e.g. "game_kickstart",
                "game_event", "autonomous_work", "subscription_immediate").
            trigger_event: The event that caused this activation, if any.
            max_calls_override: If set, overrides
                ``max_tool_calls_per_activation`` from config for this
                activation only. A value of ``None`` (or non-positive)
                falls back to the global default.

        Returns:
            List of ActionEnvelopes produced during this activation.
        """
        # PMF Plan Phase 4A — active-cohort gate. Applies only to
        # Active NPCs (``activation_profile_name`` set); agents are
        # always exempt so this never affects the agent path. When
        # ``self._cohort_manager`` is None (the default), the whole
        # block short-circuits and behavior is byte-identical to
        # pre-4A. When enabled, dormant NPCs dispatch to
        # ``record_only`` / ``defer`` / ``promote`` per
        # ``CohortConfig.inactive_event_policies``.
        # Review fix D3: stronger gate predicate — only actors that
        # are BOTH ``HUMAN`` type AND have an activation_profile are
        # cohort-gated. Previously we checked only
        # ``activation_profile_name is not None`` which would
        # accidentally capture any future non-HUMAN actor category
        # that gains a profile. This predicate is lifted into a
        # helper so the intent is reviewable at one site.
        cm = self._cohort_manager
        if cm is not None and self._should_cohort_gate(actor, cm):
            event_type = getattr(trigger_event, "event_type", "") if trigger_event else ""
            policy = cm.policy_for(event_type or "default")
            if policy == "record_only":
                # Review fix M4 + M8: record the decision as a ledger
                # entry so runners can explain why this NPC didn't
                # activate. We deliberately do NOT also append to
                # ``actor.pending_notifications`` here — the notify()
                # loop already added one generic entry earlier for
                # every subscription-matched actor, and doubling up
                # would bloat the actor's rolling buffer without new
                # information. The ``CohortDecisionEntry`` is the
                # authoritative record of the gate decision.
                self._record_cohort_decision(actor.actor_id, "record_only", event_type, cm)
                return []
            if policy == "defer":
                overflow_occurred = False
                if trigger_event is not None:
                    # N1: ``QueuedEvent`` is a frozen value object
                    # (not an engine). Value-object imports across
                    # module boundaries are fine per DESIGN_PRINCIPLES
                    # — the composition-root rule targets concrete
                    # *engine* classes. Consolidated to module scope.
                    # ``enqueue`` returns False on overflow-drop so we
                    # can log the overflow separately (M4).
                    did_queue = cm.enqueue(
                        actor.actor_id,
                        QueuedEvent(
                            event=trigger_event,
                            queued_tick=self._current_tick(),
                            reason="defer_inactive",
                        ),
                    )
                    overflow_occurred = not did_queue
                if overflow_occurred:
                    self._record_cohort_decision(actor.actor_id, "queue_overflow", event_type, cm)
                self._record_cohort_decision(actor.actor_id, "defer", event_type, cm)
                return []
            if policy == "promote":
                promoted, evicted = cm.try_promote(actor.actor_id)
                if not promoted:
                    # Budget exhausted → fall back to defer so the
                    # event isn't lost. The next rotation will surface
                    # this NPC naturally if its queue keeps growing.
                    if trigger_event is not None:
                        cm.enqueue(
                            actor.actor_id,
                            QueuedEvent(
                                event=trigger_event,
                                queued_tick=self._current_tick(),
                                reason="promote_budget_exhausted",
                            ),
                        )
                    self._record_cohort_decision(
                        actor.actor_id,
                        "promote_budget_exhausted",
                        event_type,
                        cm,
                    )
                    return []
                # Promotion succeeded — record and fall through to
                # normal NPC path so the LLM loop actually runs.
                self._record_cohort_decision(
                    actor.actor_id,
                    "promote",
                    event_type,
                    cm,
                    evicted_actor_id=evicted,
                )
                # PMF 4B cleanup commit 5 — publish CohortRotationEvent
                # on preempt-promote too, not just scheduled rotations.
                # Previously MemoryEngine (subscribed to cohort.rotated)
                # never saw try_promote evictions, so demoted actors
                # bypassed the memory-eviction/consolidation pathway
                # entirely (4A+4B audit M4).
                if evicted is not None:
                    from datetime import UTC, datetime

                    from volnix.core.events import CohortRotationEvent
                    from volnix.core.types import Timestamp

                    now = datetime.now(UTC)
                    tick_now = self._current_tick()
                    try:
                        await self.publish(
                            CohortRotationEvent(
                                timestamp=Timestamp(world_time=now, wall_time=now, tick=tick_now),
                                promoted_ids=[actor.actor_id],
                                demoted_ids=[evicted],
                                rotation_policy="preempt_promote",
                                tick=tick_now,
                            )
                        )
                    except (OSError, RuntimeError, ValueError) as exc:
                        logger.warning(
                            "try_promote: CohortRotationEvent publish "
                            "failed (cohort state still mutated): %s",
                            exc,
                        )

        # Active-NPC branch — catch both entry points (``notify`` calls
        # this method directly; ``activate_for_event`` routes through it
        # after locking). NPCs never play games (game players are filtered
        # to non-HUMAN types at app.py:1371 [verified]) and must not
        # acquire the agent prompt-builder context; their loop is
        # isolated in NPCActivator. Opt-in: the branch fires only when
        # both an ``activation_profile_name`` is set on the actor and an
        # ``NPCActivator`` has been injected via ``set_npc_activator``.
        if actor.activation_profile_name is not None and self._npc_activator is not None:
            return await self._npc_activator.activate_npc(
                actor=actor,
                reason=reason,
                trigger_event=trigger_event,
                max_calls_override=max_calls_override,
                host=self,
            )

        if not self._llm_router or not self._prompt_builder:
            return []
        if not self._tool_executor:
            logger.warning(
                "[AGENCY] No tool_executor set — cannot run multi-turn loop for %s",
                actor.actor_id,
            )
            return []

        import time as _time
        import uuid

        from volnix.ledger.entries import ActivationCompleteEntry, ToolLoopStepEntry

        activation_id = str(uuid.uuid4())[:12]
        # Per-activation tool-call budget. Override (from game runner's
        # actions_per_turn) wins when set; otherwise use the global default.
        max_calls = (
            max_calls_override
            if isinstance(max_calls_override, int) and max_calls_override > 0
            else self._typed_config.max_tool_calls_per_activation
        )
        tool_choice = self._typed_config.tool_choice_mode
        # Phase 2 (game_move): force the LLM to return a tool call.
        # "required" is supported by all providers (Gemini=ANY,
        # Anthropic={"type":"any"}, OpenAI="required"). This is the
        # clean way to ensure the agent makes a game move — no retry
        # loops, no nudge messages, no special-case handlers.
        if reason == "game_move":
            tool_choice = "required"

        async with self._llm_semaphore:
            system_prompt = self._prompt_builder.build_system_prompt()
            team_roster = [
                {"role": a.role, "id": str(a.actor_id)} for a in self._actor_states.values()
            ]
            actor_tools = self._get_tools_for_actor(str(actor.actor_id))

            # Two-phase game activation: research (game_research) uses
            # full tools, move (game_move) uses game-only tools.
            # activate_for_event dispatches the phases; this block just
            # configures the tool list for whichever phase we're in.
            _GAME_ACTIVATION_REASONS = {
                "game_kickstart",
                "game_event",
                "game_research",
                "game_move",
            }
            if reason in _GAME_ACTIVATION_REASONS:
                if reason == "game_move":
                    # Phase 2: game tools ONLY — force the negotiate move
                    allowed_services: set[str] | None = {"game"}
                    actor_tools = [t for t in actor_tools if t.service == "game"]
                else:
                    # Phase 1 (game_research) or legacy (game_kickstart/event):
                    # full tool set for research, text prompt focuses on game
                    allowed_services = {"game"}
                    actor_tools = [t for t in actor_tools if t.name != "do_nothing"]
            else:
                # Non-game: show all services in text prompt (existing behavior)
                allowed_services = {t.service for t in actor_tools if t.service}

            user_prompt = self._prompt_builder.build_individual_prompt(
                actor=actor,
                trigger_event=trigger_event,
                activation_reason=reason,
                available_actions=self._available_actions,
                team_roster=team_roster,
                allowed_services=allowed_services,
                simulation_progress=self._simulation_progress,
            )

            # Build messages: continue from persisted conversation or start fresh.
            #
            # For GAME activations (``game_kickstart`` / ``game_event``),
            # the caller (``activate_for_event``) has already appended a
            # game-specific state-summary user message to
            # ``activation_messages``. Do NOT layer the generic re-activation
            # context or autonomous lead/sub-agent instructions on top —
            # those are for delegation/monitoring workflows and will confuse
            # a game player (e.g. telling a non-lead negotiator to
            # "INVESTIGATE/SHARE/call do_nothing" directly contradicts the
            # game persona's instruction to counter or accept).
            #
            # Non-game re-activations (autonomous lead agents, subscription
            # triggers, etc.) still get the generic re-activation context +
            # autonomous phase instructions.
            _GAME_REASONS = {"game_kickstart", "game_event", "game_research", "game_move"}
            if actor.activation_messages:
                messages: list[dict[str, Any]] = list(actor.activation_messages)
                if reason not in _GAME_REASONS:
                    reactivation_ctx = self._build_reactivation_context(
                        actor,
                        trigger_event,
                        reason,
                    )
                    # Include updated phase-aware instructions on re-activation.
                    # Lead agents get phase-specific prompts (monitor/buffer)
                    # based on activation_reason + is_reactivation.
                    if actor.autonomous:
                        reactivation_instructions = (
                            ActorPromptBuilder.build_autonomous_instructions(
                                actor=actor,
                                team_roster=team_roster,
                                activation_reason=reason,
                                simulation_progress=self._simulation_progress,
                            )
                        )
                        combined = f"{reactivation_instructions}\n\n{reactivation_ctx}"
                    else:
                        combined = reactivation_ctx
                    if combined:
                        messages.append({"role": "user", "content": combined})
            else:
                # First activation: build from scratch
                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

            # Inject state summary — works on BOTH first activation
            # (messages just built from system+user) and re-activation
            # (messages loaded from activation_messages). Game state
            # (deal IDs, proposal history, world events) is visible
            # from the very first activation, not just re-activations.
            if state_summary:
                messages.append(
                    {
                        "role": "user",
                        "content": f"[game state update]\n{state_summary}",
                    }
                )

            envelopes: list[ActionEnvelope] = []
            terminated_by = "max_tool_calls"
            total_tool_calls = 0

            # Outer loop: one LLM call per iteration. Each response may
            # contain multiple tool calls (OpenAI, Anthropic, and Google
            # Gemini all support this); we execute all of them in order,
            # each through the governance pipeline, each recorded in the
            # conversation history. The LLM on the next iteration sees
            # the complete record of what happened and does not need to
            # re-emit any "dropped" calls.
            #
            # Iteration cap equals max_calls as a safety rail — if the
            # LLM only emits one call per iteration (the common pattern),
            # the outer loop naturally limits work to the budget.
            for iteration in range(max_calls):
                if total_tool_calls >= max_calls:
                    break

                # Compact tool-result history before each LLM call:
                # keep only the last N results verbatim, elide older.
                # Provider-agnostic — operates on the generic message
                # dict shape. See _history_compaction.py.
                messages = compact_tool_results(
                    messages,
                    keep_last=self._typed_config.max_verbatim_tool_results,
                    max_chars=self._typed_config.max_tool_result_chars,
                )

                step_start = _time.monotonic()

                request = LLMRequest(
                    messages=messages,
                    tools=actor_tools or None,
                    tool_choice=tool_choice,
                    cache_system_prompt=True,
                    model_override=actor.llm_model,
                    provider_override=actor.llm_provider,
                    thinking_enabled=actor.llm_thinking_enabled,
                    thinking_budget_tokens=(actor.llm_thinking_budget_tokens or 2048),
                )
                response = await self._llm_router.route(
                    request,
                    "agency",
                    self._typed_config.llm_use_case_individual,
                )
                step_latency = (_time.monotonic() - step_start) * 1000

                if response.tool_calls:
                    # Execute ALL tool calls from this response, in order,
                    # respecting the total budget. Build ONE assistant
                    # message containing every executed tool_call, followed
                    # by matching tool-result messages — this mirrors the
                    # original LLM response structure (one model turn with
                    # multiple function_calls) and preserves per-call
                    # provider metadata (including Gemini thought_signatures
                    # that Gemini 3 requires on replay).
                    stop_outer = False
                    executed_tc_dicts: list[dict[str, Any]] = []
                    tool_result_msgs: list[dict[str, Any]] = []

                    for tc_index, tc in enumerate(response.tool_calls):
                        if total_tool_calls >= max_calls:
                            stop_outer = True
                            break

                        tc_latency = step_latency if tc_index == 0 else 0.0

                        # do_nothing short-circuits the whole activation,
                        # even if it appears mid-response. Do not record it
                        # in the assistant history (it's a sentinel, not a
                        # real action); just terminate.
                        if tc.name == "do_nothing":
                            terminated_by = "do_nothing"
                            self._record_to_ledger(
                                ToolLoopStepEntry(
                                    actor_id=actor.actor_id,
                                    activation_id=activation_id,
                                    step_index=total_tool_calls,
                                    tool_name="do_nothing",
                                    llm_latency_ms=tc_latency,
                                )
                            )
                            stop_outer = True
                            break

                        # Parse tool call into ActionEnvelope. A bad parse is
                        # skipped (does NOT terminate the loop) so sibling
                        # calls in the same response still execute.
                        env = self._parse_tool_call(actor, tc, reason, trigger_event)
                        if env is None:
                            continue

                        # Execute through governance pipeline INLINE.
                        # Lock serializes pipeline access across parallel agents.
                        async with self._pipeline_lock:
                            committed_event = await self._tool_executor(env)

                        tc_id = tc.id or f"call_{iteration}_{tc_index}"
                        executed_tc_dicts.append(_build_tool_call_dict(tc, tc_id))

                        if committed_event is None:
                            # Pipeline blocked — still record the call in
                            # the assistant history and feed a BLOCKED
                            # result back so the LLM sees what happened.
                            tool_result_msgs.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": (
                                        "BLOCKED: This action was not permitted "
                                        "by the governance pipeline."
                                    ),
                                }
                            )
                            self._record_to_ledger(
                                ToolLoopStepEntry(
                                    actor_id=actor.actor_id,
                                    activation_id=activation_id,
                                    step_index=total_tool_calls,
                                    tool_name=tc.name,
                                    tool_arguments=tc.arguments,
                                    blocked=True,
                                    llm_latency_ms=tc_latency,
                                )
                            )
                            total_tool_calls += 1
                            continue

                        # Success — record envelope and append matching
                        # tool-result message.
                        envelopes.append(env)

                        # Full-fidelity serialization — compaction applied
                        # pre-LLM-call in compact_tool_results() owns
                        # char-capping uniformly.
                        result_body = json.dumps(
                            committed_event.response_body or {},
                            default=str,
                        )

                        tool_result_msgs.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": result_body,
                            }
                        )

                        self._record_to_ledger(
                            ToolLoopStepEntry(
                                actor_id=actor.actor_id,
                                activation_id=activation_id,
                                step_index=total_tool_calls,
                                tool_name=tc.name,
                                tool_arguments=tc.arguments,
                                event_id=committed_event.event_id,
                                llm_latency_ms=tc_latency,
                                response_preview=result_body[:200],
                            )
                        )
                        total_tool_calls += 1

                    # Commit the assistant message + tool results as a
                    # single coherent turn in the conversation history.
                    # One assistant message with N tool_calls, followed by
                    # N tool results (one per executed tool_call) — this
                    # is what Gemini, Anthropic, and OpenAI all expect
                    # when replaying multi-call responses.
                    if executed_tc_dicts:
                        assistant_msg: dict[str, Any] = {
                            "role": "assistant",
                            "tool_calls": executed_tc_dicts,
                        }
                        if response.provider_metadata:
                            assistant_msg["_provider_metadata"] = response.provider_metadata
                        messages.append(assistant_msg)
                        messages.extend(tool_result_msgs)

                    # Step 3b: turn-ending action detection for game
                    # activations. If any tool call in this response
                    # committed a game-service event (negotiate_*), the
                    # turn is over — yield to the other player. Non-game
                    # tool calls (Notion reads, Slack reads, chat posts)
                    # do NOT end the turn — they're research preparation.
                    if reason in _GAME_ACTIVATION_REASONS:
                        game_move_this_response = (
                            any(
                                getattr(e, "action_type", "").startswith("negotiate_")
                                for e in envelopes[-len(executed_tc_dicts) :]
                            )
                            if executed_tc_dicts
                            else False
                        )
                        if game_move_this_response:
                            terminated_by = "game_move"
                            stop_outer = True

                    if stop_outer:
                        break
                    if total_tool_calls >= max_calls:
                        terminated_by = "max_tool_calls"
                        break
                    # Otherwise continue to next iteration — the LLM may
                    # have more to do after seeing all the results.

                elif response.content:
                    # Text response — agent is sharing findings
                    terminated_by = "text_response"
                    text = response.content.strip()

                    # Update agent's goal_context with findings
                    actor.goal_context = text[:500]

                    # Persist text response in conversation history so the
                    # agent sees it on re-activation and doesn't repeat itself.
                    messages.append({"role": "assistant", "content": text})

                    # Auto-post findings to team channel — ONLY if the agent
                    # did not already explicitly chat-post during this
                    # activation. Without this guard the same text is posted
                    # twice: once via the agent's explicit chat.postMessage
                    # tool call earlier in the loop, and again via this
                    # auto-post branch.
                    already_posted_chat = any(
                        getattr(e, "action_type", "") == "chat.postMessage" for e in envelopes
                    )
                    if actor.team_channel and not already_posted_chat:
                        post_env = self._create_channel_post(
                            actor,
                            text,
                            reason,
                            trigger_event,
                        )
                        if post_env:
                            async with self._pipeline_lock:
                                committed = await self._tool_executor(post_env)
                            if committed:
                                envelopes.append(post_env)
                    break

                else:
                    # Empty response — model returned neither content nor tool_calls.
                    # Treat as do_nothing (agent has nothing to contribute).
                    terminated_by = "do_nothing"
                    logger.info(
                        "[AGENCY.loop] actor=%s iter=%d: empty response "
                        "(completion_tokens=%d), treating as do_nothing",
                        actor.actor_id,
                        iteration,
                        response.usage.completion_tokens if response.usage else 0,
                    )
                    break

            # Inject closure message so the agent knows what happened on re-activation.
            # Without this, max_tool_calls termination leaves the conversation
            # looking incomplete and the model repeats work.
            actions_taken = [e.action_type for e in envelopes]
            if terminated_by == "max_tool_calls":
                closure = (
                    f"[Your activation ended — you used all {len(envelopes)} tool calls. "
                    f"Actions taken: {', '.join(actions_taken[:5])}. "
                    "Do NOT repeat these actions on your next activation.]"
                )
            elif terminated_by == "text_response":
                closure = "[You shared your findings. Activation complete.]"
            elif terminated_by == "do_nothing":
                closure = "[Nothing to do. Activation complete.]"
            else:
                closure = f"[Activation ended: {terminated_by}.]"
            if append_closure:
                messages.append({"role": "user", "content": closure})

            # Persist conversation for future re-activations (always,
            # even without closure — Phase 1 persists so Phase 2 sees it)
            actor.activation_messages = messages

            # Record activation completion
            self._record_to_ledger(
                ActivationCompleteEntry(
                    actor_id=actor.actor_id,
                    activation_id=activation_id,
                    activation_reason=reason,
                    total_tool_calls=len(
                        [e for e in envelopes if e.action_type != "chat.postMessage"]
                    ),
                    total_envelopes=len(envelopes),
                    terminated_by=terminated_by,
                    final_text=(actor.goal_context or "")[:200],
                )
            )

        logger.info(
            "[AGENCY.loop] actor=%s reason=%s envelopes=%d terminated=%s",
            actor.actor_id,
            reason,
            len(envelopes),
            terminated_by,
        )
        return envelopes

    def _create_channel_post(
        self,
        actor: ActorState,
        text: str,
        reason: str,
        trigger_event: WorldEvent | None,
    ) -> ActionEnvelope | None:
        """Create an ActionEnvelope to post text to the agent's team channel."""
        if not actor.team_channel:
            return None

        parent_ids = [trigger_event.event_id] if trigger_event else []

        return ActionEnvelope(
            actor_id=actor.actor_id,
            source=ActionSource.INTERNAL,
            action_type="chat.postMessage",
            target_service=ServiceId("slack"),
            payload={
                "text": text,
                "channel": actor.team_channel,
                "channel_id": actor.team_channel,
                # No intended_for — auto-posts are passive recordings.
                # LLM-generated tool calls control who gets activated.
            },
            logical_time=self._get_current_time(),
            priority=EnvelopePriority.INTERNAL,
            parent_event_ids=parent_ids,
            metadata={
                "activation_reason": reason,
                "activation_tier": 3,
                "reasoning": "Sharing investigation findings with team",
            },
        )

    def _build_reactivation_context(
        self,
        actor: ActorState,
        trigger_event: WorldEvent | None,
        reason: str,
    ) -> str:
        """Build context update for a re-activated agent.

        Shows new team messages accumulated since the last activation
        so the agent can pick up where it left off.
        """
        parts: list[str] = [f"## Re-activation ({reason})"]

        # New team messages from recent_interactions
        team_msgs = [
            r
            for r in actor.recent_interactions
            if isinstance(r, InteractionRecord) and r.source != "self"
        ]
        if team_msgs:
            parts.append("### New team messages")
            for r in team_msgs[-5:]:
                tag = ""
                if r.intended_for:
                    if actor.role in r.intended_for or "all" in r.intended_for:
                        tag = " [TO YOU]"
                parts.append(f'- [{r.actor_role}]{tag}: "{r.summary}"')

        if trigger_event:
            parts.append(f"\nTriggered by: {trigger_event.actor_id} → {trigger_event.action}")

        parts.append(
            "\nContinue your work based on the new information above. "
            "Check your prior messages — do NOT repeat actions you already took."
        )

        return "\n".join(parts)

    # -- Response parsing --

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Strip markdown code fences from LLM output."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    def _parse_llm_action(
        self,
        actor: ActorState,
        raw_output: str,
        reason: str,
        trigger_event: WorldEvent | None,
    ) -> ActionEnvelope | None:
        """Parse LLM output into ActionEnvelope. Returns None for do_nothing."""
        try:
            cleaned = self._strip_code_fences(raw_output)
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM output for actor %s", actor.actor_id)
            return None

        if not isinstance(data, dict):
            logger.warning("LLM output is not a dict for actor %s", actor.actor_id)
            return None

        action_type = data.get("action_type", "do_nothing")
        if action_type == "do_nothing":
            return None

        # Apply state updates from LLM
        state_updates = data.get("state_updates", {})
        self._apply_state_updates(actor, state_updates)

        # Resolve target_service: LLM may return tool name instead of service name
        raw_service = data.get("target_service", "")
        resolved_service = self._resolve_service_name(raw_service, action_type)

        # Build payload — auto-fill communication context from trigger event
        # so the LLM only needs to provide text + intent, not API details.
        # For autonomous agents (no trigger), use their primary subscription channel.
        payload = data.get("payload", {})
        if trigger_event is not None:
            self._autofill_comm_context(payload, action_type, trigger_event, data)
        else:
            # Autonomous agent — use primary Slack subscription channel
            self._autofill_autonomous_comm(payload, action_type, actor, data)

        parent_ids = [trigger_event.event_id] if trigger_event else []

        return ActionEnvelope(
            actor_id=actor.actor_id,
            source=ActionSource.INTERNAL,
            action_type=action_type,
            target_service=ServiceId(resolved_service) if resolved_service else None,
            payload=payload,
            logical_time=self._get_current_time(),
            priority=EnvelopePriority.INTERNAL,
            parent_event_ids=parent_ids,
            metadata={
                "activation_reason": reason,
                "activation_tier": 3,
                "reasoning": data.get("reasoning", ""),
            },
        )

    def _parse_tool_call(
        self,
        actor: ActorState,
        tool_call: ToolCall,
        reason: str,
        trigger_event: WorldEvent | None,
    ) -> ActionEnvelope | None:
        """Parse a native tool call into ActionEnvelope. Returns None for do_nothing."""
        if tool_call.name == "do_nothing":
            return None

        # Look up original action name and service from build-time maps
        if tool_call.name in self._tool_name_map:
            action_type = self._tool_name_map[tool_call.name]
            service = self._tool_to_service.get(tool_call.name, "")
        elif "__" in tool_call.name:
            # Collision-prefixed tools: "slack__list" when two services share "list"
            service, sanitized_action = tool_call.name.split("__", 1)
            action_type = sanitized_action
        else:
            service = ""
            action_type = tool_call.name

        args = dict(tool_call.arguments)

        # Extract metadata from arguments
        reasoning = args.pop("reasoning", "")
        intended_for = args.pop("intended_for", [])
        state_updates = args.pop("state_updates", {})

        # Apply state updates (same as text-based path)
        if state_updates:
            self._apply_state_updates(actor, state_updates)

        # Remaining args = action payload
        payload = args

        # Auto-fill communication context (channel_id etc.)
        llm_data: dict[str, Any] = {"intended_for": intended_for}
        if trigger_event is not None:
            self._autofill_comm_context(payload, action_type, trigger_event, llm_data)
        else:
            self._autofill_autonomous_comm(payload, action_type, actor, llm_data)

        parent_ids = [trigger_event.event_id] if trigger_event else []

        return ActionEnvelope(
            actor_id=actor.actor_id,
            source=ActionSource.INTERNAL,
            action_type=action_type,
            target_service=ServiceId(service) if service else None,
            payload=payload,
            logical_time=self._get_current_time(),
            priority=EnvelopePriority.INTERNAL,
            parent_event_ids=parent_ids,
            metadata={
                "activation_reason": reason,
                "activation_tier": 3,
                "reasoning": reasoning,
            },
        )

    @staticmethod
    def _autofill_comm_context(
        payload: dict,
        action_type: str,
        trigger_event: WorldEvent,
        llm_data: dict,
    ) -> None:
        """Auto-fill communication fields from trigger event.

        The LLM provides text + intent. The system fills channel_id,
        thread_ts, and intended_for from the conversation context.
        """
        comm_actions = {
            "chat.postMessage",
            "chat.replyToThread",
            "chat.update",
            "users.messages.send",
            "email_send",
        }
        if action_type not in comm_actions:
            return

        # channel_id: always use trigger event's channel for replies.
        # Don't trust LLM's channel choice — system manages channel context.
        trigger_channel = (
            trigger_event.input_data.get("channel_id")
            or trigger_event.input_data.get("channel")
            or (trigger_event.response_body or {}).get("channel", "")
        )
        if trigger_channel:
            payload["channel_id"] = trigger_channel

        # channel: for subscription matching
        if "channel" not in payload and payload.get("channel_id"):
            payload["channel"] = payload["channel_id"]

        # thread_ts: for replyToThread, use trigger message's ts
        if action_type == "chat.replyToThread" and "thread_ts" not in payload:
            resp = trigger_event.response_body or {}
            payload["thread_ts"] = resp.get("ts", "")

        # intended_for: from LLM top-level field
        if "intended_for" not in payload:
            intended = llm_data.get("intended_for", [])
            if intended:
                payload["intended_for"] = intended

    @staticmethod
    def _autofill_autonomous_comm(
        payload: dict,
        action_type: str,
        actor: ActorState,
        llm_data: dict,
    ) -> None:
        """Auto-fill communication fields for autonomous agents (no trigger event).

        Uses the agent's first Slack subscription channel as the team channel.
        """
        comm_actions = {
            "chat.postMessage",
            "chat.replyToThread",
            "chat.update",
            "users.messages.send",
            "email_send",
        }
        if action_type not in comm_actions:
            return

        # Use team channel — the explicit channel set by configure_agency().
        if actor.team_channel:
            payload["channel_id"] = actor.team_channel

        if "channel" not in payload and payload.get("channel_id"):
            payload["channel"] = payload["channel_id"]

        # intended_for: from LLM top-level field
        if "intended_for" not in payload:
            intended = llm_data.get("intended_for", [])
            if intended:
                payload["intended_for"] = intended

    def _resolve_service_name(self, raw_service: str, action_type: str) -> str:
        """Resolve a service name from LLM output.

        The LLM sometimes returns the tool name (e.g. "chat.replyToThread")
        instead of the service name (e.g. "slack"). Look up the correct
        service from available_actions.
        """
        if not raw_service:
            # No service provided — look up by action_type
            for tool in self._available_actions:
                if tool.get("name") == action_type:
                    return tool.get("service", "")
            return ""

        # Check if raw_service is already a valid service name
        service_names = {t.get("service", "") for t in self._available_actions}
        if raw_service in service_names:
            return raw_service

        # raw_service might be a tool name — look up its service
        for tool in self._available_actions:
            if tool.get("name") == raw_service:
                return tool.get("service", "")

        return raw_service  # pass through as-is

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

            batch_payload = action_data.get("payload", {})
            self._autofill_comm_context(batch_payload, action_type, trigger_event, action_data)

            envelopes.append(
                ActionEnvelope(
                    actor_id=actor.actor_id,
                    source=ActionSource.INTERNAL,
                    action_type=action_type,
                    target_service=(
                        ServiceId(
                            self._resolve_service_name(
                                action_data.get("target_service", ""),
                                action_type,
                            )
                        )
                        if action_data.get("target_service")
                        else None
                    ),
                    payload=batch_payload,
                    logical_time=self._get_current_time(),
                    priority=EnvelopePriority.INTERNAL,
                    parent_event_ids=[trigger_event.event_id],
                    metadata={
                        "activation_reason": reason,
                        "activation_tier": 2,
                        "reasoning": action_data.get("reasoning", ""),
                    },
                )
            )

        return envelopes

    # -- Deterministic state updates --

    def update_actor_state(self, actor: ActorState, committed_event: WorldEvent) -> None:
        """Update actor's reactive state after a committed event. Deterministic, no LLM.

        Rules:
        - Frustration: +0.1 per patience window exceeded, -0.1 per positive event
        - WaitingFor: cleared when the waited-for entity is referenced
        - Recent interactions: append summary, keep last max_recent_interactions
        - Pending notifications: new events added between activations
        - Scheduled action: cleared when executed, can be set by LLM response
        """
        config = self._typed_config

        # Frustration update: increase if patience exceeded
        if actor.waiting_for:
            elapsed = committed_event.timestamp.tick - actor.waiting_for.since
            if elapsed >= actor.waiting_for.patience:
                actor.frustration = min(
                    1.0,
                    actor.frustration + config.frustration_increase_per_patience,
                )
                # Trigger escalation if defined (dedup: skip if already scheduled)
                if actor.waiting_for.escalation_action:
                    esc_action = actor.waiting_for.escalation_action
                    if not any(sa.action_type == esc_action for sa in actor.scheduled_actions):
                        actor.scheduled_actions.append(
                            ScheduledAction(
                                logical_time=committed_event.timestamp.tick + 1.0,
                                action_type=esc_action,
                                description=f"Escalation: {actor.waiting_for.description}",
                                target_service=None,
                                payload={
                                    "reason": "patience_expired",
                                    "original_wait": actor.waiting_for.description,
                                },
                            )
                        )

        # Check if this event resolves what the actor was waiting for
        if actor.waiting_for and str(committed_event.actor_id) != str(actor.actor_id):
            # Heuristic: event mentions this actor or their watched entity
            if str(actor.actor_id) in str(committed_event.input_data) or (
                committed_event.target_entity
                and str(committed_event.target_entity) in [str(e) for e in actor.watched_entities]
            ):
                actor.waiting_for = None
                actor.frustration = max(
                    0.0,
                    actor.frustration - config.frustration_decrease_per_positive,
                )

        # Clear pending_actions for self-actions that have now committed
        is_self = str(committed_event.actor_id) == str(actor.actor_id)
        if is_self:
            try:
                actor.pending_actions.remove(committed_event.action)
            except ValueError:
                pass

        # Recent interactions (structured InteractionRecord)
        # Skip if already recorded via subscription notification in notify()
        event_id_str = str(committed_event.event_id)
        already_recorded = any(r.event_id == event_id_str for r in actor.recent_interactions)
        if not already_recorded:
            text = committed_event.input_data.get("text", "")
            if text:
                summary = text[:300]
            else:
                # Include key params so agents know what they already queried
                key_params = {
                    k: v
                    for k, v in committed_event.input_data.items()
                    if k in ("id", "charge", "query", "customer", "status", "channel_id") and v
                }
                if key_params:
                    param_str = ", ".join(f"{k}={v}" for k, v in key_params.items())
                    summary = f"{committed_event.action}({param_str})"
                else:
                    summary = committed_event.action

            # Include truncated response data so agents see what tool calls returned
            response_summary = ""
            if is_self and committed_event.response_body:
                import json as _json

                response_summary = _json.dumps(committed_event.response_body, default=str)[:500]

            record = InteractionRecord(
                tick=committed_event.timestamp.tick,
                actor_id=str(committed_event.actor_id),
                actor_role=self._get_actor_role(committed_event.actor_id),
                action=committed_event.action,
                summary=summary,
                source="self" if is_self else "observed",
                event_id=event_id_str,
                reply_to=committed_event.input_data.get("reply_to_event_id"),
                channel=committed_event.input_data.get("channel"),
                intended_for=committed_event.input_data.get("intended_for", []),
                response_summary=response_summary,
            )
            actor.recent_interactions.append(record)
        max_interactions = config.max_recent_interactions
        if max_interactions <= 0:
            actor.recent_interactions.clear()
        elif len(actor.recent_interactions) > max_interactions:
            actor.recent_interactions = actor.recent_interactions[-max_interactions:]

    async def update_states_for_event(self, event: WorldEvent) -> None:
        """Update all internal actor states based on committed event. Deterministic."""
        for actor in self._actor_states.values():
            if actor.actor_type == "internal":
                self.update_actor_state(actor, event)

    def _apply_state_updates(self, actor: ActorState, updates: dict[str, Any]) -> None:
        """Apply LLM-suggested state updates to actor (within safe bounds)."""
        if not isinstance(updates, dict):
            return
        try:
            if "frustration_delta" in updates:
                delta = float(updates["frustration_delta"])
                actor.frustration = max(0.0, min(1.0, actor.frustration + delta))
        except (ValueError, TypeError):
            pass  # Skip invalid delta
        try:
            if "urgency" in updates:
                actor.urgency = max(0.0, min(1.0, float(updates["urgency"])))
        except (ValueError, TypeError):
            pass  # Skip invalid urgency
        if "new_goal" in updates and updates["new_goal"]:
            actor.current_goal = str(updates["new_goal"])
        if "goal_strategy" in updates and updates["goal_strategy"]:
            actor.goal_strategy = str(updates["goal_strategy"])
        try:
            if "schedule_action" in updates and updates["schedule_action"]:
                sa = updates["schedule_action"]
                actor.scheduled_actions.append(
                    ScheduledAction(
                        logical_time=float(sa.get("logical_time", self._get_current_time() + 60)),
                        action_type=str(sa.get("action_type", "check_status")),
                        description=str(sa.get("description", "")),
                        target_service=sa.get("target_service"),
                        payload=sa.get("payload", {}),
                    )
                )
        except (ValueError, TypeError, AttributeError):
            pass  # Skip invalid schedule_action

        # Pending tasks from LLM
        if "pending_tasks" in updates and isinstance(updates["pending_tasks"], list):
            actor.pending_tasks = [str(t) for t in updates["pending_tasks"]]

        # Goal context from LLM
        if "goal_context" in updates and updates["goal_context"]:
            actor.goal_context = str(updates["goal_context"])

        # Deliverable flag from lead actor
        if "deliverable" in updates and updates["deliverable"]:
            actor.pending_notifications.append(
                f"[DELIVERABLE] {str(updates.get('deliverable_content', ''))[:500]}"
            )

    def _get_current_time(self) -> float:
        """Get current logical time from the event queue (or 0 if not wired)."""
        event_queue = self._config.get("_event_queue")
        if event_queue is not None:
            return event_queue.current_time
        return 0.0

    # -- Public accessors --

    def get_actor_state(self, actor_id: ActorId) -> ActorState | None:
        """Return the state for the given actor, or None if not found."""
        return self._actor_states.get(actor_id)

    def get_all_states(self) -> list[ActorState]:
        """Return all actor states managed by this engine."""
        return list(self._actor_states.values())

    async def activate_for_event(
        self,
        actor_id: ActorId,
        reason: str,
        trigger_event: Event | None = None,
        max_calls_override: int | None = None,
        max_read_calls: int | None = None,
        state_summary: str | None = None,
    ) -> list[ActionEnvelope]:
        """Activate an actor for one multi-turn tool-loop iteration.

        Implements :class:`volnix.core.protocols.AgencyActivationProtocol`.
        This is the unified entry point used by:

        - :class:`GameOrchestrator` for ``game_kickstart`` and ``game_event``
          re-activations
        - :class:`SimulationRunner` for autonomous tick activations
        - The agent adapter for event-affected triggers

        Args:
            actor_id: The actor to activate.
            reason: Activation reason string. One of ``"game_kickstart"``,
                ``"game_event"``, ``"subscription_match"``,
                ``"event_affected"``, ``"autonomous_tick"``, or any other
                string the caller wants to tag this activation with. Game-
                reason values drive the prompt shape via the prompt
                builder's ``_GAME_REASONS`` check.
            trigger_event: The committed world event that caused this
                activation, if any. ``None`` for kickstarts. Passed through
                to :meth:`_activate_with_tool_loop` if the event is a
                :class:`WorldEvent`.
            max_calls_override: Override the per-activation tool-call
                budget. ``None`` falls back to
                ``max_tool_calls_per_activation`` from global agency config.
            state_summary: Optional compact game-state summary string.
                Injected as a fresh user message at the top of the actor's
                rolling conversation (``activation_messages``). Used for
                game re-activations so the LLM sees ground truth from state
                without replaying full history. Trimmed to a rolling
                window of ``K`` recent entries to cap prompt size.

        Returns:
            List of :class:`ActionEnvelope` objects produced during the
            activation. Empty list if the actor is unknown.
        """
        actor_state = self._actor_states.get(actor_id)
        if actor_state is None:
            logger.warning(
                "activate_for_event: unknown actor_id %s, ignoring activation",
                actor_id,
            )
            return []

        # Per-actor lock serializes same-actor activations. The orchestrator
        # feedback loop can request a re-activation while the previous one
        # is still mid-tool-loop (see class docstring above), which races
        # on ``actor_state.activation_messages`` mutation. Lazy-create the
        # lock on first use so unused actors don't pay the cost.
        actor_lock = self._actor_activation_locks.get(actor_id)
        if actor_lock is None:
            actor_lock = asyncio.Lock()
            self._actor_activation_locks[actor_id] = actor_lock

        async with actor_lock:
            # Rolling-window trim — cap activation_messages to prevent
            # unbounded prompt growth. Pins first 2 messages (system +
            # user prompt) so the agent never loses identity mid-game.
            # State summary injection moved to _activate_with_tool_loop
            # so it works on both first activation and re-activation.
            if actor_state.activation_messages:
                cap = self._typed_config.max_activation_messages
                if len(actor_state.activation_messages) > cap:
                    pinned = actor_state.activation_messages[:2]
                    rolling = actor_state.activation_messages[2:]
                    actor_state.activation_messages = pinned + rolling[-(cap - 2) :]

            # Only WorldEvent triggers are forwarded to the tool-loop; other
            # event types (lifecycle, policy, etc.) flow through as ``None``.
            world_trigger: WorldEvent | None = (
                trigger_event if isinstance(trigger_event, WorldEvent) else None
            )

            # Two-phase game activation: research → move.
            # Phase 1 (research): full tools, read the world.
            # Phase 2 (move): game tools only, make exactly 1 negotiate call.
            # The agent decides whether to research — if it calls a
            # negotiate tool in Phase 1, turn-ending fires and Phase 2
            # is skipped. If max_read_calls=0, Phase 1 is skipped entirely.
            if reason in {"game_kickstart", "game_event"}:
                research_budget = max_read_calls or 0

                # Phase 1: Research (optional)
                if research_budget > 0:
                    research_envelopes = await self._activate_with_tool_loop(
                        actor_state,
                        "game_research",
                        world_trigger,
                        max_calls_override=research_budget,
                        append_closure=False,
                        state_summary=state_summary,
                    )
                else:
                    research_envelopes = []

                # Short-circuit: if Phase 1 already made a game move
                # (turn-ending fired in research phase), skip Phase 2.
                phase1_made_game_move = any(
                    getattr(e, "action_type", "").startswith("negotiate_")
                    for e in research_envelopes
                )
                if phase1_made_game_move:
                    return research_envelopes

                # Sanitize Phase 1 history: replace non-game tool-call
                # messages with a text research summary so Phase 2 doesn't
                # see non-game tool names in the conversation. Without this,
                # weaker models (Haiku) hallucinate tool calls from history
                # even though only game tools are in Phase 2's tool list.
                if research_budget > 0:
                    game_tool_names = frozenset(
                        t.name
                        for t in self._get_tools_for_actor(
                            str(actor_state.actor_id),
                        )
                        if t.service == "game"
                    )
                    actor_state.activation_messages = _sanitize_history_for_game_move(
                        actor_state.activation_messages,
                        game_tool_names,
                        char_limit=self._typed_config.history_sanitize_char_limit,
                    )

                # Bridge message: tell the LLM research is done.
                # Only injected when Phase 1 actually ran (budget > 0).
                if research_budget > 0:
                    actor_state.activation_messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[Research phase complete. Based on what "
                                "you just read, make your negotiation "
                                "move now. You can only call "
                                "negotiate_propose, negotiate_counter, "
                                "negotiate_accept, or negotiate_reject.]"
                            ),
                        }
                    )

                # Phase 2: Move (required). Budget of 4 allows retries
                # Phase 2 uses tool_choice="required" so the LLM MUST
                # return a tool call. No retries needed.
                # State summary: if Phase 1 ran, it's already in the
                # persisted conversation. If Phase 1 was skipped
                # (budget=0), Phase 2 needs it directly.
                move_envelopes = await self._activate_with_tool_loop(
                    actor_state,
                    "game_move",
                    world_trigger,
                    max_calls_override=2,  # 1 game move + 1 margin
                    append_closure=True,
                    state_summary=state_summary if research_budget == 0 else None,
                )
                return research_envelopes + move_envelopes

            else:
                # Non-game: single-phase (unchanged)
                return await self._activate_with_tool_loop(
                    actor_state,
                    reason,
                    world_trigger,
                    max_calls_override=max_calls_override,
                    state_summary=state_summary,
                )
