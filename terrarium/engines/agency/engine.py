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

from terrarium.actors.state import ActorState, InteractionRecord, ScheduledAction, Subscription
from terrarium.core.engine import BaseEngine
from terrarium.core.envelope import ActionEnvelope
from terrarium.core.events import Event, WorldEvent
from terrarium.core.types import (
    ActionSource,
    ActorId,
    EnvelopePriority,
    ServiceId,
)
from terrarium.engines.agency.config import AgencyConfig
from terrarium.engines.agency.prompt_builder import ActorPromptBuilder
from terrarium.llm.types import LLMRequest
from terrarium.simulation.world_context import WorldContextBundle

logger = logging.getLogger(__name__)


class AgencyEngine(BaseEngine):
    """Manages internal actor lifecycle: activation, action generation, state updates."""

    engine_name: ClassVar[str] = "agency"
    subscriptions: ClassVar[list[str]] = ["world", "simulation"]
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
        self._llm_semaphore = asyncio.Semaphore(self._typed_config.max_concurrent_actor_calls)

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
        """Handle bus events. WorldEvents trigger notify()."""
        logger.info(
            "[AGENCY._handle_event] type=%s, is_WorldEvent=%s, event_type=%s",
            type(event).__name__, isinstance(event, WorldEvent),
            getattr(event, "event_type", "?"),
        )
        if isinstance(event, WorldEvent):
            envelopes = await self.notify(event)
            # Submit envelopes to the event queue if wired
            event_queue = self._config.get("_event_queue")
            logger.info(
                "[AGENCY._handle_event] envelopes=%d, queue_wired=%s",
                len(envelopes), event_queue is not None,
            )
            if event_queue is not None:
                for env in envelopes:
                    event_queue.submit(env)

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
            logger.info("[AGENCY.notify] no actor_states — returning empty")
            return []

        # Tier 1: deterministic activation check
        activated = self._tier1_activation_check(committed_event)
        logger.info("[AGENCY.notify] tier1 activated: %d", len(activated))

        # Subscription-based activation (collaborative communication)
        if self._typed_config.collaboration_enabled:
            already_activated = {aid for aid, _ in activated}
            for actor_id, actor in self._actor_states.items():
                if str(actor_id) == str(committed_event.actor_id):
                    continue  # don't notify yourself
                if actor_id in already_activated:
                    continue  # already activated by tier1

                for sub in actor.subscriptions:
                    if not self._matches_subscription(committed_event, sub):
                        continue

                    # Build structured interaction record
                    record = self._build_interaction_record(
                        committed_event, actor, source="notified"
                    )
                    actor.recent_interactions.append(record)
                    if len(actor.recent_interactions) > actor.max_recent_interactions:
                        actor.recent_interactions = actor.recent_interactions[
                            -actor.max_recent_interactions :
                        ]

                    # Check intended_for tagging (token efficiency)
                    collab_mode = self._typed_config.collaboration_mode
                    intended_for = committed_event.input_data.get("intended_for", [])

                    should_activate = False
                    activation_reason = ""

                    if collab_mode == "tagged" and intended_for:
                        # Only activate if actor is tagged or "all"
                        if (
                            "all" in intended_for
                            or actor.role in intended_for
                            or str(actor_id) in intended_for
                        ):
                            if sub.sensitivity == "immediate":
                                should_activate = True
                                activation_reason = "subscription_immediate"
                            elif sub.sensitivity == "batch":
                                actor.batch_notification_count += 1
                                if actor.batch_notification_count >= actor.batch_threshold:
                                    should_activate = True
                                    activation_reason = "subscription_batch"
                                    actor.batch_notification_count = 0
                            # passive: record stored, no activation
                    elif collab_mode == "open":
                        # All subscribed actors activate
                        if sub.sensitivity == "immediate":
                            should_activate = True
                            activation_reason = "subscription_immediate"
                        elif sub.sensitivity == "batch":
                            actor.batch_notification_count += 1
                            if actor.batch_notification_count >= actor.batch_threshold:
                                should_activate = True
                                activation_reason = "subscription_batch"
                                actor.batch_notification_count = 0
                    elif not intended_for:
                        # No intended_for specified — treat as open for this event
                        if sub.sensitivity == "immediate":
                            should_activate = True
                            activation_reason = "subscription_immediate"
                        elif sub.sensitivity == "batch":
                            actor.batch_notification_count += 1
                            if actor.batch_notification_count >= actor.batch_threshold:
                                should_activate = True
                                activation_reason = "subscription_batch"
                                actor.batch_notification_count = 0

                    if should_activate:
                        activated.append((actor_id, activation_reason))

                    # Record subscription match to ledger
                    ledger = self._config.get("_ledger")
                    if ledger is not None:
                        from terrarium.ledger.entries import (
                            CollaborationNotificationEntry,
                            SubscriptionMatchEntry,
                        )

                        match_entry = SubscriptionMatchEntry(
                            actor_id=actor_id,
                            event_id=committed_event.event_id,
                            service_id=sub.service_id,
                            sensitivity=sub.sensitivity,
                            activated=should_activate,
                            reason=activation_reason or "passive",
                        )
                        collab_entry = CollaborationNotificationEntry(
                            recipient_actor_id=actor_id,
                            source_actor_id=committed_event.actor_id,
                            event_id=committed_event.event_id,
                            channel=committed_event.input_data.get("channel"),
                            intended_for=intended_for,
                            sensitivity=sub.sensitivity,
                        )
                        # Use fire-and-forget pattern for ledger writes
                        try:
                            await ledger.append(match_entry)
                            await ledger.append(collab_entry)
                        except Exception:
                            logger.debug(
                                "Failed to record subscription match to ledger"
                            )

                    break  # one match per actor per event

        if not activated:
            return []

        logger.info(
            "[AGENCY.notify] total activated (tier1+subs): %d — %s",
            len(activated),
            [(str(a), r) for a, r in activated[:5]],
        )

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

        # Record activations to ledger
        ledger = self._config.get("_ledger")
        if ledger is not None:
            from terrarium.ledger.entries import ActorActivationEntry

            for actor_id, reason in activated:
                tier = self._classify_tier(self._actor_states[actor_id], reason)
                entry = ActorActivationEntry(
                    actor_id=actor_id,
                    activation_reason=reason,
                    activation_tier=tier,
                    trigger_event_id=committed_event.event_id,
                )
                await ledger.append(entry)

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

        # Respect max envelopes per event
        envelopes = envelopes[: self._typed_config.max_envelopes_per_event]

        # Record action generation to ledger
        if ledger is not None:
            from terrarium.ledger.entries import ActionGenerationEntry

            for env in envelopes:
                entry = ActionGenerationEntry(
                    actor_id=env.actor_id,
                    envelope_id=env.envelope_id,
                    action_type=env.action_type,
                    tier=env.metadata.get("activation_tier", 0),
                )
                await ledger.append(entry)

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
                    target_service=(ServiceId(sa.target_service) if sa.target_service else None),
                    payload=sa.payload,
                    logical_time=current_time,
                    priority=EnvelopePriority.INTERNAL,
                    metadata={
                        "activation_reason": "scheduled",
                        "scheduled_description": sa.description,
                    },
                )
                envelopes.append(env)
                actor.scheduled_action = None
        return envelopes

    def has_scheduled_actions(self) -> bool:
        """Return True if any actor has a scheduled action."""
        return any(a.scheduled_action is not None for a in self._actor_states.values())

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
                and actor.scheduled_action
                and actor.scheduled_action.action_type == "produce_deliverable"
                and actor.scheduled_action.logical_time <= event_time
            ):
                activated.append((actor_id, "synthesis_deadline"))
                continue

            # 5. Scheduled action due
            if actor.scheduled_action and actor.scheduled_action.logical_time <= event_time:
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
            sub.service_id, dict(sub.filter),
            event.input_data.get("channel", event.input_data.get("channel_id", "?")),
        )
        # Service must match
        if str(event.service_id) != sub.service_id:
            return False

        # Match filter criteria against event payload and metadata
        for key, value in sub.filter.items():
            if value == "self":
                continue  # resolved at activation time, not here

            # "entity" filter matches against event's entity context
            # (e.g. filter={"entity": "message"} matches chat.postMessage)
            if key == "entity":
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
        if len(summary_text) > 200:
            summary_text = summary_text[:197] + "..."

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

        async with self._llm_semaphore:
            system_prompt = self._prompt_builder.build_system_prompt()
            user_prompt = self._prompt_builder.build_individual_prompt(
                actor=actor,
                trigger_event=trigger_event,
                activation_reason=reason,
                available_actions=self._available_actions,
            )

            request = LLMRequest(
                system_prompt=system_prompt,
                user_content=user_prompt,
                output_schema=None,  # We parse JSON from text
                temperature=0.7,
            )
            response = await self._llm_router.route(
                request,
                "agency",
                self._typed_config.llm_use_case_individual,
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
        batch_size = self._typed_config.batch_size
        batches: list[list[tuple[ActorState, str]]] = []
        for i in range(0, len(actors_with_reasons), batch_size):
            batches.append(actors_with_reasons[i : i + batch_size])

        envelopes: list[ActionEnvelope] = []
        for batch in batches:
            actors_triggers: list[tuple[ActorState, WorldEvent | None, str]] = [
                (actor, trigger_event, reason) for actor, reason in batch
            ]

            async with self._llm_semaphore:
                system_prompt = self._prompt_builder.build_system_prompt()
                user_prompt = self._prompt_builder.build_batch_prompt(
                    actors_with_triggers=actors_triggers,
                    available_actions=self._available_actions,
                )

                request = LLMRequest(
                    system_prompt=system_prompt,
                    user_content=user_prompt,
                    temperature=0.7,
                )
                response = await self._llm_router.route(
                    request,
                    "agency",
                    self._typed_config.llm_use_case_batch,
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

        return ActionEnvelope(
            actor_id=actor.actor_id,
            source=ActionSource.INTERNAL,
            action_type=action_type,
            target_service=(
                ServiceId(data["target_service"]) if data.get("target_service") else None
            ),
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

            envelopes.append(
                ActionEnvelope(
                    actor_id=actor.actor_id,
                    source=ActionSource.INTERNAL,
                    action_type=action_type,
                    target_service=(
                        ServiceId(action_data["target_service"])
                        if action_data.get("target_service")
                        else None
                    ),
                    payload=action_data.get("payload", {}),
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
                # Trigger escalation if defined
                if actor.waiting_for.escalation_action:
                    actor.scheduled_action = ScheduledAction(
                        logical_time=committed_event.timestamp.tick + 1.0,
                        action_type=actor.waiting_for.escalation_action,
                        description=f"Escalation: {actor.waiting_for.description}",
                        target_service=None,
                        payload={
                            "reason": "patience_expired",
                            "original_wait": actor.waiting_for.description,
                        },
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

        # Recent interactions (structured InteractionRecord)
        record = InteractionRecord(
            tick=committed_event.timestamp.tick,
            actor_id=str(committed_event.actor_id),
            actor_role=self._get_actor_role(committed_event.actor_id),
            action=committed_event.action,
            summary=f"{committed_event.action} by {committed_event.actor_id}",
            source="observed",
            event_id=str(committed_event.event_id),
            reply_to=committed_event.input_data.get("reply_to_event_id"),
            channel=committed_event.input_data.get("channel"),
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
                actor.scheduled_action = ScheduledAction(
                    logical_time=float(sa.get("logical_time", self._get_current_time() + 60)),
                    action_type=str(sa.get("action_type", "check_status")),
                    description=str(sa.get("description", "")),
                    target_service=sa.get("target_service"),
                    payload=sa.get("payload", {}),
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
