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
        """Handle bus events. WorldEvents trigger notify().

        When SimulationRunner is active (event_queue is wired), skip —
        the runner calls notify() directly. Running both paths causes
        a re-entrancy deadlock on _llm_semaphore.
        """
        if self._config.get("_event_queue") is not None:
            return  # SimulationRunner handles notify() directly

        if isinstance(event, WorldEvent):
            envelopes = await self.notify(event)

    def _record_to_ledger(self, *entries) -> None:
        """Schedule ledger writes without blocking the caller.

        Ledger is observability — writes must never block the simulation loop.
        Uses asyncio.create_task for fire-and-forget scheduling.
        """
        ledger = self._config.get("_ledger")
        if ledger is None:
            return

        async def _write(lgr, items):
            for entry in items:
                try:
                    await lgr.append(entry)
                except Exception:
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

        # Subscription-based activation (collaborative communication)
        if self._typed_config.collaboration_enabled:
            already_activated = {aid for aid, _ in activated}
            for actor_id, actor in self._actor_states.items():
                if str(actor_id) == str(committed_event.actor_id):
                    continue  # don't notify yourself
                if actor_id in already_activated:
                    continue  # already activated by tier1

                for sub in actor.subscriptions:
                    # When intended_for includes "all", only require service match
                    # (not specific channel/filter) — broadcast to all listeners
                    intended_for = committed_event.input_data.get("intended_for", [])
                    if "all" in intended_for:
                        if str(committed_event.service_id) != sub.service_id:
                            continue
                    elif not self._matches_subscription(committed_event, sub):
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
                    logger.info(
                        "[AGENCY.notify] %s sub matched: svc=%s sensitivity=%s",
                        actor_id, sub.service_id, sub.sensitivity,
                    )

                    if collab_mode == "tagged" and intended_for:
                        # Only activate if actor is tagged or "all"
                        if (
                            "all" in intended_for
                            or actor.role in intended_for
                            or str(actor_id) in intended_for
                        ):
                            # V2: batch/passive sensitivity gating
                            should_activate = True
                            activation_reason = "subscription_match"
                    elif collab_mode == "open":
                        # V2: batch/passive sensitivity gating
                        should_activate = True
                        activation_reason = "subscription_match"
                    elif not intended_for:
                        # No intended_for specified — treat as open
                        # V2: batch/passive sensitivity gating
                        should_activate = True
                        activation_reason = "subscription_match"

                    if should_activate:
                        activated.append((actor_id, activation_reason))

                    # Record subscription match to ledger (non-blocking)
                    from terrarium.ledger.entries import (
                        CollaborationNotificationEntry,
                        SubscriptionMatchEntry,
                    )
                    self._record_to_ledger(
                        SubscriptionMatchEntry(
                            actor_id=actor_id,
                            event_id=committed_event.event_id,
                            service_id=sub.service_id,
                            sensitivity=sub.sensitivity,
                            activated=should_activate,
                            reason=activation_reason or "passive",
                        ),
                        CollaborationNotificationEntry(
                            recipient_actor_id=actor_id,
                            source_actor_id=committed_event.actor_id,
                            event_id=committed_event.event_id,
                            channel=committed_event.input_data.get("channel"),
                            intended_for=intended_for,
                            sensitivity=sub.sensitivity,
                        ),
                    )

                    break  # one match per actor per event

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
        from terrarium.ledger.entries import ActorActivationEntry
        for actor_id, reason in activated:
            tier = self._classify_tier(self._actor_states[actor_id], reason)
            self._record_to_ledger(ActorActivationEntry(
                actor_id=actor_id,
                activation_reason=reason,
                activation_tier=tier,
                trigger_event_id=committed_event.event_id,
            ))

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

        # Record action generation to ledger (non-blocking)
        from terrarium.ledger.entries import ActionGenerationEntry
        for env in envelopes:
            self._record_to_ledger(ActionGenerationEntry(
                actor_id=env.actor_id,
                envelope_id=env.envelope_id,
                action_type=env.action_type,
                tier=env.metadata.get("activation_tier", 0),
            ))

        return envelopes

    async def check_scheduled_actions(self, current_time: float) -> list[ActionEnvelope]:
        """Check for actors with scheduled actions that are due."""
        envelopes: list[ActionEnvelope] = []
        for actor in self._actor_states.values():
            if actor.scheduled_action and actor.scheduled_action.logical_time <= current_time:
                sa = actor.scheduled_action
                actor.scheduled_action = None

                if sa.action_type == "continue_work":
                    # Autonomous agent work loop — activate via LLM
                    env = await self._activate_autonomous_agent(actor)
                    if env is not None:
                        envelopes.append(env)
                else:
                    # Standard scheduled action (produce_deliverable, etc.)
                    env = ActionEnvelope(
                        actor_id=actor.actor_id,
                        source=ActionSource.INTERNAL,
                        action_type=sa.action_type,
                        target_service=(ServiceId(sa.target_service) if sa.target_service else None),
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
        return any(a.scheduled_action is not None for a in self._actor_states.values())

    def next_scheduled_time(self) -> float | None:
        """Earliest logical_time of any actor's scheduled action, or None."""
        earliest: float | None = None
        for actor in self._actor_states.values():
            if actor.scheduled_action is not None:
                t = actor.scheduled_action.logical_time
                if earliest is None or t < earliest:
                    earliest = t
        return earliest

    async def generate_deliverable(
        self, actor_id: ActorId, payload: dict,
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
        conversation = "\n".join(
            f"[{r.actor_role or r.actor_id}] {r.summary}"
            for r in actor.recent_interactions[-20:]
        ) if actor.recent_interactions else "(no conversation history)"

        system_prompt = self._prompt_builder.build_system_prompt()
        user_prompt = (
            f"## DELIVERABLE REQUEST\n\n"
            f"{goal_context}\n\n"
            f"## TEAM CONVERSATION\n\n{conversation}\n\n"
            f"## OUTPUT FORMAT\n\n"
            f"Respond with ONLY a JSON object matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```\n\n"
            f"Synthesize the team's discussion into this structured format. "
            f"Be comprehensive and include all key findings, methodology, "
            f"and any dissenting views from the conversation."
        )

        try:
            request = LLMRequest(
                system_prompt=system_prompt,
                user_content=user_prompt,
                temperature=0.3,
                cache_system_prompt=True,
            )
            response = await self._llm_router.route(
                request, "agency",
                self._typed_config.llm_use_case_individual,
            )

            content = response.content.strip()
            # Strip markdown code fences if present
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
            # Build team roster for intended_for tagging
            team_roster = [
                {"role": a.role, "id": str(a.actor_id)}
                for a in self._actor_states.values()
            ]
            user_prompt = self._prompt_builder.build_individual_prompt(
                actor=actor,
                trigger_event=trigger_event,
                activation_reason=reason,
                available_actions=self._available_actions,
                team_roster=team_roster,
            )

            request = LLMRequest(
                system_prompt=system_prompt,
                user_content=user_prompt,
                output_schema=None,  # We parse JSON from text
                temperature=0.7,
                fresh_session=True,  # Each actor gets isolated ACP session
                cache_system_prompt=True,  # System prompt is identical across actors
            )
            response = await self._llm_router.route(
                request,
                "agency",
                self._typed_config.llm_use_case_individual,
            )

        logger.info(
            "[AGENCY.individual] actor=%s, LLM response length=%d, preview=%s",
            actor.actor_id, len(response.content or ""),
            (response.content or "")[:200],
        )
        return self._parse_llm_action(actor, response.content, reason, trigger_event)

    async def _activate_autonomous_agent(
        self, actor: ActorState,
    ) -> ActionEnvelope | None:
        """Activate an autonomous agent to continue their work loop.

        The agent sees their full context including recent_interactions
        (messages from teammates received via event bus subscriptions).
        They decide what to do next: research, share findings, or do_nothing.
        """
        if not self._llm_router or not self._prompt_builder:
            return None

        async with self._llm_semaphore:
            system_prompt = self._prompt_builder.build_system_prompt()
            team_roster = [
                {"role": a.role, "id": str(a.actor_id)}
                for a in self._actor_states.values()
            ]
            user_prompt = self._prompt_builder.build_individual_prompt(
                actor=actor,
                trigger_event=None,
                activation_reason="autonomous_continue",
                available_actions=self._available_actions,
                team_roster=team_roster,
            )

            request = LLMRequest(
                system_prompt=system_prompt,
                user_content=user_prompt,
                output_schema=None,
                temperature=0.7,
                fresh_session=True,
                cache_system_prompt=True,
            )
            response = await self._llm_router.route(
                request,
                "agency",
                self._typed_config.llm_use_case_individual,
            )

        logger.info(
            "[AGENCY.autonomous] actor=%s, LLM response length=%d",
            actor.actor_id, len(response.content or ""),
        )
        env = self._parse_llm_action(actor, response.content, "autonomous_continue", None)

        # Auto-reschedule: if the agent produced an action, schedule next tick
        if env is not None and actor.autonomous:
            tick_interval = self._typed_config.autonomous_tick_interval
            actor.scheduled_action = ScheduledAction(
                logical_time=self._get_current_time() + tick_interval,
                action_type="continue_work",
                description=f"Continue: {actor.current_goal or 'mission'}",
                target_service=None,
                payload={},
            )

        return env

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
                    cache_system_prompt=True,  # System prompt is identical across batches
                )
                response = await self._llm_router.route(
                    request,
                    "agency",
                    self._typed_config.llm_use_case_batch,
                )

            logger.info(
                "[AGENCY.batch] LLM response length=%d, preview=%s",
                len(response.content or ""),
                (response.content or "")[:200],
            )
            batch_envs = self._parse_batch_response(batch, response.content, trigger_event)
            envelopes.extend(batch_envs)

        return envelopes

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
            "chat.postMessage", "chat.replyToThread", "chat.update",
            "users.messages.send", "email_send",
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
            "chat.postMessage", "chat.replyToThread", "chat.update",
            "users.messages.send", "email_send",
        }
        if action_type not in comm_actions:
            return

        # Use team channel from agent's subscriptions.
        # Don't trust LLM's channel choice — system manages channel context.
        for sub in actor.subscriptions:
            if sub.service_id == "slack" and sub.filter.get("channel"):
                payload["channel_id"] = sub.filter["channel"]
                break

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
                        ServiceId(self._resolve_service_name(
                            action_data.get("target_service", ""), action_type,
                        ))
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
        # Skip if already recorded via subscription notification in notify()
        event_id_str = str(committed_event.event_id)
        already_recorded = any(r.event_id == event_id_str for r in actor.recent_interactions)
        if not already_recorded:
            text = committed_event.input_data.get("text", "")
            summary = text[:300] if text else f"{committed_event.action}"
            record = InteractionRecord(
                tick=committed_event.timestamp.tick,
                actor_id=str(committed_event.actor_id),
                actor_role=self._get_actor_role(committed_event.actor_id),
                action=committed_event.action,
                summary=summary,
                source="observed",
                event_id=event_id_str,
                reply_to=committed_event.input_data.get("reply_to_event_id"),
                channel=committed_event.input_data.get("channel"),
                intended_for=committed_event.input_data.get("intended_for", []),
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
