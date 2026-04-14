"""World animator engine implementation.

Generates autonomous world events (NPC behaviour, scheduled triggers,
organic activity) on each simulation tick.

Uses: WorldScheduler (scheduling/) for deterministic events
Uses: OrganicGenerator (LLM) for creative events
Uses: ConditionExpander.build_prompt_context() (D1) for reality context
Uses: app.handle_action() for pipeline execution

Controlled by behavior mode from WorldPlan:
- static: OFF (tick returns [])
- dynamic: scheduled + organic
- reactive: events only in response to recent agent actions
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from volnix.core import BaseEngine, Event
from volnix.core.events import AnimatorEvent
from volnix.core.types import ActorId, Timestamp
from volnix.engines.animator.config import AnimatorConfig
from volnix.engines.animator.context import AnimatorContext
from volnix.engines.animator.generator import OrganicGenerator
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.scheduling.scheduler import WorldScheduler

logger = logging.getLogger(__name__)


def _parse_duration(duration_str: str) -> float:
    """Parse a duration string like '5m', '1h', '30s' into seconds.

    Supports: s (seconds), m (minutes), h (hours), d (days).
    Falls back to float(duration_str) if no suffix detected.
    """
    duration_str = duration_str.strip()
    suffixes = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    for suffix, multiplier in suffixes.items():
        if duration_str.endswith(suffix):
            try:
                return float(duration_str[:-1]) * multiplier
            except ValueError:
                pass
    try:
        return float(duration_str)
    except ValueError:
        return 60.0  # Default to 1 minute


def _parse_at_time(
    at_time_str: str,
    now: datetime | None = None,
) -> datetime | None:
    """Parse an ``at_time`` value into an absolute fire datetime.

    Supports two formats for blueprint-declared one-shot scheduled events:

    1. **Relative duration**: ``"60s"``, ``"2m"``, ``"1h"`` — interpreted
       as an offset from ``now``. Uses :func:`_parse_duration`.
    2. **Absolute ISO-8601 timestamp**: ``"2026-04-11T00:01:30Z"`` — used
       as-is (converted to timezone-aware UTC).

    Returns ``None`` on any parse failure so the caller can log and skip
    gracefully — we never want a malformed blueprint entry to raise and
    break the whole animator startup.

    Args:
        at_time_str: The string value from the YAML ``at_time`` field.
        now: Optional "now" for deterministic tests. Defaults to UTC now.

    Returns:
        The absolute fire datetime (timezone-aware UTC), or ``None`` if
        the string could not be parsed as either format.
    """
    if not isinstance(at_time_str, str):
        return None
    at_time_str = at_time_str.strip()
    if not at_time_str:
        return None
    if now is None:
        now = datetime.now(tz=UTC)

    # Heuristic: any string containing 'T' OR multiple hyphens is treated
    # as an ISO-8601 candidate first. Relative durations never contain 'T'
    # and never contain hyphens (suffixes are s/m/h/d).
    looks_iso = "T" in at_time_str or at_time_str.count("-") >= 2
    if looks_iso:
        try:
            # ``datetime.fromisoformat`` accepts '+00:00' but not 'Z' in
            # Python < 3.11, so normalize first.
            iso = at_time_str.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(iso)
            # Ensure timezone-aware (assume UTC if naive)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            # Fall through to relative-duration attempt only if ISO failed.
            pass

    # Relative duration (e.g. "60s", "2m")
    try:
        seconds = _parse_duration(at_time_str)
        # _parse_duration returns 60.0 on failure — distinguish that case
        # by re-trying a strict parse.
        if at_time_str.strip() not in {"60", "60.0"}:
            # If _parse_duration would have fallen back to 60.0 and the
            # input wasn't literally "60", treat as parse failure.
            if seconds == 60.0:
                # Strict re-parse to confirm
                stripped = at_time_str.strip()
                suffixes = {"s", "m", "h", "d"}
                suffix_ok = any(
                    stripped.endswith(suffix) and _is_numeric(stripped[:-1]) for suffix in suffixes
                )
                bare_ok = _is_numeric(stripped)
                if not (suffix_ok or bare_ok):
                    return None
        return now + timedelta(seconds=seconds)
    except Exception:
        return None


def _is_numeric(s: str) -> bool:
    """Return True if ``s`` parses as a float."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


class WorldAnimatorEngine(BaseEngine):
    """Autonomous world event generation engine.

    Uses WorldConditions to apply runtime probabilities (service failures,
    injection content in organic events).

    Behavior modes:
    - static: OFF -- tick() returns [] always
    - dynamic: scheduled + probabilistic + organic events
    - reactive: events only in response to recent agent actions
    """

    engine_name: ClassVar[str] = "animator"
    subscriptions: ClassVar[list[str]] = []  # animator uses tick() scheduling, not event-driven
    dependencies: ClassVar[list[str]] = ["state"]

    # -- BaseEngine hook -------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Initialize animator state. Real configuration happens in configure()."""
        self._scheduler: WorldScheduler | None = None
        self._generator: OrganicGenerator | None = None
        self._context: AnimatorContext | None = None
        self._behavior: str = "static"
        self._conditions: Any = None
        self._typed_config: AnimatorConfig = AnimatorConfig()
        self._recent_actions: list[dict[str, Any]] = []
        self._creativity_used_this_tick: int = 0
        self._available_tools: list[dict[str, Any]] = []

    async def configure(self, plan: WorldPlan, scheduler: WorldScheduler) -> None:
        """Configure from compiled world plan. Called after generate_world().

        Sets behavior mode, creates AnimatorContext, registers scheduled
        events from YAML, and creates the organic generator if LLM is available.

        Args:
            plan: The compiled WorldPlan with conditions, behavior, and animator_settings.
            scheduler: The shared WorldScheduler instance.
        """
        self._behavior = plan.behavior
        self._conditions = plan.conditions
        self._scheduler = scheduler

        # Build typed config from plan's animator_settings
        settings = plan.animator_settings or {}
        self._typed_config = AnimatorConfig(
            **{k: v for k, v in settings.items() if k in AnimatorConfig.model_fields}
        )

        # Build an optional state reader for the AnimatorContext (P3).
        # When state is available, the organic LLM animator gets a
        # capped snapshot of the current world entities so it can
        # generate contextually-relevant events that reference real
        # existing entities (e.g. escalating a specific weather_alert
        # instead of inventing a generic new one). Backward compat: if
        # no state engine is wired, the reader is None and the context
        # renders a placeholder in the prompt.
        state_engine = self._dependencies.get("state") if self._dependencies else None
        state_reader = self._build_state_reader(state_engine) if state_engine is not None else None

        # Optional blueprint override of which entity types to exclude
        # from the snapshot (defaults exclude game-internal types like
        # negotiation_target/scorecard to avoid leaking private game
        # state into the organic animator).
        snapshot_exclude_raw = settings.get("state_snapshot_exclude")
        snapshot_exclude: list[str] | None = None
        if isinstance(snapshot_exclude_raw, list):
            snapshot_exclude = [str(e) for e in snapshot_exclude_raw]

        # Build AnimatorContext (reuses WorldGenerationContext pattern)
        self._context = AnimatorContext(
            plan,
            available_tools=self._available_tools,
            state_reader=state_reader,
            state_snapshot_exclude=snapshot_exclude,
        )

        # Register scheduled events from YAML animator settings.
        #
        # Three formats are supported:
        # - ``interval: "60s"``   → recurring, fires every N seconds
        # - ``trigger: "<expr>"`` → fires when a condition is met
        # - ``at_time: "60s"`` or ISO-8601 → one-shot, fires once at T+N
        #
        # Events with none of these keys are skipped with a warning —
        # silent drops make blueprint debugging miserable.
        for event_config in settings.get("scheduled_events", []):
            if "interval" in event_config:
                scheduler.register_recurring(
                    interval_seconds=_parse_duration(str(event_config["interval"])),
                    event_def=event_config,
                    source="animator",
                )
            elif "trigger" in event_config:
                scheduler.register_trigger(
                    condition=event_config["trigger"],
                    event_def=event_config,
                    source="animator",
                )
            elif "at_time" in event_config:
                at_time_val = event_config["at_time"]
                fire_time = _parse_at_time(str(at_time_val))
                if fire_time is None:
                    logger.warning(
                        "Invalid at_time %r in scheduled_events — skipping event: %s",
                        at_time_val,
                        event_config,
                    )
                    continue
                scheduler.register_event(
                    fire_time=fire_time,
                    event_def=event_config,
                    source="animator",
                )
            else:
                logger.warning(
                    "Scheduled event has no interval/trigger/at_time — skipping: %s",
                    event_config,
                )

        # Create organic generator if LLM available and not static
        llm_router = self._config.get("_llm_router")
        if llm_router and self._behavior != "static":
            self._generator = OrganicGenerator(
                llm_router=llm_router,
                context=self._context,
                config=self._typed_config,
            )

        # Track recent organic events across ticks so LLM can vary actors/actions
        self._recent_organic_events: list[dict[str, str]] = []

        logger.info(
            "Animator configured: behavior=%s, creativity=%s, budget=%d",
            self._behavior,
            self._typed_config.creativity,
            self._typed_config.creativity_budget_per_tick,
        )

    @staticmethod
    def _build_state_reader(state_engine: Any) -> Any:
        """Build an async callable that returns a compact entity snapshot.

        The returned callable is passed to :class:`AnimatorContext` which
        invokes it each tick inside ``for_organic_generation``. It reads
        all entity types from the state engine and returns a dict keyed
        by entity_type. AnimatorContext itself handles capping, field
        selection, and exclusion of game-internal types.

        If the state engine does not expose the expected methods
        (``list_entity_types`` + ``query_entities``), the reader logs a
        warning once and returns an empty dict thereafter.
        """

        async def read_snapshot() -> dict[str, list[dict[str, Any]]]:
            try:
                entity_types = await state_engine.list_entity_types()
            except AttributeError:
                logger.warning(
                    "Animator state reader: state_engine has no "
                    "list_entity_types() — snapshot disabled."
                )
                return {}
            except Exception as exc:
                logger.warning(
                    "Animator state reader: list_entity_types raised %s "
                    "— returning empty snapshot.",
                    exc,
                )
                return {}

            snapshot: dict[str, list[dict[str, Any]]] = {}
            for entity_type in entity_types:
                try:
                    rows = await state_engine.query_entities(entity_type)
                except Exception as exc:
                    logger.debug(
                        "Animator state reader: query_entities(%s) failed: %s",
                        entity_type,
                        exc,
                    )
                    continue
                if rows:
                    snapshot[entity_type] = rows
            return snapshot

        return read_snapshot

    async def tick(self, world_time: datetime) -> list[dict[str, Any]]:
        """Advance the animator by one logical tick and return generated actions.

        Layer 1a: Time-based scheduled events (from YAML scheduled_events)
        Layer 1b: Probabilistic events from per-attribute numbers
        Layer 2: Organic events (LLM, within creativity budget)

        Args:
            world_time: Current simulation time.

        Returns:
            List of result dicts from executed events (via pipeline).
            Empty list if behavior is "static".
        """
        if self._behavior == "static":
            return []

        results: list[dict[str, Any]] = []
        self._creativity_used_this_tick = 0

        # Layer 1a: Time-based scheduled events (deterministic, no LLM)
        if self._scheduler:
            state_engine = self._dependencies.get("state")
            scheduled = await self._scheduler.get_due_events(world_time, state_engine)
            for event_def in scheduled:
                result = await self._execute_event(event_def, world_time)
                results.append(result)

        # Layer 2: Organic events (LLM, within creativity budget)
        if self._generator and self._behavior in ("dynamic", "reactive"):
            budget = self._typed_config.creativity_budget_per_tick - self._creativity_used_this_tick
            if self._behavior == "reactive" and not self._recent_actions:
                # Reactive mode: no events without recent agent actions
                budget = 0
            recent = self._recent_actions if self._behavior == "reactive" else None
            if budget > 0:
                logger.info(
                    "Animator organic generation: budget=%d, behavior=%s, recent_actions=%d",
                    budget,
                    self._behavior,
                    len(recent or []),
                )
                organic = await self._generator.generate(
                    world_time,
                    budget,
                    recent,
                    recent_organic=self._recent_organic_events,
                )
                logger.info("Animator organic generated %d events", len(organic))
                for event_def in organic:
                    result = await self._execute_event(event_def, world_time)
                    results.append(result)
                    self._creativity_used_this_tick += 1
                    # Track for next tick's context (keep last 10)
                    self._recent_organic_events.append(
                        {
                            "actor": event_def.get("actor_id", "system"),
                            "action": event_def.get("action", ""),
                            "service": event_def.get("service_id", ""),
                        }
                    )
                    self._recent_organic_events = self._recent_organic_events[-10:]
        elif not self._generator and self._behavior != "static":
            logger.warning("Animator: no organic generator available (LLM router missing?)")

        self._recent_actions = []
        return results

    async def _execute_event(
        self, event_def: dict[str, Any], world_time: datetime
    ) -> dict[str, Any]:
        """Execute event through the 7-step pipeline via app.handle_action().

        Args:
            event_def: The event definition dict with actor_id, service_id, action, input_data.
            world_time: Current simulation time.

        Returns:
            Result dict from the pipeline execution.
        """
        app = self._config.get("_app")

        # Validate input_data has required fields before hitting the
        # pipeline. Skipping invalid events is cheaper than a pipeline
        # round-trip that fails at the responder with a validation error.
        action_name = event_def.get("action", "")
        input_data = event_def.get("input_data") or {}
        if self._available_tools:
            tool_def = next(
                (t for t in self._available_tools if t.get("name") == action_name),
                None,
            )
            if tool_def:
                required = set(tool_def.get("parameters", {}).get("required", []))
                missing = required - set(input_data.keys())
                if missing:
                    logger.warning(
                        "Animator: skipping event %s — missing required fields %s in input_data",
                        action_name,
                        missing,
                    )
                    return {"status": "skipped", "reason": f"missing_fields: {missing}"}

        result: dict[str, Any]
        if app:
            result = await app.handle_action(
                actor_id=event_def.get("actor_id", "system"),
                service_id=event_def.get("service_id", "world"),
                action=event_def.get("action", "animator_event"),
                input_data=input_data,
                world_time=world_time,
            )
        else:
            # Fallback if app not wired (should not happen in production)
            result = {"status": "executed", "event_def": event_def}

        # Publish AnimatorEvent to the event bus
        await self.publish(
            AnimatorEvent(
                event_type=f"animator.{event_def.get('action', 'event')}",
                timestamp=Timestamp(
                    world_time=world_time,
                    wall_time=datetime.now(tz=UTC),
                    tick=0,
                ),
                sub_type=event_def.get("sub_type", "organic"),
                actor_id=ActorId(event_def.get("actor_id", "system")),
                content=event_def,
            )
        )

        return result

    def _generate_probabilistic_events(
        self, context: AnimatorContext, world_time: datetime
    ) -> list[dict[str, Any]]:
        """Generate deterministic probabilistic events based on Level 2 numbers.

        These are NOT LLM-generated -- they're probability checks against
        the per-attribute intensity values from the compiler YAML.

        Uses a seeded RNG for reproducibility (same world_time = same events).
        Maps abstract concepts (volatility, failures) to real pack tools.

        Args:
            context: The AnimatorContext with dimension_values.
            world_time: Current simulation time (used as RNG seed).

        Returns:
            List of event definition dicts for events that passed probability checks.
        """
        events: list[dict[str, Any]] = []
        rng = random.Random(hash(world_time.isoformat()))

        # Classify available tools by http_method for mapping
        write_tools = [
            t
            for t in self._available_tools
            if t.get("http_method", "GET").upper() in ("POST", "PUT")
        ]
        if not write_tools:
            # No write tools → can't generate state-changing events
            return events

        def _pick_tool(tools: list[dict]) -> dict[str, Any]:
            return rng.choice(tools)

        # Reliability: service failures → update existing data (simulate stale/corrupt)
        failure_prob = context.get_probability("reliability", "failures")
        if rng.random() < failure_prob:
            tool = _pick_tool(write_tools)
            events.append(
                {
                    "actor_id": "system",
                    "service_id": tool.get("pack_name", "world"),
                    "action": tool["name"],
                    "input_data": {"_animator_reason": "service_reliability_event"},
                    "sub_type": "scheduled",
                }
            )

        # Complexity: volatility → create new data (news, price movement)
        volatility_prob = context.get_probability("complexity", "volatility")
        if rng.random() < volatility_prob:
            tool = _pick_tool(write_tools)
            events.append(
                {
                    "actor_id": "system",
                    "service_id": tool.get("pack_name", "world"),
                    "action": tool["name"],
                    "input_data": {"_animator_reason": "market_volatility_event"},
                    "sub_type": "scheduled",
                }
            )

        return events

    # -- SimulationRunner adapter methods ----------------------------------------

    async def check_scheduled_events(self, current_time: float) -> list:
        """Check for due scheduled/probabilistic events. Returns ActionEnvelopes.

        Adapter method called by SimulationRunner. Delegates to the scheduler's
        deterministic Layer 1a checking (same logic as tick() Layer 1a).

        Args:
            current_time: Current logical time in the simulation.

        Returns:
            List of ActionEnvelopes for due scheduled events.
        """
        from volnix.core.envelope import ActionEnvelope
        from volnix.core.types import ActionSource, EnvelopePriority, ServiceId

        envelopes: list[ActionEnvelope] = []
        if self._behavior == "static":
            return envelopes

        if self._scheduler:
            from datetime import UTC, datetime

            # Convert logical time to datetime for scheduler compatibility
            world_time = datetime.fromtimestamp(current_time, tz=UTC)
            state_engine = getattr(self, "_dependencies", {}).get("state")
            due_events = await self._scheduler.get_due_events(world_time, state_engine)
            for evt in due_events:
                envelopes.append(
                    ActionEnvelope(
                        actor_id=ActorId(evt.get("actor_id", "environment")),
                        source=ActionSource.ENVIRONMENT,
                        action_type=evt.get("action", "environment_event"),
                        target_service=(
                            ServiceId(evt["service_id"]) if evt.get("service_id") else None
                        ),
                        payload=evt.get("input_data", {}),
                        logical_time=current_time,
                        priority=EnvelopePriority.ENVIRONMENT,
                        metadata={"event_type": "scheduled"},
                    )
                )
        return envelopes

    async def notify_event(self, committed_event: Any) -> list:
        """Called after a committed event. May generate reactive environment events.

        Adapter method called by SimulationRunner. Records the event for
        reactive mode and returns an empty list (reactive event generation
        happens during tick()).

        Args:
            committed_event: The committed WorldEvent.

        Returns:
            List of ActionEnvelopes (currently empty; reactive events generated in tick()).
        """
        # Track for reactive mode
        if self._behavior == "reactive" and hasattr(committed_event, "action"):
            self._recent_actions.append(
                {
                    "action": getattr(committed_event, "action", ""),
                    "actor_id": str(getattr(committed_event, "actor_id", "")),
                    "event_type": getattr(committed_event, "event_type", ""),
                }
            )
        return []

    def has_scheduled_events(self) -> bool:
        """Check if there are future scheduled events.

        Used by SimulationRunner to decide if the simulation should continue
        when the event queue is empty.

        Returns:
            True if the scheduler has pending events, False otherwise.
        """
        if self._scheduler:
            return self._scheduler.pending_count > 0
        return False

    def next_scheduled_time(self) -> float | None:
        """Earliest logical time (float seconds) of the next scheduled event, or None.

        Converts the scheduler's datetime-based fire time to float seconds,
        the inverse of the ``datetime.fromtimestamp(current_time)`` conversion
        used in :meth:`check_scheduled_events`.
        """
        if not self._scheduler:
            return None
        nft = self._scheduler.next_fire_time
        if nft is None:
            return None
        return nft.timestamp()

    # -- Event handling --------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Track recent agent actions for reactive mode.

        In reactive mode, the animator generates events only in response
        to recent agent actions. This handler records relevant events.

        Args:
            event: An inbound event from the bus.
        """
        if self._behavior == "reactive" and hasattr(event, "action"):
            self._recent_actions.append(
                {
                    "action": getattr(event, "action", ""),
                    "actor_id": str(getattr(event, "actor_id", "")),
                    "event_type": event.event_type,
                }
            )
