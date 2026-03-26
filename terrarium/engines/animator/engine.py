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
from datetime import datetime, timezone
from typing import Any, ClassVar

from terrarium.core import ActionContext, BaseEngine, Event
from terrarium.core.events import AnimatorEvent
from terrarium.core.types import ActorId, Timestamp
from terrarium.engines.animator.config import AnimatorConfig
from terrarium.engines.animator.context import AnimatorContext
from terrarium.engines.animator.generator import OrganicGenerator
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.scheduling.scheduler import WorldScheduler

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
        self._typed_config = AnimatorConfig(**{
            k: v for k, v in settings.items()
            if k in AnimatorConfig.model_fields
        })

        # Build AnimatorContext (reuses WorldGenerationContext pattern)
        self._context = AnimatorContext(plan)

        # Register scheduled events from YAML animator settings
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

        # Create organic generator if LLM available and not static
        llm_router = self._config.get("_llm_router")
        if llm_router and self._behavior != "static":
            self._generator = OrganicGenerator(
                llm_router=llm_router,
                context=self._context,
                config=self._typed_config,
            )

        logger.info(
            "Animator configured: behavior=%s, creativity=%s, budget=%d",
            self._behavior,
            self._typed_config.creativity,
            self._typed_config.creativity_budget_per_tick,
        )

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

        # Layer 1b: Probabilistic events from per-attribute numbers
        # Uses Level 2 compiler YAML numbers: reliability.failures=20 -> 20% chance
        if self._context:
            probabilistic = self._generate_probabilistic_events(self._context, world_time)
            for event_def in probabilistic:
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
                organic = await self._generator.generate(world_time, budget, recent)
                for event_def in organic:
                    result = await self._execute_event(event_def, world_time)
                    results.append(result)
                    self._creativity_used_this_tick += 1

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

        result: dict[str, Any]
        if app:
            result = await app.handle_action(
                actor_id=event_def.get("actor_id", "system"),
                service_id=event_def.get("service_id", "world"),
                action=event_def.get("action", "animator_event"),
                input_data=event_def.get("input_data", {}),
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
                    wall_time=datetime.now(tz=timezone.utc),
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

        Args:
            context: The AnimatorContext with dimension_values.
            world_time: Current simulation time (used as RNG seed).

        Returns:
            List of event definition dicts for events that passed probability checks.
        """
        events: list[dict[str, Any]] = []
        rng = random.Random(hash(world_time.isoformat()))

        # Reliability: service failures
        failure_prob = context.get_probability("reliability", "failures")
        if rng.random() < failure_prob:
            events.append({
                "actor_id": "system",
                "service_id": "world",
                "action": "service_degradation",
                "input_data": {"type": "failure", "probability": failure_prob},
                "sub_type": "scheduled",
            })

        # Reliability: service degradation over time
        degradation_prob = context.get_probability("reliability", "degradation")
        if rng.random() < degradation_prob:
            events.append({
                "actor_id": "system",
                "service_id": "world",
                "action": "service_degradation",
                "input_data": {"type": "degradation", "probability": degradation_prob},
                "sub_type": "scheduled",
            })

        # Complexity: volatility (situation changes)
        volatility_prob = context.get_probability("complexity", "volatility")
        if rng.random() < volatility_prob:
            events.append({
                "actor_id": "system",
                "service_id": "world",
                "action": "situation_change",
                "input_data": {"type": "volatility", "probability": volatility_prob},
                "sub_type": "scheduled",
            })

        # Boundaries: access control incidents
        gaps_prob = context.get_probability("boundaries", "boundary_gaps")
        if rng.random() < gaps_prob:
            events.append({
                "actor_id": "system",
                "service_id": "world",
                "action": "access_incident",
                "input_data": {"type": "boundary_gap", "probability": gaps_prob},
                "sub_type": "scheduled",
            })

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
        from terrarium.core.envelope import ActionEnvelope
        from terrarium.core.types import ActionSource, EnvelopePriority, ServiceId

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
            self._recent_actions.append({
                "action": getattr(committed_event, "action", ""),
                "actor_id": str(getattr(committed_event, "actor_id", "")),
                "event_type": getattr(committed_event, "event_type", ""),
            })
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

    # -- Event handling --------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Track recent agent actions for reactive mode.

        In reactive mode, the animator generates events only in response
        to recent agent actions. This handler records relevant events.

        Args:
            event: An inbound event from the bus.
        """
        if self._behavior == "reactive" and hasattr(event, "action"):
            self._recent_actions.append({
                "action": getattr(event, "action", ""),
                "actor_id": str(getattr(event, "actor_id", "")),
                "event_type": event.event_type,
            })
